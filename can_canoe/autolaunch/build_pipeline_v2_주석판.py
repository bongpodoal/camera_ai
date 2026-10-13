"""자동 launch 시험용 파이프라인 (DepthAI **v2**). 카메라 → YOLO 검출 → 칩 안 Script 가 UDP 로 결과를 내보낸다. PC 는 필요 없다.

DepthAI v3 는 RVC2 의 standalone(플래시 후 전원만으로 자동 실행)을 지원하지 않는다. v2 의 DeviceBootloader.flash 로 플래시하는 방식만 가능하며, 이 폴더는 그 시험용이다.
(맥에서 depthai 2.33 에 API 이름이 있는 것까지만 확인했고, 실제 카메라 동작은 미검증이다.)

패킷 형식 (UDP, 한 장에 JSON 한 줄):
    {"n": 칩이 센 검출 프레임 수, "t": 칩 시계 초(촬영→송신 지연 계산용), "d": [[클래스, 신뢰도, xmin, ymin, xmax, ymax], ...]}
"""
# DepthAI v2 라이브러리. 호스트 PC 에서 파이프라인(노드 연결 구조)을 조립할 때만 쓰고, 카메라에는 조립된 결과가 올라간다.
import depthai as dai

# 2026-10-12 수정: ⓪ v2 Script 의 검출 메시지에는 getTimestampDevice() 가 없고 getTimestamp() 가 칩 시계(Clock.now()와 같은 시계)다 → 칩 지연은 Clock.now() - det.getTimestamp()
#                   ① 칩 Script 는 기본 LEON_MSS 에서 돌고 거기엔 socket 이 없다 → setProcessor(LEON_CSS) 필요
#                   ② 전원 직후에는 네트워크가 아직 안 올라와 첫 sendto 가 예외를 내고, 예외가 나면 Script 와 앱이 같이 죽어 부트로더로 돌아간다 → try/except 로 재시도
# ── 아래 SCRIPT 는 '카메라 칩 안에서' 부팅 때마다 도는 파이썬 코드(Script 노드)다. 문자열 안에 주석을 넣으면 카메라에 올라가는 코드가 바뀌므로
#    줄별 설명은 문자열 밖(여기)에 적는다. {ip}·{port} 는 build() 에서 .format() 으로 채워지고, JSON 의 중괄호는 {{ }} 로 써서 .format() 이 건드리지 않게 한다.
#  줄 1  import socket, time, json            : UDP 송신용 socket, JSON 변환용 json 을 가져온다 (time 은 쓰이지 않음). socket 은 LEON_CSS 프로세서에만 있다.
#  줄 2  dest = ("{ip}", {port})              : 결과를 받을 PC 의 (IP, 포트). 플래시할 때 정해져 저장되므로 바꾸려면 다시 플래시해야 한다.
#  줄 3  sock = None                           : UDP 소켓. 처음엔 없음(None)이고, 첫 송신 때 만든다.
#  줄 4  n = 0                                  : 칩이 처리한 검출 메시지(프레임) 수 카운터.
#  줄 5  while True:                            : 전원이 켜져 있는 동안 계속 반복.
#  줄 6  det = node.io['det'].get()             : 신경망(YoloDetectionNetwork)이 보낸 검출 결과를 기다렸다가 받는다(결과가 올 때까지 멈춰 있음).
#  줄 7  n += 1                                 : 프레임 수 1 증가.
#  줄 8  d = [[x.label, ...] for x in det.detections] : 검출마다 [클래스, 신뢰도(소수 3자리), xmin, ymin, xmax, ymax(0~1 정규화, 소수 4자리)] 리스트로 만든다.
#  줄 9~12 try: lat = (Clock.now() - det.getTimestamp()) ... : 칩 시계 지금 시각 − 이 프레임의 촬영 시각 = 칩 지연(ms). 읽기에 실패하면 -1.0.
#  줄 13~16 try: ... sock.sendto(json.dumps({"n", "lat_ms", "d"}).encode(), dest) : 소켓이 없으면 만들고, {"n": 프레임 번호, "lat_ms": 칩 지연, "d": 검출 목록} 을 JSON 으로
#           만들어 UDP 한 패킷으로 PC 에 보낸다.
#  줄 17~19 except Exception as e: node.warn(...); sock = None : 전원 직후엔 네트워크가 아직 안 올라와 첫 sendto 가 예외를 낸다. 예외가 Script 를 죽이면 앱이 부트로더로 돌아가므로
#           경고만 남기고 소켓을 버려(None) 다음 반복에서 다시 만들어 재시도한다. (이 try/except 와 LEON_CSS 가 standalone UDP 동작의 필수 조건이었다)
#  참고: 위 모듈 docstring 의 패킷 형식 설명에는 "t" 라고 되어 있지만 실제 코드가 보내는 키는 "lat_ms" 이다(docstring 이 오래됨).
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


# 파이프라인을 조립해 돌려주는 함수. 인자: 블롭 파일, 결과를 받을 PC 의 IP·포트, 입력 크기, 클래스 수, 신뢰도·IoU 문턱, fps.
def build(blob_path, dest_ip, dest_port=5005, width=416, height=416, num_classes=4, conf=0.35, iou=0.5, fps=5):
    """blob_path: 칩에 올릴 블롭 (예: 우리 신호등 6 SHAVE 변환본의 .blob). YOLOv8 형식(앵커 없음) 가정."""
    # 빈 파이프라인(노드와 연결을 담는 그릇)을 만든다.
    p = dai.Pipeline()
    # 컬러 카메라 노드를 만든다(영상 입력).
    cam = p.create(dai.node.ColorCamera)
    # 신경망에 넣을 미리보기 영상 크기(기본 416×416).
    cam.setPreviewSize(width, height)
    # 영상을 채널별 평면(planar, CHW) 배열로 출력. 신경망 입력 형식에 맞춘 것.
    cam.setInterleaved(False)
    # 채널 순서를 BGR 로(학습·변환 때와 같게).
    cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    # 카메라 프레임레이트(기본 5 fps).
    cam.setFps(fps)
    # YOLO 검출 신경망 노드. 칩에서 신경망 실행 + 박스 해석(디코딩) + NMS 까지 해 준다.
    nn = p.create(dai.node.YoloDetectionNetwork)
    # 칩에 올릴 신경망 파일(.blob)의 경로. 이 파일이 플래시에 함께 저장된다.
    nn.setBlobPath(blob_path)
    # 클래스 수(예: 신호등 4개).
    nn.setNumClasses(num_classes)
    # 박스 좌표 수 4개(x, y, 폭, 높이).
    nn.setCoordinateSize(4)
    # 앵커 없음 = 앵커 없는 YOLOv8 형식으로 해석하라는 설정(실제 맞는지는 신호등이 보이는 장면에서 미확정).
    nn.setAnchors([])               # 앵커 없는 YOLOv8 형식 (미검증 가정)
    # 앵커 마스크도 비움(위와 같은 이유).
    nn.setAnchorMasks({})
    # 신뢰도가 이 값(기본 0.35) 미만인 박스는 버린다.
    nn.setConfidenceThreshold(conf)
    # NMS 문턱(기본 0.5): 겹침이 이 값 이상인 박스는 하나만 남긴다.
    nn.setIouThreshold(iou)
    # 신경망 입력 큐를 비차단으로: 신경망이 바쁘면 카메라 프레임을 막지 않고 버린다.
    nn.input.setBlocking(False)
    # 입력 큐 크기 1: 프레임이 칩 안에 쌓이지 않게 해 항상 최신 프레임만 처리(지연 누적 방지).
    nn.input.setQueueSize(1)        # 최신화 큐: 칩 안에서 프레임이 쌓이지 않게
    # 카메라 미리보기 출력 → 신경망 입력으로 연결.
    cam.preview.link(nn.input)
    # Script 노드(칩 안에서 파이썬 코드를 실행하는 노드)를 만든다.
    script = p.create(dai.node.Script)
    # Script 를 LEON_CSS 코어에서 실행. socket 모듈은 이 코어에만 있어서 필수(기본 LEON_MSS 에는 없음).
    script.setProcessor(dai.ProcessorType.LEON_CSS)   # socket 모듈은 LEON_CSS 에서만 있다
    # SCRIPT 문자열의 {ip}, {port} 를 실제 값으로 채워 Script 노드에 넣는다. 이 코드가 플래시에 저장된다.
    script.setScript(SCRIPT.format(ip=dest_ip, port=dest_port))
    # 신경망 출력(검출 결과) → Script 의 입력 'det' 로 연결(SCRIPT 의 node.io['det']).
    nn.out.link(script.inputs["det"])
    # Script 입력도 비차단: Script 가 느려도 신경망을 막지 않는다.
    script.inputs["det"].setBlocking(False)
    # Script 입력 큐 크기 1: 최신 결과만 보낸다.
    script.inputs["det"].setQueueSize(1)
    # 완성한 파이프라인을 돌려준다(flash_v2.py 가 이것을 카메라 플래시에 쓴다).
    return p
