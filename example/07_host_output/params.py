"""OAK-D 엣지 토출 파라미터 카탈로그 — 무엇을, 어디서 꺼내, 어느 파일에 기록하는가.

로거(edge_logger.py)와 검토 도구(review.py)가 이 목록 하나를 공유한다.
CSV 열 순서도 여기서 정해진다.

    python3 params.py            # 파일별 개수
    python3 params.py --md       # 문서용 표
"""
import sys
from collections import namedtuple

P = namedtuple("P", "file name unit source desc")

# file: session(1회) · frames(프레임당 1행) · detections(검출당 1행) · telemetry(1초당 1행)
CATALOG = [
    # ---------------------------------------------------------------- session.json
    P("session", "device_id",        "",    "Device.getDeviceId()",              "장치 고유 ID"),
    P("session", "product_name",     "",    "Device.getProductName()",           "제품명"),
    P("session", "platform",         "",    "Device.getPlatformAsString()",      "칩 플랫폼 (RVC2)"),
    P("session", "bootloader",       "",    "Device.getBootloaderVersion()",     "부트로더 버전"),
    P("session", "cameras",          "",    "Device.getConnectedCameras()",      "연결된 센서 소켓"),
    P("session", "depthai_version",  "",    "depthai.__version__",               "호스트 라이브러리 버전"),
    P("session", "model",            "",    "인자",                              "모델 (주 이름 또는 NNArchive)"),
    P("session", "nn_input_w",       "px",  "NNArchive.getInputWidth()",         "신경망 입력 가로"),
    P("session", "nn_input_h",       "px",  "NNArchive.getInputHeight()",        "신경망 입력 세로"),
    P("session", "n_classes",        "",    "DetectionNetwork.getClasses()",     "클래스 수"),
    P("session", "conf_threshold",   "",    "getConfidenceThreshold()",          "신뢰도 문턱"),
    P("session", "spatial",          "",    "인자",                              "깊이(XYZ) 계산 여부"),
    P("session", "fx",               "px",  "CalibrationHandler.getCameraIntrinsics", "초점거리 x (신경망 입력 크기 기준)"),
    P("session", "fy",               "px",  "CalibrationHandler.getCameraIntrinsics", "초점거리 y"),
    P("session", "cx",               "px",  "CalibrationHandler.getCameraIntrinsics", "주점 x"),
    P("session", "cy",               "px",  "CalibrationHandler.getCameraIntrinsics", "주점 y"),
    P("session", "baseline_cm",      "cm",  "CalibrationHandler.getBaselineDistance()", "스테레오 기선 거리"),
    P("session", "started_at",       "",    "호스트 시계",                        "기록 시작 시각 (ISO 8601)"),

    # ---------------------------------------------------------------- frames.csv
    P("frames", "t_s",               "s",   "호스트 단조 시계",                   "기록 시작 후 경과 시간 (시간축)"),
    P("frames", "seq",               "",    "ImgFrame.getSequenceNum()",         "프레임 순번"),
    P("frames", "ts_device_s",       "s",   "ImgFrame.getTimestampDevice()",     "장치 시계 기준 촬영 시각"),
    P("frames", "ts_host_s",         "s",   "ImgFrame.getTimestamp()",           "호스트 시계로 동기화한 촬영 시각"),
    P("frames", "latency_ms",        "ms",  "Clock.now() - getTimestamp()",      "촬영 → 호스트 수신까지 지연"),
    P("frames", "det_latency_ms",    "ms",  "Clock.now() - ImgDetections.getTimestamp()", "촬영 → 검출 결과 수신까지 지연"),
    P("frames", "fps_inst",          "fps", "직전 프레임 간격",                   "순간 처리율"),
    P("frames", "seq_gap",           "",    "seq 차이 - 1",                       "직전 이후 누락된 프레임 수"),
    P("frames", "frame_w",           "px",  "ImgFrame.getWidth()",               "신경망이 처리한 이미지 가로"),
    P("frames", "frame_h",           "px",  "ImgFrame.getHeight()",              "신경망이 처리한 이미지 세로"),
    P("frames", "frame_type",        "",    "ImgFrame.getType()",                "픽셀 형식"),
    P("frames", "source_w",          "px",  "ImgFrame.getSourceWidth()",         "센서 원본 가로"),
    P("frames", "source_h",          "px",  "ImgFrame.getSourceHeight()",        "센서 원본 세로"),
    P("frames", "cam_instance",      "",    "ImgFrame.getInstanceNum()",         "카메라 소켓 번호"),
    P("frames", "exposure_us",       "us",  "ImgFrame.getExposureTime()",        "노출 시간"),
    P("frames", "iso",               "",    "ImgFrame.getSensitivity()",         "감도"),
    P("frames", "lens_pos",          "",    "ImgFrame.getLensPosition()",        "초점 렌즈 위치 (0~255, 고정초점 모델은 -1)"),
    P("frames", "lens_pos_raw",      "",    "ImgFrame.getLensPositionRaw()",     "초점 렌즈 위치 (원시값)"),
    P("frames", "color_temp_k",      "K",   "ImgFrame.getColorTemperature()",    "화이트밸런스 색온도"),
    P("frames", "hfov_deg",          "deg", "ImgFrame.getSourceHFov()",          "수평 화각"),
    P("frames", "vfov_deg",          "deg", "ImgFrame.getSourceVFov()",          "수직 화각"),
    P("frames", "det_count",         "",    "len(ImgDetections.detections)",     "이 프레임의 검출 수"),
    P("frames", "conf_max",          "",    "max(confidence)",                   "최고 신뢰도"),
    P("frames", "conf_mean",         "",    "mean(confidence)",                  "평균 신뢰도"),
    P("frames", "top_label",         "",    "최고 신뢰도 검출의 labelName",       "대표 클래스"),
    P("frames", "n_person",          "",    "label == person",                   "사람 수"),
    P("frames", "n_car",             "",    "label == car",                      "승용차 수"),
    P("frames", "n_traffic_light",   "",    "label == traffic light",            "신호등 수"),
    P("frames", "n_stop_sign",       "",    "label == stop sign",                "정지 표지 수"),
    P("frames", "nearest_z_mm",      "mm",  "min(spatialCoordinates.z)",         "가장 가까운 검출의 전방 거리"),
    P("frames", "image_file",        "",    "저장 경로",                          "이 프레임의 원본 이미지 (신경망 입력 그대로)"),

    # ---------------------------------------------------------------- detections.csv
    P("detections", "t_s",           "s",   "frames.t_s",                        "시간축"),
    P("detections", "seq",           "",    "ImgDetections.getSequenceNum()",    "프레임 순번 (frames.csv와 결합 키)"),
    P("detections", "idx",           "",    "목록 순서",                          "프레임 안 검출 번호"),
    P("detections", "label",         "",    "ImgDetection.label",                "클래스 번호"),
    P("detections", "label_name",    "",    "ImgDetection.labelName",            "클래스 이름"),
    P("detections", "confidence",    "",    "ImgDetection.confidence",           "신뢰도 (0~1)"),
    P("detections", "xmin",          "",    "ImgDetection.xmin",                 "박스 왼쪽 (정규화 0~1)"),
    P("detections", "ymin",          "",    "ImgDetection.ymin",                 "박스 위쪽"),
    P("detections", "xmax",          "",    "ImgDetection.xmax",                 "박스 오른쪽"),
    P("detections", "ymax",          "",    "ImgDetection.ymax",                 "박스 아래쪽"),
    P("detections", "cx_px",         "px",  "(xmin+xmax)/2 × frame_w",           "박스 중심 x"),
    P("detections", "cy_px",         "px",  "(ymin+ymax)/2 × frame_h",           "박스 중심 y"),
    P("detections", "w_px",          "px",  "(xmax-xmin) × frame_w",             "박스 가로"),
    P("detections", "h_px",          "px",  "(ymax-ymin) × frame_h",             "박스 세로"),
    P("detections", "area_ratio",    "",    "w × h (정규화)",                    "화면 대비 박스 면적"),
    P("detections", "angle_deg",     "deg", "ImgDetection.getAngle()",           "박스 회전각 (OBB 모델만)"),
    P("detections", "x_mm",          "mm",  "spatialCoordinates.x",              "카메라 기준 좌우 위치 (+오른쪽)"),
    P("detections", "y_mm",          "mm",  "spatialCoordinates.y",              "카메라 기준 상하 위치"),
    P("detections", "z_mm",          "mm",  "spatialCoordinates.z",              "카메라 기준 전방 거리"),
    P("detections", "range_mm",      "mm",  "sqrt(x²+y²+z²)",                    "직선 거리"),
    P("detections", "bearing_deg",   "deg", "atan2(x, z)",                       "정면 기준 방위각"),
    P("detections", "roi_x",        "px",  "boundingBoxMapping.roi",            "깊이 계산 ROI 왼쪽 (깊이 프레임 픽셀)"),
    P("detections", "roi_y",        "px",  "boundingBoxMapping.roi",            "깊이 계산 ROI 위쪽"),
    P("detections", "roi_w",        "px",  "boundingBoxMapping.roi",            "깊이 계산 ROI 가로"),
    P("detections", "roi_h",        "px",  "boundingBoxMapping.roi",            "깊이 계산 ROI 세로"),
    P("detections", "depth_lo_mm",   "mm",  "boundingBoxMapping.depthThresholds", "깊이 유효 하한"),
    P("detections", "depth_hi_mm",   "mm",  "boundingBoxMapping.depthThresholds", "깊이 유효 상한"),

    # ---------------------------------------------------------------- telemetry.csv
    P("telemetry", "t_s",            "s",   "호스트 단조 시계",                   "시간축"),
    P("telemetry", "ts_device_s",    "s",   "SystemInformation.getTimestampDevice()", "장치 시계"),
    P("telemetry", "temp_css",       "°C",  "chipTemperature.css",               "칩 온도: CPU 서브시스템"),
    P("telemetry", "temp_mss",       "°C",  "chipTemperature.mss",               "칩 온도: 미디어 서브시스템"),
    P("telemetry", "temp_upa",       "°C",  "chipTemperature.upa",               "칩 온도: SHAVE 영역"),
    P("telemetry", "temp_dss",       "°C",  "chipTemperature.dss",               "칩 온도: DDR 서브시스템"),
    P("telemetry", "temp_avg",       "°C",  "chipTemperature.average",           "칩 평균 온도"),
    P("telemetry", "cpu_css_pct",    "%",   "leonCssCpuUsage.average",           "LEON CSS 코어 사용률"),
    P("telemetry", "cpu_mss_pct",    "%",   "leonMssCpuUsage.average",           "LEON MSS 코어 사용률"),
    P("telemetry", "ddr_used_mb",    "MB",  "ddrMemoryUsage.used",               "DDR 사용량"),
    P("telemetry", "ddr_total_mb",   "MB",  "ddrMemoryUsage.total",              "DDR 전체"),
    P("telemetry", "cmx_used_kb",    "KB",  "cmxMemoryUsage.used",               "CMX(온칩 SRAM) 사용량"),
    P("telemetry", "cmx_total_kb",   "KB",  "cmxMemoryUsage.total",              "CMX 전체"),
    P("telemetry", "css_heap_used_kb", "KB", "leonCssMemoryUsage.used",          "LEON CSS 힙 사용량"),
    P("telemetry", "css_heap_total_kb", "KB", "leonCssMemoryUsage.total",        "LEON CSS 힙 전체"),
    P("telemetry", "mss_heap_used_kb", "KB", "leonMssMemoryUsage.used",          "LEON MSS 힙 사용량"),
    P("telemetry", "mss_heap_total_kb", "KB", "leonMssMemoryUsage.total",        "LEON MSS 힙 전체"),
]

FILES = ("session", "frames", "detections", "telemetry")


def columns(file):
    return [p.name for p in CATALOG if p.file == file]


def unique_names():
    """파일 사이에 겹치는 결합 키(t_s, seq, ts_device_s)는 한 번만 센다."""
    return sorted({p.name for p in CATALOG})


def to_markdown():
    rows = ["| 파일 | 이름 | 단위 | 출처 | 설명 |", "| --- | --- | --- | --- | --- |"]
    rows += [f"| {p.file} | `{p.name}` | {p.unit} | `{p.source}` | {p.desc} |" for p in CATALOG]
    return "\n".join(rows)


if __name__ == "__main__":
    if "--md" in sys.argv:
        print(to_markdown())
    else:
        for f in FILES:
            print(f"{f:<11} {len(columns(f)):>3}")
        print(f"{'고유 파라미터':<11} {len(unique_names()):>3}")
