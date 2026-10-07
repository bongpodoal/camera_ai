#!/usr/bin/env python3
"""다중작업 후보 5개의 구조(파라미터·연산량·출력 모양)를 같은 방법으로 잰다. 가중치 없이 구조만 만들어서 잰다 (속도는 구조로 정해지므로).

준비: 후보 저장소를 CAND 폴더에 받아 둔다 (아래 이름) + 파이썬 환경에 torch, efficientnet_pytorch, timm==0.6.13, yacs, loguru,
      setuptools<81, pyyaml, tqdm, psutil, thop, pandas, requests 설치.
      git clone --depth 1 https://github.com/JiayuanWang-JW/YOLOv8-multi-task a_yolom ; datvuthanh/HybridNets hybridnets ;
      jiaoZ7688/YOLOPX yolopx ; hustvl/YOLOP yolop ; CAIC-AD/YOLOPv2 yolopv2 (+ yolopv2.pt 릴리스 가중치)
실행: python3 measure_arch.py [--cand ~/camera_work/candidates] [--yolopv2-weights ~/camera_work/yolopv2.pt]
연산량은 GMACs(곱셈-덧셈 1쌍을 1로 센 값)다. torch.utils.flop_counter 의 FLOPs 를 2로 나눴다.
"""
import argparse
import os
import sys
from pathlib import Path

import torch
from torch.utils.flop_counter import FlopCounterMode

SIZES = {"320x320": (320, 320), "512x288": (288, 512), "640x384": (384, 640)}      # 이름: (높이, 너비)


def shapes(o):
    if isinstance(o, (list, tuple)):
        return [shapes(t) for t in o]
    return tuple(o.shape) if hasattr(o, "shape") else type(o).__name__


def count(model, sizes):
    res = {}
    for name, (h, w) in sizes.items():
        x = torch.randn(1, 3, h, w)
        try:
            with FlopCounterMode(display=False) as fc, torch.no_grad():
                out = model(x)
            res[name] = (fc.get_total_flops() / 2e9, shapes(out))
        except Exception as e:
            res[name] = (None, str(e)[:80])
    return res


def params(model):
    return sum(p.numel() for p in model.parameters()) / 1e6


def in_repo(path):
    """저장소 폴더로 들어간다. YOLOP 와 YOLOPX 는 둘 다 'lib' 패키지를 쓰므로, 앞서 불러온 'lib*' 모듈을 비워야 서로 섞이지 않는다."""
    for k in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
        del sys.modules[k]
    sys.path[:] = [p for p in sys.path if "camera_work/candidates" not in p]
    sys.path.insert(0, str(path))
    os.chdir(path)


def a_yolom(cand, scale):
    in_repo(cand / "a_yolom")
    from ultralytics.nn.tasks import MultiModel
    m = MultiModel(f"ultralytics/models/v8/yolov8-bdd-v4-one-dropout-individual-{scale}.yaml", ch=3, nc=None, verbose=False).eval()
    return m, SIZES


def hybridnets(cand):
    in_repo(cand / "hybridnets")
    from backbone import HybridNetsBackbone
    m = HybridNetsBackbone(num_classes=11, compound_coef=3, seg_classes=4, seg_mode="multiclass", onnx_export=True).eval()
    return m, {"512x256": (256, 512), "640x384": (384, 640)}        # 128 의 배수만 가능 (P7 이 stride 128)


def yolop_family(cand, name):
    in_repo(cand / name)
    from lib.config import cfg
    from lib.models import get_net
    cfg.defrost()
    cfg.MODEL.PRETRAINED = ""
    cfg.freeze()
    return get_net(cfg).eval(), SIZES


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cand", default=str(Path("~/camera_work/candidates").expanduser()))
    ap.add_argument("--yolopv2-weights", default=str(Path("~/camera_work/yolopv2.pt").expanduser()))
    a = ap.parse_args()
    cand = Path(a.cand).expanduser()
    jobs = [("A-YOLOM(n)", lambda: a_yolom(cand, "n")), ("A-YOLOM(s)", lambda: a_yolom(cand, "s")),
            ("HybridNets(d3)", lambda: hybridnets(cand)), ("YOLOP", lambda: yolop_family(cand, "yolop")),
            ("YOLOPX", lambda: yolop_family(cand, "yolopx"))]
    print("| 모델 | 파라미터(M) | 입력 | GMACs | 출력 모양 |\n|---|---|---|---|---|")
    for label, build in jobs:
        cwd = os.getcwd()
        try:
            model, sizes = build()
            p = params(model)
            for name, (g, out) in count(model, sizes).items():
                print(f"| {label} | {p:.2f} | {name} | {'실패' if g is None else f'{g:.2f}'} | {out if g is None else out} |")
        except Exception as e:
            print(f"| {label} | - | - | 실패 | {str(e)[:80]} |")
        os.chdir(cwd)
    wp = Path(a.yolopv2_weights)
    if wp.exists():
        m = torch.jit.load(str(wp), map_location="cpu").eval()
        p = params(m)
        for name, (g, out) in count(m, SIZES).items():
            print(f"| YOLOPv2 | {p:.2f} | {name} | {'실패' if g is None else f'{g:.2f}'} | {out} |")


if __name__ == "__main__":
    main()
