"""로거·검토 도구·CAN 브리지가 함께 쓰는 함수."""
import csv
from pathlib import Path

import cv2

COLORS = {"person": (0, 200, 255), "car": (255, 160, 0), "traffic light": (0, 255, 0),
          "stop sign": (0, 0, 255)}


def draw_detections(img, dets):
    """dets: detections.csv 형식 dict 목록. img에 직접 그린다."""
    h, w = img.shape[:2]
    for d in dets:
        name = d.get("label_name") or str(d.get("label"))
        color = COLORS.get(name, (255, 255, 255))
        p1 = (int(float(d["xmin"]) * w), int(float(d["ymin"]) * h))
        p2 = (int(float(d["xmax"]) * w), int(float(d["ymax"]) * h))
        cv2.rectangle(img, p1, p2, color, 1)
        text = f"{name} {float(d['confidence'])*100:.0f}%"
        if d.get("z_mm") not in (None, ""):
            text += f" {float(d['z_mm'])/1000:.1f}m"
        ty = p1[1] - 4 if p1[1] > 26 else max(p1[1], 14) + 12     # 위쪽 헤더에 가리지 않게
        cv2.putText(img, text, (p1[0] + 2, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
    return img


def draw_header(img, text):
    cv2.rectangle(img, (0, 0), (img.shape[1], 14), (0, 0, 0), -1)
    cv2.putText(img, text, (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
