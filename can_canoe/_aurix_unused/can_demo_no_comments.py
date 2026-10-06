import argparse
import csv
import random
import statistics
import threading
import time
from collections import deque
from pathlib import Path

import can
import numpy as np

from aurix_can import (BITS_PER_FRAME, ID_ECHO, ID_SYNC, MODEL_IDS, Unwrap32, decode, det_box,
                       frame_status)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "yolov8n": "05_nnarchive/yolov8n/yolov8n-416x416.tar.xz",
    "traffic_light": "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz",
    "traffic_light_11n": "traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz",
}
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
DROP_SCRIPT = """
while True:
    node.inputs['x'].get()
"""

class OakSource:

    def __init__(self, args):
        self.args, self.edge_by_seq = args, {}

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
            network.input.setMaxSize(1)
            network.input.setBlocking(False)
            edge_script = pipeline.create(dai.node.Script)
            edge_script.setScript(EDGE_SCRIPT)
            network.out.link(edge_script.inputs["det"])
            det_queue = network.out.createOutputQueue()
            edge_queue = edge_script.outputs["edge"].createOutputQueue()
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
                    for d in det.detections:
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

    def __init__(self, args):
        self.args, self.edge_by_seq = args, {}

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

class CanRx(threading.Thread):

    def __init__(self, bus):
        super().__init__(daemon=True)
        self.bus, self.stop_flag, self.unwrap = bus, threading.Event(), Unwrap32()
        self.sync, self.echo, self.rx_count = [], {}, 0

    def run(self):
        while not self.stop_flag.is_set():
            m = self.bus.recv(timeout=0.1)
            if m is None:
                continue
            self.rx_count += 1
            if m.arbitration_id == ID_SYNC:
                self.sync.append((m.timestamp, self.unwrap(decode(m)[1]["TimeUs"])))
            elif m.arbitration_id == ID_ECHO:
                v = decode(m)[1]
                self.echo[int(v["Seq"])] = (m.timestamp, self.unwrap(v["RxTimeUs"]))

def read_nic_bytes(nic):
    try:
        for line in open("/proc/net/dev"):
            if line.strip().startswith(nic + ":"):
                return int(line.split(":")[1].split()[0])
    except OSError:
        pass
    return None

def slope_ppm(x_s, y_s):
    if len(x_s) < 3:
        return None
    return (float(np.polyfit(x_s, y_s, 1)[0]) - 1) * 1e6

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
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--max-dets", type=int, default=8)
    ap.add_argument("--nic", default="", help="OAK-D 가 꽂힌 이더넷 이름(예: enp5s0). 있으면 실제 수신 바이트를 잰다")
    ap.add_argument("--save-every", type=float, default=1.0, help="--raw on 일 때 이미지 저장 간격(초)")
    ap.add_argument("--fake", action="store_true", help="카메라 없이 가짜 입력 (검증용)")
    ap.add_argument("--fake-ppm", type=float, default=0.0, help="--fake 일 때 카메라 시계를 이만큼(ppm) 빠르게")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out_dir).expanduser()
    (out / "images").mkdir(parents=True, exist_ok=True)
    kw = {} if a.interface == "virtual" else {"bitrate": a.bitrate}
    bus = can.Bus(interface=a.interface, channel=a.channel, **kw)
    rx = CanRx(bus)
    rx.start()
    source = FakeSource(a) if a.fake else OakSource(a)
    stop = threading.Event()

    rows, can_tx, last_save = [], 0, 0.0
    fps_win, prev_seq = deque(), None
    nic0, t_start = read_nic_bytes(a.nic) if a.nic else None, time.monotonic()
    try:
        for f in source.frames(stop):
            if time.monotonic() - t_start >= a.duration:
                break
            fps_win.append(f["dev_t"])
            while fps_win[0] < f["dev_t"] - 1.0:
                fps_win.popleft()
            fps = (len(fps_win) - 1) / (f["dev_t"] - fps_win[0]) if len(fps_win) > 1 else 0
            gap = min(f["seq"] - prev_seq - 1, 15) if prev_seq is not None else 0
            prev_seq = f["seq"]
            edge = source.edge_by_seq.get(f["seq"], 0)
            f["t_send"] = time.time()
            bus.send(frame_status(f["seq"], len(f["dets"]), fps, edge, gap, MODEL_IDS[a.model], a.raw == "on"))
            top = sorted(f["dets"], key=lambda d: -d[1])[:min(a.max_dets, 16)]
            for i, d in enumerate(top):
                bus.send(det_box(f["seq"], i, *d))
            can_tx += 1 + len(top)
            if f["frame"] is not None and time.monotonic() - last_save >= a.save_every:
                import cv2
                cv2.imwrite(str(out / "images" / f"{f['seq']:06d}.jpg"), f["frame"])
                last_save = time.monotonic()
            f["frame"] = None
            f["n_det"], f["fps"] = len(f["dets"]), fps
            rows.append(f)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        dur = time.monotonic() - t_start
        nic1 = read_nic_bytes(a.nic) if a.nic else None
        time.sleep(0.5)
        rx.stop_flag.set()
        rx.join(timeout=1)
        bus.shutdown()

    ok = [r for r in rows if r["seq"] % 65536 in rx.echo]
    for r in rows:
        e = rx.echo.get(r["seq"] % 65536)
        r["pc_echo"], r["aurix_us"] = e if e else (None, None)
    if not ok:
        print("ECHO 를 하나도 못 받음 → AURIX(또는 aurix_sim.py) 가 켜져 있고 CAN 이 이어졌는지 확인")
        return 1
    a0, d0 = ok[0], ok[0]
    au0 = rx.echo[a0["seq"] % 65536][1]
    dev0 = d0["dev_t"]
    csv_path = out / "frames.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "raw", "seq", "t_axis_ms", "aurix_us", "interval_ms", "cam_minus_aurix_ms",
                    "edge_ms", "pc_ms", "post_ms", "echo_rtt_ms", "raw_bytes", "n_objects"])
        prev_us = None
        for r in rows:
            if r["aurix_us"] is None:
                continue
            t_axis = round((r["aurix_us"] - au0) / 1000)
            interval = round((r["aurix_us"] - prev_us) / 1000, 3) if prev_us is not None else ""
            prev_us = r["aurix_us"]
            edge = source.edge_by_seq.get(r["seq"])
            w.writerow([a.model, a.raw, r["seq"], t_axis, int(r["aurix_us"] - au0), interval,
                        round(((r["dev_t"] - dev0) - (r["aurix_us"] - au0) / 1e6) * 1000, 3),
                        edge if edge is not None else "", round(r["total_ms"] - edge, 2) if edge is not None else "",
                        round(r["post_ms"], 2), round((r["pc_echo"] - r["t_send"]) * 1000, 2),
                        r["raw_bytes"], r["n_det"]])

    au_s = np.array([r["aurix_us"] - au0 for r in ok]) / 1e6
    cam_ppm = slope_ppm(au_s, np.array([r["dev_t"] - dev0 for r in ok]))
    pc_ppm = slope_ppm(np.array([(u - rx.sync[0][1]) / 1e6 for _, u in rx.sync]),
                       np.array([t - rx.sync[0][0] for t, _ in rx.sync])) if rx.sync else None
    intervals = np.diff([r["aurix_us"] for r in ok]) / 1000
    edges = [source.edge_by_seq[r["seq"]] for r in rows if r["seq"] in source.edge_by_seq]
    pcs = [r["total_ms"] - source.edge_by_seq[r["seq"]] for r in rows if r["seq"] in source.edge_by_seq]
    rtts = [(r["pc_echo"] - r["t_send"]) * 1000 for r in ok]
    eth = (nic1 - nic0) / dur if nic0 is not None and nic1 is not None else \
        sum(r["raw_bytes"] for r in rows) / dur
    can_frames = can_tx + rx.rx_count
    summary = dict(model=a.model, raw=a.raw, camera_fps=a.fps, seconds=round(dur, 1), frames=len(rows),
                   echo_lost=len(rows) - len(ok), fps_avg=round(len(rows) / dur, 2),
                   edge_ms=med(edges), pc_ms=med(pcs), post_ms=med([r["post_ms"] for r in rows]),
                   echo_rtt_ms=med(rtts), interval_ms_median=med(list(intervals)),
                   interval_ms_std=round(float(np.std(intervals)), 2) if len(intervals) > 1 else "",
                   eth_MBps=round(eth / 1e6, 3), eth_source="nic" if a.nic and nic0 is not None else "raw_frames_only",
                   can_frames_per_s=round(can_frames / dur, 1),
                   can_load_pct=round(100 * can_frames / dur * BITS_PER_FRAME / a.bitrate, 2),
                   camera_drift_ppm=round(cam_ppm, 1) if cam_ppm is not None else "",
                   pc_drift_ppm=round(pc_ppm, 1) if pc_ppm is not None else "")
    sp = out / "summary.csv"
    new = not sp.exists()
    with open(sp, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary))
        if new:
            w.writeheader()
        w.writerow(summary)
    print(" ".join(f"{k}={v}" for k, v in summary.items()))
    print(f"→ {csv_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
