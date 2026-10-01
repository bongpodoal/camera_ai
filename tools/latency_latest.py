#!/usr/bin/env python3
"""카메라 FPS를 낮추고 AI 입력 큐를 '최신 1장만' 으로 바꿔 지연(엣지 / PC / 총)과 FPS를 잰다.

latency_test.py 와 측정 방식은 같고, 바뀐 점은 셋이다.
    1) --fps     : 카메라가 1초에 찍는 장수 (기본 5). AI 처리 속도보다 낮으면 칩 안에 줄이 생기지 않는다.
    2) 최신화 큐 : AI 입력 큐 크기 1 · 비차단(non-blocking). AI 가 바쁜 동안 새 프레임이 오면 옛 것을 버린다.
    3) 화면 창 끔 : 기본은 창 없이 잰다. --show 를 주면 창을 띄운다.

지연 세 조각 (모두 같은 촬영 시각에서 출발):
    엣지 지연 = 칩에서 AI 결과가 나온 시각 - 센서가 찍은 시각   (칩 위 Script 노드가 칩 시계로 잼)
    총 지연   = PC 가 결과를 손에 쥔 시각   - 센서가 찍은 시각   (PC 시계, 칩 시각을 PC 시계로 맞춘 값)
    PC 지연   = 총 지연 - 엣지 지연 (이더넷 전송 + PC 큐 대기 + PC 처리)

예) python3 latency_latest.py --model traffic_light --fps 5 --duration 300 --out-dir latency_runs/test
결과: <out-dir>/frames.csv (프레임마다), <out-dir>/summary.csv (모델·설정마다 한 줄, 실행할 때마다 덧붙임)
"""
import argparse
import csv
import statistics
import time
from pathlib import Path

import cv2
import depthai as dai

ROOT = Path(__file__).resolve().parents[1]          # 이 파일이 있는 camera_ai 폴더 (T7 위치와 무관하게 찾음)
# 입력 크기 (2026-10-01): YOLOv6n 은 공식 예제 512×384 그대로, 나머지 둘은 416×416 으로 다시 변환한 것
MODELS = {
    "yolov6n": lambda: dai.NNModelDescription("yolov6-nano"),
    "yolov8n": lambda: dai.NNArchive(str(ROOT / "05_nnarchive/yolov8n/yolov8n-416x416.tar.xz")),
    "traffic_light": lambda: dai.NNArchive(str(ROOT / "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz")),
    # YOLO11n 재학습본 (00_train → ②~⑤ 416x416 traffic_light_11n 으로 만든 뒤 사용)
    "traffic_light_11n": lambda: dai.NNArchive(str(ROOT / "traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz")),
}

# 칩(LEON CPU) 위에서 도는 코드. AI 결과가 나오는 즉시 칩 시계로 "지금 - 촬영 시각"을 재서 보낸다.
# 주의 (2026-09-29 실측): Script 안에서 getTimestamp() 를 부르면 펌웨어 크래시. 칩 시계끼리 뺀다.
#       Buffer.setData() 는 bytes 만 받는다.
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
    # fps= : 카메라가 AI 입력용 영상을 이 속도로만 찍는다
    network = pipeline.create(dai.node.DetectionNetwork).build(camera, MODELS[args.model](), fps=args.fps)
    if latest:
        # 최신화 큐: 칸 1개, 가득 차면 기다리지 않고 옛 프레임을 버린다
        network.input.setMaxSize(1)
        network.input.setBlocking(False)
    script = pipeline.create(dai.node.Script)
    script.setScript(SCRIPT)
    network.out.link(script.inputs["det"])

    # passthrough 큐는 화면을 안 띄워도 만들고 읽는다 (안 만들면 장치가 연결을 끊음)
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
        rows.append([det.getSequenceNum(), round(host_t, 4),
                     det.getTimestampDevice().total_seconds(), round(total_ms, 2), len(det.detections)])

        if args.show:
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
if args.show:
    cv2.destroyAllWindows()

# ---- 프레임별 CSV ----
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
        # FPS = 칩 촬영 시각 기준 직전 1초 구간 처리 속도
        window = [t for t in times[:i + 1] if dev_t - t < 1.0]
        fps = round((len(window) - 1) / (dev_t - window[0]), 2) if len(window) > 1 else ""
        edge = edge_by_seq.get(seq)
        pc = round(total - edge, 2) if edge is not None else ""
        w.writerow([args.model, setting, seq, host_t, fps, edge if edge is not None else "", pc, total, n])
        if i > 0:                     # 첫 프레임은 시계 맞추는 중이라 요약에서 뺀다
            totals.append(total)
            if edge is not None:
                edges.append(edge)
                pcs.append(pc)

# ---- 요약 CSV ----
def med(v):
    return round(statistics.median(v), 1) if v else ""

def p95(v):
    return round(sorted(v)[int(len(v) * 0.95) - 1], 1) if len(v) >= 20 else ""

seqs = [r[0] for r in rows]
dropped = (seqs[-1] - seqs[0] + 1) - len(seqs) if len(seqs) > 1 else 0     # 순번이 건너뛴 수 = 버려진 프레임
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
