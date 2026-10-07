#!/usr/bin/env python3
"""사진을 OAK-D 칩에 직접 넣어 칩이 낸 검출을 예측 CSV 로 저장한다 (카메라 센서를 거치지 않음, 카메라 PC 에서 실행).

흐름: PC 가 이미지를 읽어 모델 입력 크기로 맞춘 뒤 → 칩의 신경망 입력 큐로 보내고 → 칩이 계산·디코딩(NMS 포함)한 검출을 받는다.
      카메라 영상 경로가 아니라 "같은 사진을 3모델에 똑같이 넣는" 공정한 비교용이다. 깊이 노드는 쓰지 않으므로 기존 8 SHAVE NNArchive 를 그대로 쓴다.

예) python3 chip_infer.py --model yolov6n --images ~/camera_eval_data/images/val --out out/yolov6n_chip.csv
    python3 chip_infer.py --model traffic_light --images ... --out out/traffic_light_chip.csv
    python3 chip_infer.py --model traffic_light_v8n --archive <경로>.tar.xz --images ... --out ...
주의: 이 스크립트는 맥에서 작성했고 아직 실카메라로 실행해 보지 않았다 (depthai 3.x 의 호스트 입력 큐 API 에 의존).
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = {      # can_canoe/can_demo.py 와 같은 모델 (yolov6n 은 공식 모델 이름)
    "yolov8n": "05_nnarchive/yolov8n/yolov8n-416x416.tar.xz",
    "traffic_light": "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz",
    "traffic_light_11n": "traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz",
    "traffic_light_v8n": "traffic_light/05_nnarchive/traffic_light_v8n-416x416.tar.xz",
}


def preprocess(img, w, h, mode):
    """원본 이미지를 모델 입력 크기 (w, h) 로 맞춘다. 반환: 입력 영상, 되돌리기 정보 (scale_x, scale_y, pad_x, pad_y)
    letterbox = 비율을 유지하고 남는 곳을 회색(114)으로 채움 (학습 때와 같은 방식), stretch = 비율 무시하고 늘려 맞춤."""
    oh, ow = img.shape[:2]
    if mode == "stretch":
        return cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR), (w / ow, h / oh, 0, 0)
    r = min(w / ow, h / oh)
    nw, nh = round(ow * r), round(oh * r)
    px, py = (w - nw) // 2, (h - nh) // 2
    canvas = np.full((h, w, 3), 114, np.uint8)
    canvas[py:py + nh, px:px + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, (r, r, px, py)


def to_original(box, w, h, ow, oh, back):
    """칩이 낸 정규화 박스(모델 입력 기준) → 원본 이미지 기준 정규화 박스."""
    sx, sy, px, py = back
    x1, y1, x2, y2 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    x1, x2 = (x1 - px) / sx / ow, (x2 - px) / sx / ow
    y1, y2 = (y1 - py) / sy / oh, (y2 - py) / sy / oh
    return [min(max(v, 0.0), 1.0) for v in (x1, y1, x2, y2)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, choices=["yolov6n", *ARCHIVES])
    ap.add_argument("--archive", help="NNArchive 경로 직접 지정")
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ip", default="169.254.1.222")
    ap.add_argument("--resize", choices=("letterbox", "stretch"), default="letterbox")
    ap.add_argument("--conf", type=float, default=0.05, help="칩의 신뢰도 문턱값을 낮춰 모아 둔다 (평가에서 운영 문턱값으로 거름)")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 이 장수만 (확인용)")
    a = ap.parse_args(argv)

    import depthai as dai
    if a.model == "yolov6n":
        archive = dai.NNArchive(dai.getModelFromZoo(dai.NNModelDescription("yolov6-nano")))
    else:
        archive = dai.NNArchive(a.archive or str(ROOT / ARCHIVES[a.model]))
    w, h = archive.getInputWidth(), archive.getInputHeight()
    files = sorted(p for p in Path(a.images).expanduser().glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if a.limit:
        files = files[:a.limit]
    print(f"모델 {a.model}: 입력 {w}×{h}, 이미지 {len(files)}장, 방식 {a.resize}, 칩 문턱값 {a.conf}")

    device = dai.Device(dai.DeviceInfo(a.ip))
    rows, t0 = [], time.time()
    with dai.Pipeline(device) as pipeline:
        net = pipeline.create(dai.node.DetectionNetwork)      # 호스트가 이미지를 넣는 검출망 (카메라 노드 없음)
        net.setNNArchive(archive)
        net.setConfidenceThreshold(a.conf)                    # 평가용: 낮은 점수까지 받아 두고 나중에 거른다
        in_q = net.input.createInputQueue()                   # PC → 칩 입력 통로
        out_q = net.out.createOutputQueue()                   # 칩 → PC 검출 결과
        labels = net.getClasses() if hasattr(net, "getClasses") else None
        pipeline.start()
        for n, p in enumerate(files, 1):
            img = cv2.imread(str(p))
            if img is None:
                print(f"읽기 실패: {p.name}")
                continue
            oh, ow = img.shape[:2]
            frame, back = preprocess(img, w, h, a.resize)
            msg = dai.ImgFrame()
            msg.setCvFrame(frame, dai.ImgFrame.Type.BGR888p)  # 칩이 받는 형식(채널 분리 BGR)으로 변환해 담기
            in_q.send(msg)
            det = out_q.get()                                 # 이 이미지의 검출 (없으면 빈 목록)
            for d in det.detections:
                name = labels[d.label] if labels and d.label < len(labels) else str(d.label)
                box = to_original((d.xmin, d.ymin, d.xmax, d.ymax), w, h, ow, oh, back)
                rows.append([a.model, f"chip_{a.resize}", p.stem, name, round(d.confidence, 4), *[round(v, 5) for v in box]])
            if n % 50 == 0 or n == len(files):
                print(f"  {n}/{len(files)}장 처리 ({time.time() - t0:.0f}s), 예측 {len(rows)}개", flush=True)
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["model", "source", "image", "cls", "conf", "x1", "y1", "x2", "y2"])
        wr.writerows(rows)
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
