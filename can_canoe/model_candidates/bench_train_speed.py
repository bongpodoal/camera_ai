#!/usr/bin/env python3
"""학습 속도 실측용 벤치마크 (학습 PC 에서 실행). 데이터셋 없이 **무작위 이미지로 순전파+역전파**를 반복해서 GPU 가 낼 수 있는 초당 이미지 수(img/s)와 VRAM 사용량을 잰다.

실제 학습의 손실 함수·데이터 읽기·증강(모자이크 등)은 빠져 있으므로 **GPU 만 봤을 때의 상한**이다. 실제 1 epoch 시간 = 이미지 수 ÷ min(GPU img/s, 데이터 읽기 img/s).
(데이터 읽기가 느리면 CPU 코어·num_workers 가 병목이 된다 — BDD100K 를 받은 뒤 1 epoch 를 직접 돌려서 확인한다.)

예) python3 bench_train_speed.py --cand ~/camera_work/candidates --batches 8 16 32 --images 70000
    python3 bench_train_speed.py --only a_yolom_n --steps 2 --batches 2          (동작 확인)
선택 가능: a_yolom_n, a_yolom_s, hybridnets_d3, yolop, (yolopx 는 --with-yolopx)
"""
import argparse
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_arch as M      # noqa: E402  (모델 구조를 만드는 함수 재사용)


def tensors(o):
    if isinstance(o, torch.Tensor):
        yield o
    elif isinstance(o, (list, tuple)):
        for t in o:
            yield from tensors(t)


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def bench(model, h, w, batch, steps, warmup, device, amp):
    model = model.to(device).train()
    opt = torch.optim.SGD(model.parameters(), lr=1e-5)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    x = torch.randn(batch, 3, h, w, device=device)

    def step():
        opt.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device, dtype=torch.float16, enabled=amp and device == "cuda"):
            out = model(x)
            loss = sum(t.float().mean() for t in tensors(out))
        loss.backward()
        opt.step()

    for _ in range(warmup):
        step()
    if device == "cuda":
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(steps):
        step()
    if device == "cuda":
        torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    peak = torch.cuda.max_memory_allocated() / 1e9 if device == "cuda" else float("nan")
    return batch * steps / dt, peak


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cand", default=str(Path("~/camera_work/candidates").expanduser()))
    ap.add_argument("--batches", type=int, nargs="+", default=[8, 16, 32])
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--images", type=int, default=70000, help="1 epoch 의 이미지 수 (BDD100K train 70,000)")
    ap.add_argument("--no-amp", action="store_true", help="혼합 정밀도(AMP) 끄기")
    ap.add_argument("--only", help="한 모델만 (예: a_yolom_n)")
    ap.add_argument("--with-yolopx", action="store_true")
    a = ap.parse_args()
    cand = Path(a.cand).expanduser()
    device = pick_device()
    jobs = [("a_yolom_n", "A-YOLOM(n)", lambda: M.a_yolom(cand, "n")[0], [(288, 512), (384, 640)]),
            ("a_yolom_s", "A-YOLOM(s)", lambda: M.a_yolom(cand, "s")[0], [(288, 512)]),
            ("hybridnets_d3", "HybridNets(d3)", lambda: M.hybridnets(cand)[0], [(256, 512), (384, 640)]),
            ("yolop", "YOLOP", lambda: M.yolop_family(cand, "yolop")[0], [(288, 512), (384, 640)])]
    if a.with_yolopx:
        jobs.append(("yolopx", "YOLOPX", lambda: M.yolop_family(cand, "yolopx")[0], [(288, 512)]))
    print(f"장치: {device}" + (f" ({torch.cuda.get_device_name(0)}, VRAM {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)" if device == "cuda" else ""))
    print(f"| 모델 | 입력 | batch | img/s | 최대 VRAM(GB) | 1 epoch({a.images} 장) 추정 |\n|---|---|---|---|---|---|")
    for key, label, build, sizes in jobs:
        if a.only and a.only != key:
            continue
        for (h, w) in sizes:
            for b in a.batches:
                try:
                    model = build()
                    ips, peak = bench(model, h, w, b, a.steps, a.warmup, device, not a.no_amp)
                    ep = a.images / ips
                    print(f"| {label} | {w}x{h} | {b} | {ips:.0f} | {peak:.1f} | {ep / 60:.1f} 분 |", flush=True)
                except torch.cuda.OutOfMemoryError:
                    print(f"| {label} | {w}x{h} | {b} | - | VRAM 부족 | - |", flush=True)
                    torch.cuda.empty_cache()
                except Exception as e:
                    print(f"| {label} | {w}x{h} | {b} | 실패 | {str(e)[:50]} | - |", flush=True)
                finally:
                    import gc
                    gc.collect()
                    if device == "cuda":
                        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
