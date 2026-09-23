"""YOLO 모델을 OAK-D(RVC2) 엣지에 올리는 전 과정을 한 파일로 묶었다.

    export   .pt      -> NNArchive(ONNX)   luxonis/tools, 로컬 실행 (업로드 없음)
    convert  NNArchive(ONNX) -> NNArchive(blob)   blobconverter, 온라인 (가중치가 Luxonis 서버로 업로드됨)
    inspect  NNArchive 내용 확인 (입력 크기, 전처리, 후처리)
    run      OAK-D에 올려 실행 (검출 수 + 정상 구간 FPS)

사용 예:
    python3 tools/edge_deploy.py export  best.pt --imgsz "512 288" --out work/
    python3 tools/edge_deploy.py convert work/best.tar.xz --out work/best_rvc2.tar.xz
    python3 tools/edge_deploy.py inspect work/best_rvc2.tar.xz
    python3 tools/edge_deploy.py run     work/best_rvc2.tar.xz --ip 169.254.1.222 --seconds 10
    python3 tools/edge_deploy.py run     luxonis/yolov6-nano:r2-coco-512x288 --ip 169.254.1.222

전처리 규칙: 입력 ÷255는 블롭 또는 config.json 중 한 곳에서만 한다.
convert는 config가 scale을 선언하면 블롭에 굽지 않고, 선언하지 않으면 블롭에 굽는다.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter, deque
from pathlib import Path


# ---------------------------------------------------------------- export
def cmd_export(args):
    """① .pt -> ONNX + config.json (NNArchive). luxonis/tools가 YOLO 헤드를 depthai 디코더 형식으로 바꾼다."""
    if not shutil.which("tools"):
        sys.exit("luxonis/tools 미설치. 설치:\n"
                 "  git clone --recursive https://github.com/luxonis/tools.git && cd tools\n"
                 "  PIP_CONSTRAINT=constraints.txt PIP_BUILD_CONSTRAINT=constraints.txt pip install .")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["tools", args.pt, "--imgsz", args.imgsz, "--encoding", args.encoding,
           "--output-dir", str(out)]
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)
    archives = sorted(out.rglob("*.tar.xz"), key=lambda p: p.stat().st_mtime)
    if archives:
        print("NNArchive:", archives[-1])


# ---------------------------------------------------------------- convert
def _read_archive(path, dst):
    with tarfile.open(path) as t:
        t.extractall(dst, filter="data")
    cfg_path = Path(dst) / "config.json"
    return cfg_path, json.loads(cfg_path.read_text())


def cmd_convert(args):
    """② ONNX -> .blob (FP16, MYRIAD), ③ blob + config.json -> NNArchive."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path, cfg = _read_archive(args.archive, tmp)
        meta = cfg["model"]["metadata"]
        onnx = Path(tmp) / meta["path"]
        if onnx.suffix != ".onnx":
            sys.exit(f"ONNX가 든 NNArchive가 아님: {meta['path']}")

        pre = cfg["model"]["inputs"][0]["preprocessing"]
        if all(float(s) == 1.0 for s in pre["scale"]):
            params = ["--scale_values=[255,255,255]"]     # config가 안 하므로 블롭에 굽는다
            if pre.get("reverse_channels"):
                params.append("--reverse_input_channels")
        else:
            params = []                                     # config가 하므로 블롭에 굽지 않는다
        print(f"config scale={pre['scale']}  ->  optimizer_params={params}")

        if args.blob:                                       # 이미 받은 블롭으로 재포장만
            blob = Path(args.blob)
        else:
            import blobconverter
            print("주의: blobconverter는 ONNX를 Luxonis 서버로 업로드합니다.")
            blob = Path(blobconverter.from_onnx(
                model=str(onnx), data_type="FP16", shaves=args.shaves,
                use_cache=False, output_dir=tmp, optimizer_params=params))
        print("블롭:", blob.name, f"{blob.stat().st_size/1e6:.1f} MB")

        meta["path"] = blob.name
        meta["precision"] = "float16"
        pack = Path(tmp) / "pack"
        pack.mkdir()
        shutil.copy(blob, pack / blob.name)
        (pack / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out, "w:xz") as t:
            t.add(pack / "config.json", "config.json")
            t.add(pack / blob.name, blob.name)
    print("NNArchive:", out)


# ---------------------------------------------------------------- inspect
def cmd_inspect(args):
    with tempfile.TemporaryDirectory() as tmp:
        _, cfg = _read_archive(args.archive, tmp)
        files = sorted(p.name for p in Path(tmp).iterdir())
    m = cfg["model"]
    inp = m["inputs"][0]
    head = m["heads"][0]
    hm = head["metadata"]
    print(f"파일       : {files}")
    print(f"모델 파일  : {m['metadata']['path']} ({m['metadata']['precision']})")
    print(f"입력 shape : {inp['shape']} {inp['layout']}")
    print(f"전처리     : mean={inp['preprocessing']['mean']} scale={inp['preprocessing']['scale']}")
    print(f"후처리     : parser={head['parser']} subtype={hm.get('subtype')}")
    print(f"클래스     : {hm.get('n_classes')}  conf={hm.get('conf_threshold')} iou={hm.get('iou_threshold')}")


# ---------------------------------------------------------------- run
def cmd_run(args):
    import depthai as dai

    src = Path(args.model)
    model = dai.NNArchive(str(src)) if src.exists() else dai.NNModelDescription(args.model)

    device = dai.Device(dai.DeviceInfo(args.ip)) if args.ip else None
    pipeline = dai.Pipeline(device) if device else dai.Pipeline()

    with pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        nn = pipeline.create(dai.node.DetectionNetwork).build(cam, model)
        if args.conf is not None:
            nn.setConfidenceThreshold(args.conf)
        labels = nn.getClasses() or []
        # passthrough 큐를 만들지 않으면 장치가 연결을 끊는다 -> 항상 만들고 소비한다
        q_rgb = nn.passthrough.createOutputQueue()
        q_det = nn.out.createOutputQueue()
        pipeline.start()

        t0 = time.monotonic()
        warm_until = t0 + args.warmup
        end = warm_until + args.seconds if args.seconds else float("inf")
        frames, steady_t0, recent, counts = 0, None, deque(maxlen=60), Counter()
        size = None

        while pipeline.isRunning() and time.monotonic() < end:
            frame = q_rgb.get().getCvFrame()
            dets = q_det.get().detections
            now = time.monotonic()
            size = size or f"{frame.shape[1]}x{frame.shape[0]}"
            if now >= warm_until:                           # 워밍업(부팅) 구간은 버린다
                steady_t0 = steady_t0 or now
                frames += 1
                recent.append(now)
                counts.update(labels[d.label] if d.label < len(labels) else d.label
                              for d in dets)
            if args.display:
                import cv2
                h, w = frame.shape[:2]
                for d in dets:
                    p1, p2 = (int(d.xmin*w), int(d.ymin*h)), (int(d.xmax*w), int(d.ymax*h))
                    cv2.rectangle(frame, p1, p2, (255, 0, 0), 2)
                    name = labels[d.label] if d.label < len(labels) else d.label
                    cv2.putText(frame, f"{name} {int(d.confidence*100)}%", (p1[0]+6, p1[1]+18),
                                cv2.FONT_HERSHEY_TRIPLEX, 0.45, (255, 0, 0))
                cv2.imshow("edge", frame)
                if cv2.waitKey(1) == ord("q"):
                    break

    elapsed = (recent[-1] - steady_t0) if steady_t0 and len(recent) > 1 else 0
    print(f"실제 입력  : {size}")
    if elapsed:
        print(f"FPS        : {(frames-1)/elapsed:.2f}  ({frames}프레임 / {elapsed:.1f}s, 워밍업 {args.warmup}s 제외)")
    total = sum(counts.values())
    print(f"검출 수    : {total}  " + ", ".join(f"{k} {v}" for k, v in counts.most_common(5)))
    if frames and total == 0:
        print("경고: 검출 0개. --conf 0.05로 재확인하고, 그래도 0이면 전처리 중복(블롭+config)을 의심할 것.")


# ----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export", help=".pt -> NNArchive(ONNX)")
    p.add_argument("pt")
    p.add_argument("--imgsz", default="512 288", help='"가로 세로"')
    p.add_argument("--encoding", default="rgb", choices=["rgb", "bgr"])
    p.add_argument("--out", default="work")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("convert", help="NNArchive(ONNX) -> NNArchive(blob)")
    p.add_argument("archive")
    p.add_argument("--out", required=True)
    p.add_argument("--shaves", type=int, default=6)
    p.add_argument("--blob", help="이미 변환된 블롭으로 재포장만 (업로드 없음)")
    p.set_defaults(fn=cmd_convert)

    p = sub.add_parser("inspect", help="NNArchive 내용 확인")
    p.add_argument("archive")
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("run", help="OAK-D에서 실행")
    p.add_argument("model", help="NNArchive 경로 또는 모델 주 이름")
    p.add_argument("--ip", help="예: 169.254.1.222 (자동 탐색은 부팅 중 실패함)")
    p.add_argument("--seconds", type=float, default=10.0, help="0이면 q 누를 때까지")
    p.add_argument("--warmup", type=float, default=3.0)
    p.add_argument("--conf", type=float)
    p.add_argument("--display", action="store_true")
    p.set_defaults(fn=cmd_run)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
