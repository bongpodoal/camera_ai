#!/usr/bin/env python3

import shutil
import sys
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

MODE = sys.argv[1] if len(sys.argv) > 1 else "train"
BASE_MODEL = sys.argv[2] if len(sys.argv) > 2 else "yolo11n.pt"
IMGSZ = int(sys.argv[3]) if len(sys.argv) > 3 else 960
NAME = sys.argv[4] if len(sys.argv) > 4 else "traffic_light_11n"

DATA_DIR = HERE / "datasets" / "traffic_light"
DATA_YAML = DATA_DIR / "data.yaml"
RUN_DIR = HERE / "runs"

def prepare_dataset():
    if not (DATA_DIR / "labels" / "val").exists():
        from huggingface_hub import snapshot_download
        print("데이터셋 내려받는 중 (약 1.1 GB) ...")
        snapshot_download("lincolnn2026/traffic_light_dataset", repo_type="dataset",
                          allow_patterns=["images/*", "labels/*"], local_dir=str(DATA_DIR))
    DATA_YAML.write_text(f"path: {DATA_DIR}\ntrain: images/train\nval: images/val\n"
                         "names: ['red', 'yellow', 'green', 'off']\n")
    for split in ("train", "val"):
        print(f"  {split}: 이미지 {len(list((DATA_DIR / 'images' / split).glob('*.jpg')))}장")

def train():
    model = YOLO(BASE_MODEL)
    model.train(
        data=str(DATA_YAML), epochs=60, imgsz=IMGSZ,
        batch=16,
        patience=15,
        device=0, project=str(RUN_DIR), name=NAME, exist_ok=True,
        cache=False, workers=8,
        fliplr=0.0,
        flipud=0.0,
        degrees=0.0,
        hsv_h=0.005,
        hsv_s=0.5, hsv_v=0.5,
        scale=0.5, mosaic=1.0,
        close_mosaic=10,
    )

def resume():
    YOLO(str(RUN_DIR / NAME / "weights" / "last.pt")).train(resume=True)

def validate():
    best = RUN_DIR / NAME / "weights" / "best.pt"
    pt_copy = ROOT / "01_pytorch_pt" / f"{NAME}.pt"
    if best.exists() and not pt_copy.exists():
        shutil.copy2(best, pt_copy)
        print(f"복사: {pt_copy}")
    model = YOLO(str(pt_copy if pt_copy.exists() else best))
    for size in (IMGSZ, 416):
        metrics = model.val(data=str(DATA_YAML), imgsz=size, device=0, plots=False, verbose=False)
        print(f"\n=== {NAME} · 평가 크기 {size} ===")
        for i, name in model.names.items():
            p, r, ap50, ap = metrics.class_result(i)
            print(f"  {name:8s} precision={p:.3f} recall={r:.3f} mAP50={ap50:.3f} mAP50-95={ap:.3f}")
        print(f"  전체 mAP50={metrics.box.map50:.3f}  mAP50-95={metrics.box.map:.3f}")

if __name__ == "__main__":
    prepare_dataset()
    if MODE == "train":
        train()
    elif MODE == "resume":
        resume()
    validate()
