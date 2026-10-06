#!/usr/bin/env python3
"""OAK-D 검출 결과를 CAN 으로 CANoe 에 보내고, 이 PC 쪽 기록(frames.csv)을 남긴다.

흐름
    OAK-D --이더넷--> 이 프로그램 --CAN--> CANoe (받은 순간의 시각을 로그에 찍음 = 시간축)
    --raw on  : 원본 영상(AI 입력 프레임)도 이더넷으로 받아 박스를 그리고 1초에 1장 저장 (후처리 확인용)
    --raw off : 원본 영상은 칩 안에서 버린다 (이더넷으로 안 나옴). 결과(박스)만 받는다.

시간축은 CANoe 로그의 시각 하나다. 이 프로그램은 시각을 CAN 에 싣지 않고, 자기 기록에
    t_send_s (PC 시계로 보낸 시각) · dev_t_s (카메라 시계로 찍은 시각)
만 남긴다. 둘이 CANoe 시계에서 얼마나 벌어지는지는 analyze.py 가 로그와 합쳐서 잰다.

보내는 메시지 (oakd_canoe.dbc): FRAME_STATUS 프레임마다 · DET_BOX 검출마다 · PERF 1초마다

예) python3 can_demo.py --model yolov6n --raw on --interface socketcan --channel can0 --duration 300 --out-dir runs/1_yolov6n_on
    python3 can_demo.py --fake --interface virtual --channel t --duration 20 --out-dir /tmp/x   (카메라·CANoe 없이)
"""
import argparse
import csv
import random
import statistics
import threading
import time
from collections import deque
from pathlib import Path

import can

from can_msgs import BITS_PER_FRAME, MODEL_IDS, det_box, frame_status, open_bus, perf, set_fd_frames

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {      # latency_latest.py 와 같은 모델 (yolov6n 은 공식 예제 이름)
    "yolov8n": "05_nnarchive/yolov8n/yolov8n-416x416.tar.xz",
    "traffic_light": "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz",
    "traffic_light_11n": "traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz",
}
# 칩 위 코드 ① 엣지 지연 재기 (칩 시계끼리 뺀다. getTimestamp() 는 펌웨어 크래시라 쓰지 않는다)
EDGE_SCRIPT = """
while True:
    det = node.inputs['det'].get()
    edge = Clock.now() - det.getTimestampDevice()
    data = str(round(edge.total_seconds() * 1000, 3)).encode()
    buf = Buffer(len(data))
    buf.setData(data)
    buf.setSequenceNum(det.getSequenceNum())
    node.outputs['edge'].send(buf)
"""
# 칩 위 코드 ② --raw off 일 때 원본 프레임을 받아서 그냥 버린다 (안 받으면 장치가 연결을 끊는다)
DROP_SCRIPT = """
while True:
    node.inputs['x'].get()
"""


# ---------------------------------------------------------------- 카메라 입력
class OakSource:
    """실제 OAK-D. 프레임마다 dict 하나를 내준다."""

    def __init__(self, args):
        self.args, self.edge_by_seq, self.edge_queue = args, {}, None

    def wait_edge(self, seq, timeout=0.25):
        """이 프레임의 칩 지연값이 올 때까지 최대 timeout 초 기다린다."""
        end = time.monotonic() + timeout
        while seq not in self.edge_by_seq and self.edge_queue is not None and time.monotonic() < end:
            for buf in self.edge_queue.tryGetAll():
                self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
            time.sleep(0.01)

    def frames(self, stop):
        import cv2
        import depthai as dai
        a = self.args
        if a.model == "yolov6n":
            model = dai.NNModelDescription("yolov6-nano")
        else:
            model = dai.NNArchive(a.archive or str(ROOT / ARCHIVES[a.model]))
        device = dai.Device(dai.DeviceInfo(a.ip))
        with dai.Pipeline(device) as pipeline:
            camera = pipeline.create(dai.node.Camera).build()
            network = pipeline.create(dai.node.DetectionNetwork).build(camera, model, fps=a.fps)
            network.input.setMaxSize(1)           # 최신화 큐: AI 가 바쁘면 옛 프레임을 버린다
            network.input.setBlocking(False)
            print(f"설정: 카메라 {a.fps:g} fps 고정 · AI 입력 큐 크기 1 · 비차단(최신 프레임만) · 모델 {a.model} · raw {a.raw}")
            edge_script = pipeline.create(dai.node.Script)
            edge_script.setScript(EDGE_SCRIPT)
            network.out.link(edge_script.inputs["det"])
            det_queue = network.out.createOutputQueue()
            edge_queue = self.edge_queue = edge_script.outputs["edge"].createOutputQueue()
            frame_queue = None
            if a.raw == "on":
                frame_queue = network.passthrough.createOutputQueue()
            else:
                drop = pipeline.create(dai.node.Script)
                drop.setScript(DROP_SCRIPT)
                network.passthrough.link(drop.inputs["x"])
            pipeline.start()
            while pipeline.isRunning() and not stop.is_set():
                frame_msg = frame_queue.get() if frame_queue else None
                det = det_queue.get()
                t_pc = time.time()
                total_ms = (dai.Clock.now() - det.getTimestamp()).total_seconds() * 1000
                post_ms, raw_bytes, frame = 0.0, 0, None
                if frame_msg is not None:
                    t0 = time.perf_counter()
                    frame = frame_msg.getCvFrame()
                    raw_bytes = int(frame.nbytes)
                    h, w = frame.shape[:2]
                    for d in det.detections:     # 후처리: 원본 위에 박스와 라벨을 그린다
                        p0, p1 = (int(d.xmin * w), int(d.ymin * h)), (int(d.xmax * w), int(d.ymax * h))
                        cv2.rectangle(frame, p0, p1, (255, 0, 0), 2)
                        cv2.putText(frame, f"{d.label} {d.confidence:.2f}", (p0[0], max(p0[1] - 4, 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                    post_ms = (time.perf_counter() - t0) * 1000
                for buf in edge_queue.tryGetAll():
                    self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
                yield dict(seq=det.getSequenceNum(), dev_t=det.getTimestampDevice().total_seconds(),
                           t_pc=t_pc, total_ms=total_ms, post_ms=post_ms, raw_bytes=raw_bytes, frame=frame,
                           dets=[(d.label, d.confidence, d.xmin, d.ymin, d.xmax, d.ymax) for d in det.detections])
            time.sleep(0.3)
            for buf in edge_queue.tryGetAll():
                self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())


class FakeSource:
    """카메라 없이 흐름을 검증하는 가짜 입력. 카메라 시계를 일부러 --fake-ppm 만큼 빠르게 만든다."""

    def __init__(self, args):
        self.args, self.edge_by_seq = args, {}

    def wait_edge(self, seq, timeout=0.25):
        pass

    def frames(self, stop):
        a, t0, seq = self.args, time.monotonic(), 0
        raw_bytes = 512 * 288 * 3 if a.raw == "on" else 0
        while not stop.is_set():
            seq += 1
            true_t = time.monotonic() - t0
            edge = 100 + random.uniform(-5, 5)
            self.edge_by_seq[seq] = edge
            dets = [(random.randrange(4), random.uniform(0.4, 0.95), 0.4, 0.1, 0.44, 0.26)
                    for _ in range(random.randrange(0, 4))]
            yield dict(seq=seq, dev_t=1000 + true_t * (1 + a.fake_ppm * 1e-6), t_pc=time.time(),
                       total_ms=edge + 8, post_ms=2.0 if a.raw == "on" else 0.0, raw_bytes=raw_bytes,
                       frame=None, dets=dets)
            time.sleep(max(0, t0 + seq / a.fps - time.monotonic()))


# ---------------------------------------------------------------- 보조
def read_nic_bytes(nic):
    """리눅스에서 이더넷 카드가 받은 누적 바이트 (OAK-D 가 보낸 양). 없으면 None."""
    try:
        for line in open("/proc/net/dev"):
            if line.strip().startswith(nic + ":"):
                return int(line.split(":")[1].split()[0])
    except OSError:
        pass
    return None


def med(v, nd=2):
    return round(statistics.median(v), nd) if v else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=MODEL_IDS, default="yolov6n")
    ap.add_argument("--raw", choices=("on", "off"), default="off")
    ap.add_argument("--ip", default="169.254.1.222")
    ap.add_argument("--fps", type=float, default=5, help="카메라 FPS")
    ap.add_argument("--duration", type=float, default=300)
    ap.add_argument("--archive", help="NNArchive 경로 직접 지정 (T7 에만 있는 yolov8n 등)")
    ap.add_argument("--interface", default="socketcan", help="socketcan | vector | pcan | virtual ...")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--bitrate", type=int, default=500000, help="CAN 중재(기본) 속도")
    ap.add_argument("--fd", action="store_true", help="버스를 CAN FD 모드로 연다 (CANoe 채널 설정과 같아야 함)")
    ap.add_argument("--data-bitrate", type=int, default=2000000, help="--fd 일 때 데이터 구간 속도")
    ap.add_argument("--fd-frames", action="store_true", help="메시지를 CAN FD 프레임(BRS 켬)으로 보냄. 안 주면 클래식 프레임")
    ap.add_argument("--max-dets", type=int, default=8)
    ap.add_argument("--edge-wait", type=float, default=0.0,
                    help="칩 지연값(EdgeMs)이 늦게 온 프레임을 최대 이 시간(초) 기다렸다 보낸다. 기본 0 = 기다리지 않음 (기다리면 그 프레임 송신이 약 20 ms 늦어 간격 지터가 생김, 안 기다리면 늦은 프레임의 EdgeMs 는 0 = 값 없음)")
    ap.add_argument("--nic", default="", help="OAK-D 가 꽂힌 이더넷 이름(예: enp5s0). 있으면 실제 수신 바이트를 잰다")
    ap.add_argument("--save-every", type=float, default=1.0, help="--raw on 일 때 이미지 저장 간격(초)")
    ap.add_argument("--fake", action="store_true", help="카메라 없이 가짜 입력 (검증용)")
    ap.add_argument("--fake-ppm", type=float, default=0.0, help="--fake 일 때 카메라 시계를 이만큼(ppm) 빠르게")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out_dir).expanduser()
    (out / "images").mkdir(parents=True, exist_ok=True)
    kw = {} if a.interface == "virtual" else {"bitrate": a.bitrate}
    if a.fd and a.interface != "virtual":
        kw.update(fd=True, data_bitrate=a.data_bitrate)
    set_fd_frames(a.fd_frames)
    channel = int(a.channel) if a.channel.isdigit() else a.channel       # vector 는 채널 번호가 정수
    bus = open_bus(a.interface, channel, **kw)
    source = FakeSource(a) if a.fake else OakSource(a)
    stop = threading.Event()

    rows, can_tx, can_err, dropped = [], 0, 0, 0
    last_save, last_perf, nic_prev = 0.0, time.monotonic(), None
    recent = deque()                        # 최근 1초: (시각, seq, total_ms, post_ms, raw_bytes)
    tx_in_sec, fps_win, prev_seq = 0, deque(), None
    det_rows = []
    t_start = time.monotonic()
    t_first = None                # 첫 프레임 도착 시각: --duration 은 여기서부터 잰다 (카메라 시작 지연 제외)
    nic0 = nic_prev = read_nic_bytes(a.nic) if a.nic else None

    def send(m):
        nonlocal can_tx, can_err, tx_in_sec
        try:
            bus.send(m, timeout=0.05)
            can_tx += 1
            tx_in_sec += 1
        except can.CanError:
            can_err += 1

    try:
        for f in source.frames(stop):
            now = time.monotonic()
            if t_first is None:
                t_first = last_perf = now
                nic0 = nic_prev = read_nic_bytes(a.nic) if a.nic else None
            if now - t_first >= a.duration:
                break
            fps_win.append(f["dev_t"])
            while fps_win[0] < f["dev_t"] - 1.0:
                fps_win.popleft()
            fps = (len(fps_win) - 1) / (f["dev_t"] - fps_win[0]) if len(fps_win) > 1 else 0
            gap = f["seq"] - prev_seq - 1 if prev_seq is not None else 0
            dropped += max(gap, 0)
            prev_seq = f["seq"]
            source.wait_edge(f["seq"], a.edge_wait)      # 기본 0: 안 기다림 (송신 간격 지터 방지)
            edge = source.edge_by_seq.get(f["seq"], 0)      # 끝내 없으면 0 = 값 없음 (분석에서 제외)
            # CAN 송신: 프레임 요약 1개 + 검출 박스 (신뢰도 높은 순)
            f["t_send"] = time.time()
            send(frame_status(f["seq"], len(f["dets"]), fps, edge, min(max(gap, 0), 15), MODEL_IDS[a.model], a.raw == "on"))
            top = sorted(f["dets"], key=lambda d: -d[1])[:min(a.max_dets, 16)]
            for i, d in enumerate(top):
                send(det_box(f["seq"], i, *d))
            for d in f["dets"]:
                det_rows.append([f["seq"], *d])
            if f["frame"] is not None and now - last_save >= a.save_every:
                import cv2
                cv2.imwrite(str(out / "images" / f"{f['seq']:06d}.jpg"), f["frame"])
                last_save = now
            f["frame"] = None
            f["n_det"] = len(f["dets"])
            rows.append(f)
            recent.append((now, f["seq"], f["total_ms"], f["post_ms"], f["raw_bytes"]))
            # 1초마다 PERF (속도 비교용 요약)
            if now - last_perf >= 1.0:
                span = now - last_perf
                while recent and recent[0][0] < now - 1.0:
                    recent.popleft()
                pcs = [r[2] - source.edge_by_seq[r[1]] for r in recent if r[1] in source.edge_by_seq]
                nic_now = read_nic_bytes(a.nic) if a.nic else None
                eth = (nic_now - nic_prev) / span if nic_now is not None and nic_prev is not None \
                    else sum(r[4] for r in recent) / span
                nic_prev = nic_now
                send(perf(med(pcs) or 0, med([r[3] for r in recent]) or 0, eth / 1000,
                          100 * tx_in_sec / span * BITS_PER_FRAME / a.bitrate, dropped))
                tx_in_sec, last_perf = 0, now
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        t_end = time.monotonic()
        dur = max(t_end - (t_first if t_first is not None else t_start), 1e-6)
        startup_s = round((t_first if t_first is not None else t_end) - t_start, 1)
        nic1 = read_nic_bytes(a.nic) if a.nic else None
        time.sleep(0.3)
        bus.shutdown()

    # ---- 기록 저장 ----
    with open(out / "frames.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "raw", "seq", "t_send_s", "dev_t_s", "edge_ms", "pc_ms", "post_ms", "raw_bytes", "n_objects"])
        for r in rows:
            edge = source.edge_by_seq.get(r["seq"])
            w.writerow([a.model, a.raw, r["seq"], f"{r['t_send']:.6f}", f"{r['dev_t']:.6f}",
                        edge if edge is not None else "",
                        round(r["total_ms"] - edge, 2) if edge is not None else "",
                        round(r["post_ms"], 2), r["raw_bytes"], r["n_det"]])
    with open(out / "detections.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seq", "label", "confidence", "xmin", "ymin", "xmax", "ymax"])
        w.writerows(det_rows)

    edges = [source.edge_by_seq[r["seq"]] for r in rows if r["seq"] in source.edge_by_seq]
    pcs = [r["total_ms"] - source.edge_by_seq[r["seq"]] for r in rows if r["seq"] in source.edge_by_seq]
    eth = (nic1 - nic0) / dur if nic0 is not None and nic1 is not None else sum(r["raw_bytes"] for r in rows) / dur
    summary = dict(model=a.model, raw=a.raw, camera_fps=a.fps, seconds=round(dur, 1), startup_s=startup_s, frames=len(rows),
                   dropped=dropped, fps_avg=round(len(rows) / dur, 2), edge_ms=med(edges), pc_ms=med(pcs),
                   post_ms=med([r["post_ms"] for r in rows]), eth_MBps=round(eth / 1e6, 3),
                   eth_source="nic" if nic0 is not None else "raw_frames_only",
                   can_tx_frames=can_tx, can_tx_errors=can_err,
                   can_tx_load_pct=round(100 * can_tx / dur * BITS_PER_FRAME / a.bitrate, 2))
    sp = out / "summary.csv"
    new = not sp.exists()
    with open(sp, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary))
        if new:
            w.writeheader()
        w.writerow(summary)
    print(" ".join(f"{k}={v}" for k, v in summary.items()))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
