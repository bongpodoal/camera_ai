#!/usr/bin/env python3
import argparse
import csv
import statistics
import time
from pathlib import Path

import cv2
import depthai as dai

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "yolov6n": lambda: dai.NNModelDescription("yolov6-nano"),
    "yolov8n": lambda: dai.NNArchive(str(ROOT / "05_nnarchive/yolov8n/yolov8n-416x416.tar.xz")),
    "traffic_light": lambda: dai.NNArchive(str(ROOT / "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz")),
    "traffic_light_11n": lambda: dai.NNArchive(str(ROOT / "traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz")),
}

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
parser.add_argument("--fps", type=float, default=5, help="카메라 FPS (기본 5)")
parser.add_argument("--duration", type=float, default=300, help="측정 시간(초, 기본 300 = 5분)")
parser.add_argument("--no-latest", action="store_true", help="최신화 큐 끄기 (비교용, 기본은 켬)")
parser.add_argument("--show", action="store_true", help="화면 창 띄우기 (기본은 끔)")
parser.add_argument("--out-dir", required=True)
args = parser.parse_args()
latest = not args.no_latest

device = dai.Device(dai.DeviceInfo(args.ip))
with dai.Pipeline(device) as pipeline:
    camera = pipeline.create(dai.node.Camera).build()
    network = pipeline.create(dai.node.DetectionNetwork).build(camera, MODELS[args.model](), fps=args.fps)
    if latest:
        network.input.setMaxSize(1)
        network.input.setBlocking(False)
    script = pipeline.create(dai.node.Script)
    script.setScript(SCRIPT)
    network.out.link(script.inputs["det"])

    frame_queue = network.passthrough.createOutputQueue()
    det_queue = network.out.createOutputQueue()
    edge_queue = script.outputs["edge"].createOutputQueue()

    pipeline.start()
    edge_by_seq = {}
    rows = []
    start = time.monotonic()
    while pipeline.isRunning() and time.monotonic() - start < args.duration:
        frame_msg = frame_queue.get()
        det = det_queue.get()
        total_ms = (dai.Clock.now() - det.getTimestamp()).total_seconds() * 1000
        host_t = time.monotonic() - start

        for buf in edge_queue.tryGetAll():
            edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
        rows.append([det.getSequenceNum(), round(host_t, 4),
                     det.getTimestampDevice().total_seconds(), round(total_ms, 2), len(det.detections)])

        if args.show:
            frame = frame_msg.getCvFrame()
            h, w = frame.shape[:2]
            for d in det.detections:
                cv2.rectangle(frame, (int(d.xmin * w), int(d.ymin * h)), (int(d.xmax * w), int(d.ymax * h)), (255, 0, 0), 2)
            cv2.imshow(args.model, frame)
            cv2.waitKey(1)

    time.sleep(0.3)
    for buf in edge_queue.tryGetAll():
        edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
if args.show:
    cv2.destroyAllWindows()

setting = f"fps{args.fps:g}_{'latest' if latest else 'default'}"
out_dir = Path(args.out_dir).expanduser()
out_dir.mkdir(parents=True, exist_ok=True)
frames_csv = out_dir / "frames.csv"
new = not frames_csv.exists()
times = [r[2] for r in rows]
edges, pcs, totals, fps_list = [], [], [], []
with open(frames_csv, "a", newline="") as f:
    w = csv.writer(f)
    if new:
        w.writerow(["model", "setting", "seq", "host_time_s", "fps", "edge_latency_ms", "pc_latency_ms", "total_latency_ms", "n_objects"])
    for i, (seq, host_t, dev_t, total, n) in enumerate(rows):
        window = [t for t in times[:i + 1] if dev_t - t < 1.0]
        fps = round((len(window) - 1) / (dev_t - window[0]), 2) if len(window) > 1 else ""
        edge = edge_by_seq.get(seq)
        pc = round(total - edge, 2) if edge is not None else ""
        w.writerow([args.model, setting, seq, host_t, fps, edge if edge is not None else "", pc, total, n])
        if i > 0:
            totals.append(total)
            if edge is not None:
                edges.append(edge)
                pcs.append(pc)

def med(v):
    return round(statistics.median(v), 1) if v else ""

def p95(v):
    return round(sorted(v)[int(len(v) * 0.95) - 1], 1) if len(v) >= 20 else ""

seqs = [r[0] for r in rows]
dropped = (seqs[-1] - seqs[0] + 1) - len(seqs) if len(seqs) > 1 else 0
fps_avg = round((len(times) - 1) / (times[-1] - times[0]), 2) if len(times) > 1 else ""
summary_csv = out_dir / "summary.csv"
new = not summary_csv.exists()
with open(summary_csv, "a", newline="") as f:
    w = csv.writer(f)
    if new:
        w.writerow(["model", "camera_fps", "latest_queue", "frames", "dropped", "fps_avg",
                    "edge_ms_median", "edge_ms_p95", "pc_ms_median", "pc_ms_p95", "total_ms_median", "total_ms_p95"])
    w.writerow([args.model, args.fps, latest, len(rows), dropped, fps_avg,
                med(edges), p95(edges), med(pcs), p95(pcs), med(totals), p95(totals)])

print(f"{args.model} [{setting}]: {len(rows)} 프레임, 버림 {dropped}, FPS {fps_avg}, "
      f"엣지 {med(edges)} ms / PC {med(pcs)} ms / 총 {med(totals)} ms → {out_dir}")
