"""OAK-D 엣지 YOLO 토출 데이터를 시간축으로 기록한다 (최대 5분).

한 번 실행하면 runs/<시각>/ 아래에 남는 것:

    session.json     장치·모델·캘리브레이션 등 1회성 정보 + 실행 통계
    frames.csv       프레임당 1행 (시간, 지연, 카메라 메타데이터, 검출 요약)
    detections.csv   검출당 1행 (클래스, 신뢰도, 박스, XYZ 거리)
    telemetry.csv    1초당 1행 (칩 온도, CPU, 메모리)
    frames/          신경망이 실제로 처리한 이미지 (passthrough 그대로, JPEG)
    annotated.mp4    검출 박스를 그린 영상

열 정의는 params.py 한 곳에 있다.

    # 카메라 없이 전체 흐름 확인 (가짜 데이터)
    python3 edge_logger.py --source mock --duration 20

    # 실제 카메라, 5분
    python3 edge_logger.py --ip 169.254.1.222 --duration 300

    # 기록하면서 CAN으로도 송출 (가상 버스 / vcan0 / 실제 can0)
    python3 edge_logger.py --ip 169.254.1.222 --can-interface socketcan --can-channel vcan0
"""
import argparse
import csv
import json
import math
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import params
from common import draw_detections, draw_header

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "luxonis/yolov6-nano:r2-coco-512x288"
COUNTED = {"person": "n_person", "car": "n_car", "traffic light": "n_traffic_light",
           "stop sign": "n_stop_sign"}


def _try(fn, conv=lambda v: v):
    try:
        return conv(fn())
    except Exception:
        return ""


def _secs(td):
    return round(td.total_seconds(), 6)


# ====================================================================== 카메라
def camera_source(args, session):
    """실제 OAK-D. (이미지, frames 행, detections 행 목록, telemetry 행 목록)을 내보낸다.

    이 함수 안에 "NNArchive를 칩에 올리는" 부분(파이프라인 구성)과
    "호스트가 결과를 받는" 부분(아래 while pipeline.isRunning() 루프)이 같이 있다.
    """
    import depthai as dai

    # --- 모델 지정: 두 가지 방식 모두 지원 ---------------------------------
    # 1) --model에 실제 파일 경로(NNArchive .tar.xz)를 주면: dai.NNArchive(경로)로 직접 로드.
    #    커스텀 모델(자체 컴파일한 superblob+config.json을 패키징한 archive)을 쓸 때 이 경로.
    # 2) --model에 "yolov6-nano" 같은 이름만 주면: dai.NNModelDescription(이름)만 만들어두고,
    #    실제 다운로드는 뒤의 DetectionNetwork.build()가 호출될 때 일어난다
    #    (05_nnarchive/fetch_example.py의 dai.getModelFromZoo와 동일한 동작).
    model_path = Path(args.model)
    if model_path.exists():
        model = dai.NNArchive(str(model_path))
        session["nn_input_w"], session["nn_input_h"] = model.getInputWidth(), model.getInputHeight()
    else:
        model = dai.NNModelDescription(args.model)

    # --- 장치 연결: IP로 직접 붙되, 재부팅 직후처럼 아직 안 보이면 재시도 ---
    device = None
    for attempt in range(1, 6 if args.ip else 1):     # 직전 실행 뒤 장치가 재부팅 중이면 잠시 안 보인다
        try:
            device = dai.Device(dai.DeviceInfo(args.ip))
            break
        except RuntimeError as e:
            print(f"  장치 연결 실패 ({attempt}/5): {e}")
            if attempt == 5:
                raise
            time.sleep(4)
    pipeline = dai.Pipeline(device) if device else dai.Pipeline()
    device = device or pipeline.getDefaultDevice()

    session.update(
        device_id=_try(device.getDeviceId),
        product_name=_try(device.getProductName),
        platform=_try(device.getPlatformAsString),
        bootloader=_try(device.getBootloaderVersion, str),
        cameras=_try(device.getConnectedCameras, lambda cs: [str(c) for c in cs]),
        depthai_version=dai.__version__,
    )

    # ============================== NNArchive를 실제로 OAK-D 칩에 올리는 부분 ==============================
    with pipeline:
        # 카메라 노드: 소켓을 CAM_A(메인 RGB)로 명시. 06_oakd_chip/run_example.py의
        # 기본형과 달리 여기선 소켓을 직접 지정해 어떤 센서를 쓰는지 확실히 한다.
        cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        if args.spatial:
            # 거리(Depth) 계산까지 쓰는 경로: 스테레오 좌우 카메라로 깊이 지도를 만드는
            # Depth 노드를 추가하고, SpatialDetectionNetwork로 검출망 노드를 만든다.
            # 이 노드는 일반 DetectionNetwork에 "박스마다 depth 지도에서 XYZ 거리도 계산"
            # 하는 기능이 얹힌 것 — 그래서 칩 부하가 늘어난다 (2절에서 30fps 병목의 원인).
            depth = pipeline.create(dai.node.Depth).build(dai.node.Depth.Algorithm.AUTO, args.fps)
            nn = pipeline.create(dai.node.SpatialDetectionNetwork).build(cam, depth, model, fps=args.fps)
            nn.setDepthLowerThreshold(100)     # 100mm 미만은 깊이값 무효 처리 (센서 최소 거리 근처 잡음)
            nn.setDepthUpperThreshold(20000)   # 20m 초과도 무효 (스테레오 기선 대비 신뢰 못할 거리)
            nn.spatialLocationCalculator.initialConfig.setSegmentationPassthrough(False)
        else:
            # 거리 계산 없이 검출만: NNArchive(model)를 카메라 노드에 그대로 붙인다.
            # — 06_oakd_chip/run_example.py의 DetectionNetwork.build()와 원리는 동일하고,
            #   fps= 인자로 신경망 처리 주기를 직접 제한한다는 점만 다르다.
            nn = pipeline.create(dai.node.DetectionNetwork).build(cam, model, fps=args.fps)
        if args.conf is not None:
            nn.setConfidenceThreshold(args.conf)   # config.json 기본값(보통 0.5) 대신 직접 지정
        labels = nn.getClasses() or []
        session["n_classes"] = len(labels)
        session["conf_threshold"] = _try(nn.getConfidenceThreshold)

        # 시스템 로거: 칩 온도·CPU·메모리 사용량을 1초에 한 번(setRate(1.0)) 장치가
        # 직접 측정해서 보내주는 노드 — telemetry.csv의 출처가 바로 이거다.
        syslog = pipeline.create(dai.node.SystemLogger)
        syslog.setRate(1.0)

        # 출력 큐 4개 = 칩이 만든 결과를 호스트가 꺼내는 통로.
        # maxSize=8, blocking=False : 큐가 8개 차면 꽉 찬 상태에서도 get()이 즉시 리턴(논블로킹).
        #   호스트가 느려도 칩/장치 쪽이 멈추지 않게 하기 위함 (기록 지연이 프레임 손실보다 낫다).
        # passthrough는 반드시 소비한다 (안 만들면 장치가 연결을 끊는다 — Step 01)
        q_rgb = nn.passthrough.createOutputQueue(maxSize=8, blocking=False)        # 처리된 영상 프레임
        q_det = nn.out.createOutputQueue(maxSize=8, blocking=False)               # 검출 결과 (박스)
        q_sys = syslog.out.createOutputQueue(maxSize=8, blocking=False)           # 칩 온도/CPU/메모리
        q_depth = nn.passthroughDepth.createOutputQueue(maxSize=2, blocking=False) if args.spatial else None
        # ↑ 깊이 프레임 자체는 이 코드에서 값을 쓰지 않고 큐만 비워준다 (아래 tryGetAll) —
        #   안 만들면 장치 내부에 깊이 데이터가 쌓여 다른 큐처럼 연결이 끊길 수 있어서다.

        pipeline.start()  # 지금까지 구성한 그래프를 장치에서 실제로 실행 시작
        # ============================== 여기부터 "호스트가 검출을 받는" 부분 ==============================
        calib_done = False
        # frames/dets_by_seq : 프레임 큐와 검출 큐가 "따로" 오기 때문에, 같은 프레임을 가리키는
        #   프레임(passthrough)과 검출결과(out)를 seq(프레임 순번)로 짝지어야 한다.
        #   임시로 여기에 쌓아뒀다가 같은 seq가 둘 다 모이면 방출(yield)한다.
        frames, dets_by_seq = {}, {}
        try:
            while pipeline.isRunning():
                # q_det.get() : 검출 큐는 블로킹으로 하나 기다린다 (루프의 박자를 검출 주기에 맞춤).
                d = q_det.get()
                dets_by_seq[d.getSequenceNum()] = (d, dai.Clock.now())
                # q_rgb.tryGetAll() : 프레임 큐는 논블로킹으로 "그 사이 쌓인 만큼" 한꺼번에 꺼낸다.
                for f in q_rgb.tryGetAll():
                    frames[f.getSequenceNum()] = (f, dai.Clock.now())
                if q_depth is not None:
                    q_depth.tryGetAll()  # 깊이 프레임은 안 쓰지만 큐를 비워야 장치가 안 막힌다
                tele = [_telemetry(s) for s in q_sys.tryGetAll()]  # 1초마다 온 시스템 로그를 파싱

                # 같은 seq를 가진 프레임+검출 쌍이 모인 것만 골라 기록용으로 내보낸다.
                for seq in sorted(set(frames) & set(dets_by_seq)):
                    f, f_now = frames.pop(seq)
                    d, d_now = dets_by_seq.pop(seq)
                    img = f.getCvFrame()  # 신경망이 실제로 처리한 그 이미지 (512×288 등, JPEG로 저장됨)
                    if not calib_done:
                        # 캘리브레이션(초점거리·주점·기선)은 세션당 한 번만 읽으면 되므로 첫 프레임에서만
                        _calibration(device, dai, session, img.shape[1], img.shape[0])
                        calib_done = True
                    # 여기서 실제로 "이 프레임의 기록 1행 + 이 프레임의 검출 N행"을 만들어 내보낸다.
                    # main()의 for 루프가 이 값을 받아 CSV에 쓰고(Recorder), CAN으로도 보낸다(있으면).
                    yield img, _frame_row(f, d, f_now, d_now), _det_rows(d, labels, img.shape), tele
                    tele = []  # 텔레메트리는 한 번 방출했으면 다음 프레임에 또 넣지 않음 (중복 방지)
                # 짝을 못 찾은 오래된 항목 정리 (예: 검출 결과가 통신 문제로 영영 안 온 경우 메모리 누수 방지)
                newest = max(list(frames) + list(dets_by_seq) + [0])
                for dct in (frames, dets_by_seq):
                    for s in [s for s in dct if s < newest - 30]:
                        dct.pop(s)
        finally:
            # 종료 전 큐를 비워야 장치가 깨끗이 닫힌다 (06_oakd_chip/README.md)
            for q in (q_rgb, q_det, q_sys, q_depth):
                if q is not None:
                    _try(q.tryGetAll)
            pipeline.stop()


# --- 이 아래 세 함수(_calibration/_frame_row/_det_rows)와 _telemetry는 전부
#     "호스트가 칩에서 받은 결과를 사람이 쓸 값으로 정리하는" 코드다.
#     신경망 연산이나 디코딩은 전혀 하지 않는다 — 그건 이미 칩에서 끝나 있다.
def _calibration(device, dai, session, w, h):
    try:
        calib = device.readCalibration()
        m = calib.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, w, h)
        session.update(fx=m[0][0], fy=m[1][1], cx=m[0][2], cy=m[1][2])
        session["baseline_cm"] = _try(calib.getBaselineDistance)
    except Exception as e:
        session["calibration_error"] = str(e)
    session.setdefault("nn_input_w", w)
    session.setdefault("nn_input_h", h)


def _frame_row(f, d, f_now, d_now):
    """frames.csv 한 행. f=ImgFrame(프레임), d=ImgDetections(그 프레임의 검출),
    f_now/d_now=호스트가 각각을 받은 시각(지연 계산용)."""
    return dict(
        seq=f.getSequenceNum(),
        ts_device_s=_try(f.getTimestampDevice, _secs),
        ts_host_s=_try(f.getTimestamp, _secs),
        latency_ms=_try(lambda: (f_now - f.getTimestamp()).total_seconds() * 1000, lambda v: round(v, 2)),
        det_latency_ms=_try(lambda: (d_now - d.getTimestamp()).total_seconds() * 1000, lambda v: round(v, 2)),
        frame_w=f.getWidth(), frame_h=f.getHeight(),
        frame_type=_try(f.getType, lambda t: str(t).split(".")[-1]),
        source_w=_try(f.getSourceWidth), source_h=_try(f.getSourceHeight),
        cam_instance=_try(f.getInstanceNum),
        exposure_us=_try(f.getExposureTime, lambda td: int(td.total_seconds() * 1e6)),
        iso=_try(f.getSensitivity),
        lens_pos=_try(f.getLensPosition),
        lens_pos_raw=_try(f.getLensPositionRaw, lambda v: round(v, 4)),
        color_temp_k=_try(f.getColorTemperature),
        hfov_deg=_try(f.getSourceHFov, lambda v: round(v, 2)),
        vfov_deg=_try(f.getSourceVFov, lambda v: round(v, 2)),
    )


def _det_rows(d, labels, shape):
    """detections.csv 행들 (프레임 하나에 검출이 여러 개면 여러 행).
    det.xmin/ymin/xmax/ymax 등은 칩이 이미 디코딩·NMS까지 끝낸 최종 박스다 —
    여기서는 그 값을 꺼내 픽셀 단위로 환산하고, 깊이(spatialCoordinates)가 있으면 같이 담는다."""
    h, w = shape[:2]
    rows = []
    for i, det in enumerate(d.detections):
        name = _try(lambda: det.labelName) or (labels[det.label] if det.label < len(labels) else "")
        row = dict(idx=i, label=det.label, label_name=name,
                   confidence=round(det.confidence, 4),
                   xmin=round(det.xmin, 5), ymin=round(det.ymin, 5),
                   xmax=round(det.xmax, 5), ymax=round(det.ymax, 5),
                   angle_deg=_try(det.getAngle, lambda v: round(v, 2)))
        # spatialCoordinates: --spatial(=SpatialDetectionNetwork)일 때만 검출 객체에 붙어 있다.
        # 칩이 깊이 지도와 박스를 직접 매칭해서 낸 실좌표(mm) — 호스트는 계산 없이 받기만 한다.
        sc = getattr(det, "spatialCoordinates", None)
        if sc is not None:
            row.update(x_mm=round(sc.x, 1), y_mm=round(sc.y, 1), z_mm=round(sc.z, 1))
            m = det.boundingBoxMapping
            # roi_* 는 정규화(0~1) 값이 아니라 깊이 프레임 픽셀 좌표다 (실측으로 확인/수정한 부분)
            row.update(roi_x=round(m.roi.x, 5), roi_y=round(m.roi.y, 5),
                       roi_w=round(m.roi.width, 5), roi_h=round(m.roi.height, 5),
                       depth_lo_mm=m.depthThresholds.lowerThreshold,
                       depth_hi_mm=m.depthThresholds.upperThreshold)
        rows.append(row)
    return rows


def _telemetry(s):
    """telemetry.csv 한 행. s=SystemInformation (SystemLogger 노드가 1초마다 보낸 칩 상태)."""
    t, css, mss = s.chipTemperature, s.leonCssCpuUsage, s.leonMssCpuUsage
    mb, kb = 1024 * 1024, 1024
    return dict(
        ts_device_s=_try(s.getTimestampDevice, _secs),
        temp_css=round(t.css, 2), temp_mss=round(t.mss, 2), temp_upa=round(t.upa, 2),
        temp_dss=round(t.dss, 2), temp_avg=round(t.average, 2),
        cpu_css_pct=round(css.average * 100, 2), cpu_mss_pct=round(mss.average * 100, 2),
        ddr_used_mb=round(s.ddrMemoryUsage.used / mb, 2), ddr_total_mb=round(s.ddrMemoryUsage.total / mb, 2),
        cmx_used_kb=round(s.cmxMemoryUsage.used / kb, 1), cmx_total_kb=round(s.cmxMemoryUsage.total / kb, 1),
        css_heap_used_kb=round(s.leonCssMemoryUsage.used / kb, 1),
        css_heap_total_kb=round(s.leonCssMemoryUsage.total / kb, 1),
        mss_heap_used_kb=round(s.leonMssMemoryUsage.used / kb, 1),
        mss_heap_total_kb=round(s.leonMssMemoryUsage.total / kb, 1),
    )


# ====================================================================== 가짜 소스
def mock_source(args, session):
    """카메라 없이 전체 흐름을 검증하기 위한 합성 데이터. 모든 열을 채운다."""
    rng = np.random.default_rng(0)
    w, h = 512, 288
    session.update(device_id="MOCK", product_name="mock", platform="RVC2", bootloader="mock",
                   cameras=["CAM_A", "CAM_B", "CAM_C"], depthai_version="mock",
                   nn_input_w=w, nn_input_h=h, n_classes=80, conf_threshold=0.5,
                   fx=450.0, fy=450.0, cx=256.0, cy=144.0, baseline_cm=7.5)
    period = 1.0 / args.fps
    t_dev0 = 1000.0
    next_tele = 0.0
    seq = 0
    while True:
        t = seq * period
        if args.realtime:
            time.sleep(period)
        img = np.full((h, w, 3), 60, np.uint8)
        cv2.putText(img, f"MOCK t={t:6.2f}s seq={seq}", (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (200, 200, 200), 1)
        objs = [("traffic light", 9, 0.40, 0.10, 0.04, 0.16, 25000),
                ("car", 2, 0.1 + 0.8 * ((t / 20) % 1), 0.55, 0.18, 0.22, 15000 - 600 * ((t / 20) % 1) * 20)]
        if int(t / 5) % 2:
            objs.append(("person", 0, 0.75, 0.45, 0.06, 0.30, 6000))
        dets = []
        for i, (name, lab, cx, cy, bw, bh, z) in enumerate(objs):
            cv2.rectangle(img, (int((cx - bw / 2) * w), int((cy - bh / 2) * h)),
                          (int((cx + bw / 2) * w), int((cy + bh / 2) * h)), (120, 120, 120), -1)
            x_mm = (cx - 0.5) * z * w / 450.0
            y_mm = (cy - 0.5) * z * h / 450.0
            dets.append(dict(idx=i, label=lab, label_name=name,
                             confidence=round(float(np.clip(0.8 + rng.normal(0, 0.05), 0, 1)), 4),
                             xmin=round(cx - bw / 2, 5), ymin=round(cy - bh / 2, 5),
                             xmax=round(cx + bw / 2, 5), ymax=round(cy + bh / 2, 5), angle_deg=0.0,
                             x_mm=round(x_mm, 1), y_mm=round(y_mm, 1), z_mm=round(z, 1),
                             roi_x=round(cx - bw / 4, 5), roi_y=round(cy - bh / 4, 5),
                             roi_w=round(bw / 2, 5), roi_h=round(bh / 2, 5),
                             depth_lo_mm=100, depth_hi_mm=20000))
        frame = dict(seq=seq, ts_device_s=round(t_dev0 + t, 6), ts_host_s=round(t, 6),
                     latency_ms=round(35 + rng.normal(0, 3), 2), det_latency_ms=round(40 + rng.normal(0, 3), 2),
                     frame_w=w, frame_h=h, frame_type="BGR888i", source_w=1920, source_h=1080,
                     cam_instance=0, exposure_us=8000, iso=400, lens_pos=130, lens_pos_raw=0.51,
                     color_temp_k=4500, hfov_deg=68.8, vfov_deg=42.1)
        tele = []
        if t >= next_tele:
            next_tele += 1.0
            tt = 40 + t / 30
            tele.append(dict(ts_device_s=round(t_dev0 + t, 6), temp_css=tt, temp_mss=tt - 0.5,
                             temp_upa=tt + 0.3, temp_dss=tt - 0.2, temp_avg=tt,
                             cpu_css_pct=35.0, cpu_mss_pct=20.0, ddr_used_mb=150.0, ddr_total_mb=340.0,
                             cmx_used_kb=2000.0, cmx_total_kb=2048.0, css_heap_used_kb=30000.0,
                             css_heap_total_kb=80000.0, mss_heap_used_kb=10000.0, mss_heap_total_kb=40000.0))
        yield img, frame, dets, tele, t
        seq += 2 if seq % 97 == 96 else 1       # 가끔 프레임 누락을 흉내 낸다 (seq_gap 검증용)


# ====================================================================== 기록
class Recorder:
    """디스크 쓰기를 별도 스레드로 돌려 카메라 큐 소비가 막히지 않게 한다."""

    def __init__(self, out, fps, save_every, jpeg_quality):
        self.out = out
        (out / "frames").mkdir(parents=True, exist_ok=True)
        self.fps, self.save_every, self.q_jpeg = fps, save_every, jpeg_quality
        self.files = {}
        self.writers = {}
        for name in ("frames", "detections", "telemetry"):
            fh = open(out / f"{name}.csv", "w", newline="")
            self.files[name] = fh
            self.writers[name] = csv.DictWriter(fh, fieldnames=params.columns(name), extrasaction="ignore")
            self.writers[name].writeheader()
        self.video = None
        self.q = queue.Queue(maxsize=300)
        self.dropped = 0
        self.th = threading.Thread(target=self._loop, daemon=True)
        self.th.start()

    def put(self, item):
        try:
            self.q.put(item, timeout=0.5)
        except queue.Full:
            self.dropped += 1

    def _loop(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            kind = item[0]
            if kind == "tele":
                self.writers["telemetry"].writerow(item[1])
                continue
            _, frow, drows, img, save = item
            if save:
                cv2.imwrite(str(self.out / frow["image_file"]), img,
                            [cv2.IMWRITE_JPEG_QUALITY, self.q_jpeg])
            self.writers["frames"].writerow(frow)
            for r in drows:
                self.writers["detections"].writerow(r)
            ann = draw_header(draw_detections(img.copy(), drows),
                              f"t={frow['t_s']:.2f}s seq={frow['seq']} det={frow['det_count']} "
                              f"lat={frow['latency_ms']}ms")
            if self.video is None:
                h, w = ann.shape[:2]
                self.video = cv2.VideoWriter(str(self.out / "annotated.mp4"),
                                             cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
            self.video.write(ann)

    def close(self):
        self.q.put(None)
        self.th.join()
        if self.video is not None:
            self.video.release()
        for fh in self.files.values():
            fh.close()


def summarize(frow, drows, spatial):
    confs = [d["confidence"] for d in drows]
    frow["det_count"] = len(drows)
    frow["conf_max"] = round(max(confs), 4) if confs else ""
    frow["conf_mean"] = round(sum(confs) / len(confs), 4) if confs else ""
    frow["top_label"] = max(drows, key=lambda d: d["confidence"])["label_name"] if drows else ""
    for name, col in COUNTED.items():
        frow[col] = sum(d["label_name"] == name for d in drows)
    zs = [d["z_mm"] for d in drows if d.get("z_mm") not in (None, "") and d["z_mm"] > 0]
    frow["nearest_z_mm"] = min(zs) if zs else ""
    fw, fh = frow["frame_w"], frow["frame_h"]
    for d in drows:
        d["t_s"], d["seq"] = frow["t_s"], frow["seq"]
        bw, bh = d["xmax"] - d["xmin"], d["ymax"] - d["ymin"]
        d.update(cx_px=round((d["xmin"] + d["xmax"]) / 2 * fw, 1),
                 cy_px=round((d["ymin"] + d["ymax"]) / 2 * fh, 1),
                 w_px=round(bw * fw, 1), h_px=round(bh * fh, 1), area_ratio=round(bw * bh, 5))
        if d.get("z_mm") not in (None, ""):
            x, y, z = d["x_mm"], d["y_mm"], d["z_mm"]
            d["range_mm"] = round(math.sqrt(x * x + y * y + z * z), 1)
            d["bearing_deg"] = round(math.degrees(math.atan2(x, z)), 2) if z > 0 else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["camera", "mock"], default="camera")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="모델 주 이름 또는 NNArchive(.tar.xz) 경로")
    ap.add_argument("--ip", help="장치 IP (예: 169.254.1.222). 자동 탐색은 부팅 중 실패하므로 지정 권장")
    ap.add_argument("--duration", type=float, default=300.0, help="기록 시간 [s], 기본 300 (5분)")
    ap.add_argument("--fps", type=float, help="기본: 거리 계산 켜면 20, 끄면 30 (실측: 켜고 30이면 25%% 누락·지연 358ms)")
    ap.add_argument("--conf", type=float, help="신뢰도 문턱 (기본: 모델 설정값)")
    ap.add_argument("--no-spatial", dest="spatial", action="store_false", help="깊이(XYZ) 계산 끄기")
    ap.add_argument("--save-every", type=int, default=1, help="N프레임마다 원본 이미지 저장 (0=저장 안 함)")
    ap.add_argument("--jpeg-quality", type=int, default=90)
    ap.add_argument("--out", help="출력 폴더 (기본: runs/<시각>)")
    ap.add_argument("--display", action="store_true", help="기록 중 화면 표시")
    ap.add_argument("--realtime", action="store_true", help="mock을 실제 속도로 재생")
    ap.add_argument("--can-interface", help="CAN 동시 송출: virtual | socketcan | slcan | pcan ...")
    ap.add_argument("--can-channel", default="vcan0")
    ap.add_argument("--can-bitrate", type=int, default=500000)
    args = ap.parse_args()
    if args.fps is None:
        args.fps = 20.0 if args.spatial else 30.0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else HERE / "runs" / f"{stamp}_{args.source}"
    out.mkdir(parents=True, exist_ok=True)
    session = dict(model=args.model, spatial=args.spatial, started_at=datetime.now().isoformat(timespec="seconds"),
                   source=args.source, duration_req_s=args.duration, fps_req=args.fps)

    pub = None
    if args.can_interface:
        from can_bridge import CanPublisher
        pub = CanPublisher(args.can_interface, args.can_channel, args.can_bitrate)

    rec = Recorder(out, args.fps, args.save_every, args.jpeg_quality)   # CSV·이미지·영상을 별도 스레드로 기록
    # src : camera_source(실제 OAK-D, 위에서 칩에 올리고 결과 받는 제너레이터) 또는
    #       mock_source(카메라 없이 흐름만 검증하는 가짜 데이터 제너레이터).
    #       아래 for 루프 입장에서는 둘 다 (이미지, frame행, det행들, tele행들[, t]) 를 주는 동일한 인터페이스.
    src = mock_source(args, session) if args.source == "mock" else camera_source(args, session)
    print(f"기록 시작 → {out}")

    t0 = None
    prev_t = prev_seq = None
    n = gaps = det_total = 0
    last_print = 0.0
    stats_temp = []
    try:
        for item in src:
            if args.source == "mock":
                img, frow, drows, tele, t_s = item
            else:
                img, frow, drows, tele = item
                now = time.monotonic()
                t0 = now if t0 is None else t0
                t_s = now - t0
            if t_s > args.duration:
                break
            frow["t_s"] = round(t_s, 4)
            frow["fps_inst"] = round(1.0 / (t_s - prev_t), 2) if prev_t is not None and t_s > prev_t else ""
            frow["seq_gap"] = frow["seq"] - prev_seq - 1 if prev_seq is not None else 0
            gaps += max(frow["seq_gap"], 0)
            prev_t, prev_seq = t_s, frow["seq"]
            summarize(frow, drows, args.spatial)
            save = args.save_every > 0 and n % args.save_every == 0
            frow["image_file"] = f"frames/{frow['seq']:06d}.jpg" if save else ""
            rec.put(("frame", frow, drows, img, save))
            for tr in tele:
                tr["t_s"] = frow["t_s"]
                stats_temp.append(tr["temp_avg"])
                rec.put(("tele", tr))
            if pub:
                pub.send_frame(frow, drows)
                for tr in tele:
                    pub.send_telemetry(tr)
            n += 1
            det_total += len(drows)

            if args.display:
                ann = draw_detections(img.copy(), drows)
                cv2.imshow("edge_logger", ann)
                if cv2.waitKey(1) == ord("q"):
                    break
            if t_s - last_print >= 10:
                last_print = t_s
                print(f"  t={t_s:6.1f}s  프레임 {n:6d}  누락 {gaps:4d}  검출 {det_total:7d}"
                      + (f"  칩 {stats_temp[-1]:.1f}°C" if stats_temp else ""))
    except KeyboardInterrupt:
        print("중단 (Ctrl+C)")
    finally:
        src.close()
        rec.close()
        if pub:
            pub.close()
        elapsed = prev_t or 0.0
        session.update(frames=n, seq_gaps=gaps, detections=det_total, elapsed_s=round(elapsed, 2),
                       fps_avg=round((n - 1) / elapsed, 2) if elapsed else "",
                       recorder_dropped=rec.dropped,
                       can_sent=pub.sent if pub else "", can_errors=pub.errors if pub else "")
        (out / "session.json").write_text(json.dumps(session, indent=2, ensure_ascii=False))
        print(f"완료: {n}프레임 / {elapsed:.1f}s, 누락 {gaps}, 검출 {det_total}, 저장 누락 {rec.dropped}")
        if n == 0:
            print("경고: 프레임 0개. 장치 연결 확인: nmcli connection up oak-poe && ping 169.254.1.222")
        else:
            print(f"검토: python3 review.py summary {out}")


if __name__ == "__main__":
    main()
