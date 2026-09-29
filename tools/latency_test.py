#!/usr/bin/env python3
"""모델 하나를 칩에 올려 N초 동안 FPS와 지연(엣지 / PC / 총)을 프레임마다 CSV로 기록한다.

지연을 세 조각으로 나눈다 (모두 같은 촬영 시각에서 출발):
    엣지 지연 = 칩에서 AI 결과가 나온 시각 - 센서가 찍은 시각   (칩 위 Script 노드가 칩 시계로 잼)
    총 지연   = PC 가 결과를 손에 쥔 시각   - 센서가 찍은 시각   (PC 시계, 칩 시각을 PC 시계로 맞춘 값)
    PC 지연   = 총 지연 - 엣지 지연 (이더넷 전송 + PC 큐 대기 + PC 처리)

화면 표시(박스 그리기 + imshow)는 run_with_logging.py 와 같게 하고, 이미지 저장만 뺐다.
예) python3 latency_test.py --model traffic_light --duration 10 --out ~/latency_frames.csv
"""
import argparse
import csv
import time
from pathlib import Path

import cv2
import depthai as dai

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "yolov6n": lambda: dai.NNModelDescription("yolov6-nano"),                        # example/minimal_example
    "yolov8n": lambda: dai.NNArchive("/media/kwakjunyoung/T7/camera_ai/05_nnarchive/yolov8n/yolov8n-512x288.tar.xz"),
    "traffic_light": lambda: dai.NNArchive(str(ROOT / "traffic_light/05_nnarchive/traffic_light-512x288.tar.xz")),
}

# 칩(LEON CPU) 위에서 도는 코드. AI 결과가 나오는 즉시 칩 시계로 "지금 - 촬영 시각"을 재서 보낸다.
# 주의 (2026-09-29 실측): 칩 Script 안에서 getTimestamp()(PC 시계로 맞춘 값)를 부르면 펌웨어가 크래시한다.
#       칩 시계끼리(Clock.now(), getTimestampDevice()) 빼야 한다.
SCRIPT = """
while True:
    det = node.inputs['det'].get()
    edge = Clock.now() - det.getTimestampDevice()
    data = str(round(edge.total_seconds() * 1000, 3)).encode()
    buf = Buffer(len(data))
    buf.setData(data)
    buf.setSequenceNum(det.getSequenceNum())
    node.outputs['edge'].send(buf)
"""

parser = argparse.ArgumentParser()
parser.add_argument("--model", choices=MODELS, required=True)
parser.add_argument("--ip", default="169.254.1.222")
parser.add_argument("--duration", type=float, default=10)
parser.add_argument("--out", required=True)
args = parser.parse_args()

device = dai.Device(dai.DeviceInfo(args.ip))
with dai.Pipeline(device) as pipeline:
    camera = pipeline.create(dai.node.Camera).build()
    network = pipeline.create(dai.node.DetectionNetwork).build(camera, MODELS[args.model]())
    script = pipeline.create(dai.node.Script)
    script.setScript(SCRIPT)
    network.out.link(script.inputs["det"])

    frame_queue = network.passthrough.createOutputQueue()
    det_queue = network.out.createOutputQueue()
    edge_queue = script.outputs["edge"].createOutputQueue()

    pipeline.start()
    edge_by_seq = {}      # Script 결과는 따로 오므로 순번으로 짝을 맞춘다
    rows = []
    start = time.monotonic()
    while pipeline.isRunning() and time.monotonic() - start < args.duration:
        frame_msg = frame_queue.get()
        det = det_queue.get()
        total_ms = (dai.Clock.now() - det.getTimestamp()).total_seconds() * 1000   # PC 가 받은 순간
        host_t = time.monotonic() - start

        for buf in edge_queue.tryGetAll():
            edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
        rows.append([args.model, det.getSequenceNum(), round(host_t, 4),
                     det.getTimestampDevice().total_seconds(), round(total_ms, 2), len(det.detections)])

        frame = frame_msg.getCvFrame()
        h, w = frame.shape[:2]
        for d in det.detections:
            cv2.rectangle(frame, (int(d.xmin * w), int(d.ymin * h)), (int(d.xmax * w), int(d.ymax * h)), (255, 0, 0), 2)
        cv2.imshow(args.model, frame)
        cv2.waitKey(1)

    # 마지막 몇 개 Script 결과가 늦게 올 수 있어 잠깐 더 받는다
    time.sleep(0.3)
    for buf in edge_queue.tryGetAll():
        edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
cv2.destroyAllWindows()

# FPS = 칩 촬영 시각 간격으로 계산한 직전 1초 구간 처리 속도
out = Path(args.out).expanduser()
new = not out.exists()
with open(out, "a", newline="") as f:
    w = csv.writer(f)
    if new:
        w.writerow(["model", "seq", "host_time_s", "fps", "edge_latency_ms", "pc_latency_ms", "total_latency_ms", "n_objects"])
    times = [r[3] for r in rows]
    for i, (model, seq, host_t, dev_t, total, n) in enumerate(rows):
        window = [t for t in times[:i + 1] if dev_t - t < 1.0]
        fps = round((len(window) - 1) / (dev_t - window[0]), 2) if len(window) > 1 else ""
        edge = edge_by_seq.get(seq)
        pc = round(total - edge, 2) if edge is not None else ""
        w.writerow([model, seq, host_t, fps, edge if edge is not None else "", pc, total, n])
print(f"{args.model}: {len(rows)} 프레임 기록 → {out}")
