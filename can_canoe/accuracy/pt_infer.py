#!/usr/bin/env python3
"""PyTorch(.pt) 모델로 이미지 폴더를 추론해 예측 CSV 를 만든다 (맥에서 기준선·평가 코드 검증용).

예) python3 pt_infer.py --weights ~/github/camera_ai/traffic_light/01_pytorch_pt/traffic_light.pt --model traffic_light \
        --images ~/camera_eval_data/images/val --imgsz 960 --out out/traffic_light_pt960.csv
"""
import argparse
import csv
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--model", required=True, help="CSV 의 model 열 이름 (예: traffic_light)")
    ap.add_argument("--images", required=True)
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--conf", type=float, default=0.05, help="낮게 모아 두고 평가에서 운영 문턱값으로 거른다")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.weights)
    files = sorted(p for p in Path(a.images).expanduser().glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if a.limit:
        files = files[:a.limit]
    rows = []
    for k in range(0, len(files), 16):
        for r in model.predict([str(p) for p in files[k:k + 16]], imgsz=a.imgsz, conf=a.conf, iou=a.iou, verbose=False):
            stem = Path(r.path).stem
            for b, c, s in zip(r.boxes.xyxyn.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist()):
                rows.append([a.model, f"pytorch_imgsz{a.imgsz}", stem, r.names[int(c)], round(s, 4), *[round(v, 5) for v in b]])
    Path(a.out).expanduser().parent.mkdir(parents=True, exist_ok=True)
    with open(Path(a.out).expanduser(), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "source", "image", "cls", "conf", "x1", "y1", "x2", "y2"])
        w.writerows(rows)
    print(f"{len(files)}장 → 예측 {len(rows)}개 → {a.out}")


if __name__ == "__main__":
    main()
