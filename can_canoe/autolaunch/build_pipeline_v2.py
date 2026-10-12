"""자동 launch 시험용 파이프라인 (DepthAI **v2**). 카메라 → YOLO 검출 → 칩 안 Script 가 UDP 로 결과를 내보낸다. PC 는 필요 없다.

DepthAI v3 는 RVC2 의 standalone(플래시 후 전원만으로 자동 실행)을 지원하지 않는다. v2 의 DeviceBootloader.flash 로 플래시하는 방식만 가능하며, 이 폴더는 그 시험용이다.
(맥에서 depthai 2.33 에 API 이름이 있는 것까지만 확인했고, 실제 카메라 동작은 미검증이다.)

패킷 형식 (UDP, 한 장에 JSON 한 줄):
    {"n": 칩이 센 검출 프레임 수, "t": 칩 시계 초(촬영→송신 지연 계산용), "d": [[클래스, 신뢰도, xmin, ymin, xmax, ymax], ...]}
"""
import depthai as dai

# 2026-10-12 수정: ⓪ v2 Script 의 검출 메시지에는 getTimestampDevice() 가 없고 getTimestamp() 가 칩 시계(Clock.now()와 같은 시계)다 → 칩 지연은 Clock.now() - det.getTimestamp()
#                   ① 칩 Script 는 기본 LEON_MSS 에서 돌고 거기엔 socket 이 없다 → setProcessor(LEON_CSS) 필요
#                   ② 전원 직후에는 네트워크가 아직 안 올라와 첫 sendto 가 예외를 내고, 예외가 나면 Script 와 앱이 같이 죽어 부트로더로 돌아간다 → try/except 로 재시도
SCRIPT = """
import socket, time, json
dest = ("{ip}", {port})
sock = None
n = 0
while True:
    det = node.io['det'].get()
    n += 1
    d = [[x.label, round(x.confidence, 3), round(x.xmin, 4), round(x.ymin, 4), round(x.xmax, 4), round(x.ymax, 4)] for x in det.detections]
    try:
        lat = (Clock.now() - det.getTimestamp()).total_seconds() * 1000
    except Exception:
        lat = -1.0
    try:
        if sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps({{"n": n, "lat_ms": round(lat, 1), "d": d}}).encode(), dest)
    except Exception as e:
        node.warn("send err " + repr(e))
        sock = None
"""


def build(blob_path, dest_ip, dest_port=5005, width=416, height=416, num_classes=4, conf=0.35, iou=0.5, fps=5):
    """blob_path: 칩에 올릴 블롭 (예: 우리 신호등 6 SHAVE 변환본의 .blob). YOLOv8 형식(앵커 없음) 가정."""
    p = dai.Pipeline()
    cam = p.create(dai.node.ColorCamera)
    cam.setPreviewSize(width, height)
    cam.setInterleaved(False)
    cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    cam.setFps(fps)
    nn = p.create(dai.node.YoloDetectionNetwork)
    nn.setBlobPath(blob_path)
    nn.setNumClasses(num_classes)
    nn.setCoordinateSize(4)
    nn.setAnchors([])               # 앵커 없는 YOLOv8 형식 (미검증 가정)
    nn.setAnchorMasks({})
    nn.setConfidenceThreshold(conf)
    nn.setIouThreshold(iou)
    nn.input.setBlocking(False)
    nn.input.setQueueSize(1)        # 최신화 큐: 칩 안에서 프레임이 쌓이지 않게
    cam.preview.link(nn.input)
    script = p.create(dai.node.Script)
    script.setProcessor(dai.ProcessorType.LEON_CSS)   # socket 모듈은 LEON_CSS 에서만 있다
    script.setScript(SCRIPT.format(ip=dest_ip, port=dest_port))
    nn.out.link(script.inputs["det"])
    script.inputs["det"].setBlocking(False)
    script.inputs["det"].setQueueSize(1)
    return p
