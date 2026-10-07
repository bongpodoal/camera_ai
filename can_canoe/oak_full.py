"""--raw on (= 카메라로 받을 수 있는 모든 데이터) 용 수집·변환 도구.

받는 것 (예제 07_host_output 의 89개 파라미터와 같은 범위):
    깊이(스테레오)로 계산한 검출마다 X/Y/Z 와 깊이 ROI · 프레임마다 노출·ISO·색온도·렌즈·크기·시각 ·
    1초마다 칩 온도·CPU·메모리 · 10초마다 보정값(fx·fy·cx·cy·기선)·장치 ID·제품명·플랫폼·부트로더·모델
이더넷으로만 오는 영상류(처리된 RGB 프레임, 깊이 프레임)는 CAN 에 실을 수 없어 받아서 크기만 센다.
CAN 으로는 위 숫자·문자열 전부를 oakd_canoe.dbc 의 메시지로 보낸다.
"""
import random

from can_msgs import info_messages, make

WRAP = 2 ** 32
INFO_IDS = {"device_id": 0, "product_name": 1, "platform": 2, "bootloader": 3, "depthai_version": 4, "model": 5}


def try_(fn, conv=lambda v: v, default=0):
    try:
        return conv(fn())
    except Exception:
        return default


# ------------------------------------------------------------ 카메라에서 꺼내기 (depthai 필요)
def telemetry_row(s):
    """SystemInformation → 한 행 (example/07_host_output/edge_logger.py 의 _telemetry 와 같음)."""
    t, css, mss = s.chipTemperature, s.leonCssCpuUsage, s.leonMssCpuUsage
    mb, kb = 1024 * 1024, 1024
    return dict(
        ts_device_s=try_(lambda: s.getTimestampDevice().total_seconds()),
        temp_css=t.css, temp_mss=t.mss, temp_upa=t.upa, temp_dss=t.dss, temp_avg=t.average,
        cpu_css_pct=css.average * 100, cpu_mss_pct=mss.average * 100,
        ddr_used_mb=s.ddrMemoryUsage.used / mb, ddr_total_mb=s.ddrMemoryUsage.total / mb,
        cmx_used_kb=s.cmxMemoryUsage.used / kb, cmx_total_kb=s.cmxMemoryUsage.total / kb,
        css_heap_used_kb=s.leonCssMemoryUsage.used / kb, css_heap_total_kb=s.leonCssMemoryUsage.total / kb,
        mss_heap_used_kb=s.leonMssMemoryUsage.used / kb, mss_heap_total_kb=s.leonMssMemoryUsage.total / kb)


def session_info(device, dai, nn, model_name, w, h):
    """한 번만 읽는 값: 보정, 장치 정보, 신경망 설정."""
    sess = dict(depth_lo_mm=100, depth_hi_mm=20000, nn_w=w, nn_h=h, spatial=1, model=model_name,
                depthai_version=dai.__version__)
    try:
        calib = device.readCalibration()
        m = calib.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, w, h)
        sess.update(fx=m[0][0], fy=m[1][1], cx=m[0][2], cy=m[1][2], baseline_cm=calib.getBaselineDistance())
    except Exception as e:
        sess["calibration_error"] = str(e)
    sess.update(device_id=try_(device.getDeviceId, str, ""), product_name=try_(device.getProductName, str, ""),
                platform=try_(device.getPlatformAsString, str, ""), bootloader=try_(device.getBootloaderVersion, str, ""))
    cams = try_(device.getConnectedCameras, lambda cs: [str(c) for c in cs], [])
    sess["cameras"] = cams
    sess["camera_mask"] = sum(1 << i for i, n in enumerate(("CAM_A", "CAM_B", "CAM_C", "CAM_D", "CAM_E")) if any(n in c for c in cams))
    sess["n_classes"] = try_(lambda: len(nn.getClasses() or []))
    sess["conf_threshold"] = try_(nn.getConfidenceThreshold, float, 0)
    return sess


def frame_meta(f, d, f_now, d_now):
    """ImgFrame f 와 검출 d 에서 프레임 메타를 뽑는다."""
    return dict(
        exposure_us=try_(lambda: int(f.getExposureTime().total_seconds() * 1e6)), iso=try_(f.getSensitivity),
        color_temp_k=try_(f.getColorTemperature), lens_pos=try_(f.getLensPosition, int, -1),
        source_w=try_(f.getSourceWidth), source_h=try_(f.getSourceHeight), cam_instance=try_(f.getInstanceNum),
        frame_type=try_(lambda: int(f.getType().value)), frame_w=f.getWidth(), frame_h=f.getHeight(),
        hfov_deg=try_(f.getSourceHFov), vfov_deg=try_(f.getSourceVFov),
        ts_device_us=try_(lambda: int(f.getTimestampDevice().total_seconds() * 1e6)),
        ts_host_us=try_(lambda: int(f.getTimestamp().total_seconds() * 1e6)),
        det_latency_ms=try_(lambda: (d_now - d.getTimestamp()).total_seconds() * 1000),
        frame_latency_ms=try_(lambda: (f_now - f.getTimestamp()).total_seconds() * 1000))


def det_ext(det):
    """검출 하나의 깊이 정보 (SpatialDetectionNetwork 일 때만 있음)."""
    sc = getattr(det, "spatialCoordinates", None)
    out = dict(x_mm=0, y_mm=0, z_mm=0, roi_x=0, roi_y=0, roi_w=0, roi_h=0)
    if sc is not None:
        out.update(x_mm=sc.x, y_mm=sc.y, z_mm=sc.z)
        try:
            m = det.boundingBoxMapping
            out.update(roi_x=m.roi.x, roi_y=m.roi.y, roi_w=m.roi.width, roi_h=m.roi.height)
        except Exception:
            pass
    return out


# ------------------------------------------------------------ CAN 메시지로 바꾸기
def frame_messages(seq, meta, order, ext):
    """프레임 하나의 추가 메시지: 메타 5개 + 검출마다 위치·ROI (DET_BOX 와 같은 Index 순서)."""
    m = meta
    msgs = [
        make("FRAME_META_A", Seq=seq % 65536, ExposureUs=m["exposure_us"], Iso=m["iso"], ColorTempK=m["color_temp_k"]),
        make("FRAME_META_B", Seq=seq % 65536, LensPos=m["lens_pos"], SourceW=m["source_w"], SourceH=m["source_h"],
             CamInstance=m["cam_instance"], FrameType=m["frame_type"]),
        make("FRAME_META_C", Seq=seq % 65536, FrameW=m["frame_w"], FrameH=m["frame_h"], HfovDeg=m["hfov_deg"], VfovDeg=m["vfov_deg"]),
        make("FRAME_TIME_DEV", Seq=seq % 65536, TsDeviceUs=m["ts_device_us"] % WRAP, DetLatencyMs=m["det_latency_ms"]),
        make("FRAME_TIME_HOST", Seq=seq % 65536, TsHostUs=m["ts_host_us"] % WRAP, FrameLatencyMs=m["frame_latency_ms"]),
    ]
    for i, k in enumerate(order):
        e = ext[k]
        msgs.append(make("DET_POS", SeqLo=seq % 16, Index=i, X=e["x_mm"], Y=e["y_mm"], Z=e["z_mm"]))
        msgs.append(make("DET_ROI", SeqLo=seq % 16, Index=i, RoiX=e["roi_x"], RoiY=e["roi_y"], RoiW=e["roi_w"], RoiH=e["roi_h"]))
    return msgs


def telemetry_messages(t):
    return [
        make("DEV_TEMP", TempCss=t["temp_css"], TempMss=t["temp_mss"], TempUpa=t["temp_upa"], TempDss=t["temp_dss"],
             TempAvg=t["temp_avg"], CpuCssPct=t["cpu_css_pct"], CpuMssPct=t["cpu_mss_pct"]),
        make("DEV_MEM_A", DdrUsedMB=t["ddr_used_mb"], DdrTotalMB=t["ddr_total_mb"], CmxUsedKB=t["cmx_used_kb"],
             CmxTotalKB=t["cmx_total_kb"]),
        make("DEV_MEM_B", CssHeapUsedKB=t["css_heap_used_kb"], CssHeapTotalKB=t["css_heap_total_kb"]),
        make("DEV_MEM_C", MssHeapUsedKB=t["mss_heap_used_kb"], MssHeapTotalKB=t["mss_heap_total_kb"]),
    ]


def session_messages(s):
    msgs = [
        make("CALIB_A", Fx=s.get("fx", 0), Fy=s.get("fy", 0), Cx=s.get("cx", 0), Cy=s.get("cy", 0)),
        make("CALIB_B", BaselineCm=s.get("baseline_cm", 0), DepthLoMm=s["depth_lo_mm"], DepthHiMm=s["depth_hi_mm"],
             NClasses=s.get("n_classes", 0), ConfThresholdPct=round(s.get("conf_threshold", 0) * 100)),
        make("CALIB_C", NnInputW=s["nn_w"], NnInputH=s["nn_h"], SpatialOn=s["spatial"], CameraMask=s.get("camera_mask", 0)),
    ]
    for key, sid in INFO_IDS.items():
        if s.get(key):
            msgs += info_messages(sid, str(s[key]))
    return msgs


# ------------------------------------------------------------ 가짜 데이터 (카메라 없이 검증)
def fake_meta(seq, w=512, h=288):
    return dict(exposure_us=random.randrange(5000, 33000), iso=random.choice((100, 200, 400)),
                color_temp_k=random.randrange(3000, 7000), lens_pos=-1, source_w=1920, source_h=1080, cam_instance=0,
                frame_type=random.choice((0, 8)), frame_w=w, frame_h=h, hfov_deg=random.uniform(60, 80),
                vfov_deg=random.uniform(40, 50), ts_device_us=int(seq * 200000), ts_host_us=int(seq * 200000 + 12345),
                det_latency_ms=random.uniform(60, 90), frame_latency_ms=random.uniform(2, 5))


def fake_ext():
    return dict(x_mm=random.uniform(-3000, 3000), y_mm=random.uniform(-1500, 500), z_mm=random.uniform(2000, 30000),
                roi_x=random.randrange(0, 600), roi_y=random.randrange(0, 350), roi_w=random.randrange(5, 40),
                roi_h=random.randrange(5, 40))


def fake_telemetry():
    return dict(ts_device_s=0, temp_css=random.uniform(40, 55), temp_mss=random.uniform(40, 55),
                temp_upa=random.uniform(40, 55), temp_dss=random.uniform(40, 55), temp_avg=random.uniform(40, 55),
                cpu_css_pct=random.uniform(20, 95), cpu_mss_pct=random.uniform(10, 60), ddr_used_mb=random.uniform(100, 300),
                ddr_total_mb=340.0, cmx_used_kb=random.uniform(1000, 2000), cmx_total_kb=2048.0,
                css_heap_used_kb=random.uniform(2e4, 3e4), css_heap_total_kb=8e4, mss_heap_used_kb=random.uniform(5e3, 1e4),
                mss_heap_total_kb=4e4)


def fake_session(model):
    return dict(depth_lo_mm=100, depth_hi_mm=20000, nn_w=512, nn_h=288, spatial=1, model=model, depthai_version="mock",
                fx=420.5, fy=420.7, cx=256.2, cy=144.1, baseline_cm=7.5, device_id="19443010C19B387E00",
                product_name="OAK-D-PRO-POE-FF", platform="RVC2", bootloader="0.0.28", cameras=["CAM_A", "CAM_B", "CAM_C"],
                camera_mask=7, n_classes=80, conf_threshold=0.5)
