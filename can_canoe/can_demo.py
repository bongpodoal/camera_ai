#!/usr/bin/env python3
"""OAK-D 검출 결과를 CAN 으로 CANoe 에 보내고, 이 PC 쪽 기록(frames.csv)을 남긴다.

흐름
    OAK-D --이더넷--> 이 프로그램 --CAN--> CANoe (받은 순간의 시각을 로그에 찍음 = 시간축)
    --raw on  : 카메라로 받을 수 있는 **모든 데이터**를 받는다 (교수님 정의). 깊이(스테레오)로 검출마다 X/Y/Z·ROI,
                프레임 메타(노출·ISO·색온도·렌즈·크기·시각), 칩 온도·CPU·메모리(1초), 보정값·장치 정보(10초),
                처리된 RGB 프레임과 깊이 프레임(이더넷, CAN 불가 → 크기만 셈). 숫자·문자열은 전부 CAN 으로 보낸다.
    --raw off : 검출 결과(클래스·신뢰도·박스)만 받는다. 깊이·텔레메트리·영상은 받지 않고 칩 안에서 버린다.

시간축은 CANoe 로그의 시각 하나다. 이 프로그램은 시각을 CAN 에 싣지 않고, 자기 기록에
    t_send_s (PC 시계로 보낸 시각) · dev_t_s (카메라 시계로 찍은 시각)
만 남긴다. 둘이 CANoe 시계에서 얼마나 벌어지는지는 analyze.py 가 로그와 합쳐서 잰다.

보내는 메시지 (oakd_canoe.dbc): FRAME_STATUS 프레임마다 · DET_BOX 검출마다 · PERF 1초마다
    --raw on 추가: DET_POS·DET_ROI 검출마다 · FRAME_META_A/B/C·FRAME_TIME_DEV/HOST 프레임마다 · DEV_TEMP·DEV_MEM_A/B/C 1초 · CALIB_A/B/C·DEV_INFO 10초

예) python3 can_demo.py --model yolov6n --raw on --interface socketcan --channel can0 --duration 300 --out-dir runs/1_yolov6n_on
    python3 can_demo.py --fake --interface virtual --channel t --duration 20 --out-dir /tmp/x   (카메라·CANoe 없이)
"""
import argparse
import csv
import json
import random
import statistics
import threading
import time
from collections import deque
from pathlib import Path

import can

import oak_full
from can_msgs import BITS_PER_FRAME, MODEL_IDS, det_box, frame_status, open_bus, perf, set_fd_frames

ROOT = Path(__file__).resolve().parents[1]
DET_EXT_COLS = ('x_mm', 'y_mm', 'z_mm', 'roi_x', 'roi_y', 'roi_w', 'roi_h')
ARCHIVES = {      # latency_latest.py 와 같은 모델 (yolov6n 은 공식 예제 이름)
    "yolov8n": "05_nnarchive/yolov8n/yolov8n-416x416.tar.xz",
    "traffic_light": "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz",
    "traffic_light_11n": "traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz",
    "traffic_light_v8n": "traffic_light/05_nnarchive/traffic_light_v8n-416x416.tar.xz",
}
# 깊이(스테레오)가 칩 SHAVE 를 써서 신경망에는 7개만 남는다 → Raw 켬은 6 SHAVE 로 컴파일한 모델을 쓴다.
# (8 SHAVE 로 굳은 blob 은 "Blob compiled for 8 shaves, but only 7 are available" 로 시작하지 못함)
FULL_SHAVES = 6
ARCHIVES_FULL = {
    "traffic_light_v8n": "traffic_light/05_nnarchive/traffic_light_v8n-416x416-6shave.tar.xz",
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
        self.args, self.edge_by_seq, self.edge_queue, self.session = args, {}, None, None

    def wait_edge(self, seq, timeout=0.25):
        """이 프레임의 칩 지연값이 올 때까지 최대 timeout 초 기다린다."""
        end = time.monotonic() + timeout
        while seq not in self.edge_by_seq and self.edge_queue is not None and time.monotonic() < end:
            for buf in self.edge_queue.tryGetAll():
                self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
            time.sleep(0.01)

    def _model(self, dai):
        a = self.args
        full = a.raw == "on"
        if a.model == "yolov6n":
            if full:      # 공식 superblob 에서 SHAVE 수를 골라 쓰려고 아카이브로 받는다
                desc = dai.NNModelDescription("yolov6-nano")
                desc.platform = "RVC2"
                return dai.NNArchive(dai.getModelFromZoo(desc))
            return dai.NNModelDescription("yolov6-nano")
        if full and not a.archive and a.model in ARCHIVES_FULL:
            return dai.NNArchive(str(ROOT / ARCHIVES_FULL[a.model]))
        return dai.NNArchive(a.archive or str(ROOT / ARCHIVES[a.model]))

    def frames(self, stop):
        import cv2
        import depthai as dai
        a = self.args
        model = self._model(dai)
        device = dai.Device(dai.DeviceInfo(a.ip))
        full = a.raw == "on"
        with dai.Pipeline(device) as pipeline:
            if full:
                # 모든 데이터: 스테레오 깊이 + 깊이 포함 검출망 (예제 07_host_output/edge_logger.py 와 같은 구성)
                camera = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
                depth = pipeline.create(dai.node.Depth).build(dai.node.Depth.Algorithm.AUTO, a.fps)
                network = pipeline.create(dai.node.SpatialDetectionNetwork).build(camera, depth, model, fps=a.fps)
                if isinstance(model, dai.NNArchive) and model.getModelType() == dai.ModelType.SUPERBLOB:
                    network.setNNArchive(model, FULL_SHAVES)
                network.setDepthLowerThreshold(100)
                network.setDepthUpperThreshold(20000)
                network.spatialLocationCalculator.initialConfig.setSegmentationPassthrough(False)
            else:
                camera = pipeline.create(dai.node.Camera).build()
                network = pipeline.create(dai.node.DetectionNetwork).build(camera, model, fps=a.fps)
            try:
                network.input.setMaxSize(1)       # 최신화 큐: AI 가 바쁘면 옛 프레임을 버린다
                network.input.setBlocking(False)
            except AttributeError:
                print("경고: 이 노드에는 input 큐 설정이 없어 최신화 큐를 적용하지 못함")
            print(f"설정: 카메라 {a.fps:g} fps 고정 · AI 입력 큐 크기 1 · 비차단(최신 프레임만) · 모델 {a.model} · raw {a.raw}"
                  f"{' (깊이·텔레메트리·영상 모두 받음)' if full else ''}")
            edge_script = pipeline.create(dai.node.Script)
            edge_script.setScript(EDGE_SCRIPT)
            network.out.link(edge_script.inputs["det"])
            det_queue = network.out.createOutputQueue()
            edge_queue = self.edge_queue = edge_script.outputs["edge"].createOutputQueue()
            frame_queue = depth_queue = sys_queue = None
            if full:
                frame_queue = network.passthrough.createOutputQueue()
                depth_queue = network.passthroughDepth.createOutputQueue(maxSize=2, blocking=False)
                syslog = pipeline.create(dai.node.SystemLogger)
                syslog.setRate(1.0)
                sys_queue = syslog.out.createOutputQueue(maxSize=8, blocking=False)
            else:
                drop = pipeline.create(dai.node.Script)
                drop.setScript(DROP_SCRIPT)
                network.passthrough.link(drop.inputs["x"])
            pipeline.start()
            while pipeline.isRunning() and not stop.is_set():
                frame_msg = frame_queue.get() if frame_queue else None
                det = det_queue.get()
                t_pc = time.time()
                now_dai = dai.Clock.now()
                total_ms = (now_dai - det.getTimestamp()).total_seconds() * 1000
                post_ms, raw_bytes, frame, extra = 0.0, 0, None, {}
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
                if full:
                    depth_msgs = depth_queue.tryGetAll()
                    depth_bytes = sum(int(m.getData().nbytes) for m in depth_msgs)
                    if self.session is None:
                        self.session = oak_full.session_info(device, dai, network, a.model, frame.shape[1], frame.shape[0])
                    extra = dict(meta=oak_full.frame_meta(frame_msg, det, now_dai, now_dai),
                                 ext=[oak_full.det_ext(d) for d in det.detections],
                                 tele=[oak_full.telemetry_row(x) for x in sys_queue.tryGetAll()],
                                 depth_bytes=depth_bytes, depth_frame=depth_msgs[-1].getFrame() if depth_msgs else None)
                    raw_bytes += depth_bytes
                for buf in edge_queue.tryGetAll():
                    self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
                yield dict(seq=det.getSequenceNum(), dev_t=det.getTimestampDevice().total_seconds(),
                           t_pc=t_pc, total_ms=total_ms, post_ms=post_ms, raw_bytes=raw_bytes, frame=frame,
                           dets=[(d.label, d.confidence, d.xmin, d.ymin, d.xmax, d.ymax) for d in det.detections],
                           **extra)
            time.sleep(0.3)
            for buf in edge_queue.tryGetAll():
                self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())


class FakeSource:
    """카메라 없이 흐름을 검증하는 가짜 입력. 카메라 시계를 일부러 --fake-ppm 만큼 빠르게 만든다."""

    def __init__(self, args):
        self.args, self.edge_by_seq = args, {}
        self.session = oak_full.fake_session(args.model) if args.raw == "on" else None

    def wait_edge(self, seq, timeout=0.25):
        pass

    def frames(self, stop):
        a, t0, seq, last_tele = self.args, time.monotonic(), 0, 0.0
        full = a.raw == "on"
        while not stop.is_set():
            seq += 1
            true_t = time.monotonic() - t0
            edge = 100 + random.uniform(-5, 5)
            self.edge_by_seq[seq] = edge
            dets = [(random.randrange(4), random.uniform(0.4, 0.95), 0.4, 0.1, 0.44, 0.26)
                    for _ in range(random.randrange(0, 4))]
            extra = {}
            if full:
                tele = []
                if true_t - last_tele >= 1.0:
                    tele, last_tele = [oak_full.fake_telemetry()], true_t
                extra = dict(meta=oak_full.fake_meta(seq), ext=[oak_full.fake_ext() for _ in dets], tele=tele,
                             depth_bytes=640 * 400 * 2, depth_frame=None)
            yield dict(seq=seq, dev_t=1000 + true_t * (1 + a.fake_ppm * 1e-6), t_pc=time.time(),
                       total_ms=edge + 8, post_ms=2.0 if full else 0.0,
                       raw_bytes=(512 * 288 * 3 + 640 * 400 * 2) if full else 0, frame=None, dets=dets, **extra)
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
    det_rows, tele_rows, last_session = [], [], -1e9
    t_start = time.monotonic()
    t_first = None                # 첫 프레임 도착 시각: --duration 은 여기서부터 잰다 (카메라 시작 지연 제외)
    nic0 = nic_prev = read_nic_bytes(a.nic) if a.nic else None

    lock = threading.RLock()      # 메인 루프와 PERF 타이머 스레드가 같이 쓰는 값·CAN 송신을 보호

    def send(m):
        nonlocal can_tx, can_err, tx_in_sec
        with lock:
            try:
                bus.send(m, timeout=0.05)
                can_tx += 1
                tx_in_sec += 1
            except can.CanError:
                can_err += 1

    def perf_loop():
        """PERF 를 프레임 도착과 상관없이, 첫 프레임 기준 k초 + 50 ms (k=1,2,3…) 에 정확히 1초 간격으로 보낸다.
        (+50 ms 는 수신 쪽에서 정수 초로 내림해도 k 로 안정적으로 떨어지게 하는 여유)"""
        nonlocal last_perf, nic_prev, tx_in_sec
        k = 1
        while not stop.is_set():
            if t_first is None:
                stop.wait(0.01)
                continue
            if stop.wait(max(0.0, t_first + k + 0.05 - time.monotonic())):
                break
            with lock:
                now = time.monotonic()
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
            k += 1

    perf_thread = threading.Thread(target=perf_loop, daemon=True)
    perf_thread.start()

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
            order = sorted(range(len(f["dets"])), key=lambda i: -f["dets"][i][1])[:min(a.max_dets, 16)]
            for i, k in enumerate(order):
                send(det_box(f["seq"], i, *f["dets"][k]))
            ext = f.get("ext") or [{}] * len(f["dets"])
            for d, e in zip(f["dets"], ext):
                det_rows.append([f["seq"], *d, *(e.get(k, "") for k in DET_EXT_COLS)])
            if a.raw == "on":                      # 카메라가 줄 수 있는 나머지 데이터 전부를 CAN 으로
                for m in oak_full.frame_messages(f["seq"], f["meta"], order, f["ext"]):
                    send(m)
                for t in f["tele"]:
                    tele_rows.append(t)
                    for m in oak_full.telemetry_messages(t):
                        send(m)
                if source.session is not None and now - last_session >= 10.0:
                    last_session = now
                    for m in oak_full.session_messages(source.session):
                        send(m)
            if f["frame"] is not None and now - last_save >= a.save_every:
                import cv2
                cv2.imwrite(str(out / "images" / f"{f['seq']:06d}.jpg"), f["frame"])
                if f.get("depth_frame") is not None:
                    cv2.imwrite(str(out / "images" / f"{f['seq']:06d}_depth.png"), f["depth_frame"])   # 16비트 깊이(mm)
                last_save = now
            f["frame"] = f["depth_frame"] = None
            f["n_det"] = len(f["dets"])
            rows.append(f)
            with lock:
                recent.append((now, f["seq"], f["total_ms"], f["post_ms"], f["raw_bytes"]))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        perf_thread.join(timeout=2)
        t_end = time.monotonic()
        dur = max(t_end - (t_first if t_first is not None else t_start), 1e-6)
        startup_s = round((t_first if t_first is not None else t_end) - t_start, 1)
        nic1 = read_nic_bytes(a.nic) if a.nic else None
        time.sleep(0.3)
        bus.shutdown()

    # ---- 기록 저장 ----
    with open(out / "frames.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "raw", "seq", "t_send_s", "dev_t_s", "edge_ms", "pc_ms", "post_ms", "raw_bytes", "depth_bytes", "n_objects"])
        for r in rows:
            edge = source.edge_by_seq.get(r["seq"])
            w.writerow([a.model, a.raw, r["seq"], f"{r['t_send']:.6f}", f"{r['dev_t']:.6f}",
                        edge if edge is not None else "",
                        round(r["total_ms"] - edge, 2) if edge is not None else "",
                        round(r["post_ms"], 2), r["raw_bytes"], r.get("depth_bytes", 0), r["n_det"]])
    with open(out / "detections.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seq", "label", "confidence", "xmin", "ymin", "xmax", "ymax", *DET_EXT_COLS])
        w.writerows(det_rows)

    if tele_rows:
        with open(out / "telemetry.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(tele_rows[0]))
            w.writeheader()
            w.writerows(tele_rows)
    if source.session is not None:
        (out / "session.json").write_text(json.dumps(source.session, indent=1, ensure_ascii=False), encoding="utf-8")
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
