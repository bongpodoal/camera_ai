#!/usr/bin/env python3
# ============================================================================
# OAK-D에서 예제 YOLOv6n 모델을 돌리는 "최소 코드".
# 화면 표시, FPS 계산, 파일 기록 같은 건 하나도 없다 — 오직
#   1) 모델을 칩에 올리고
#   2) 칩이 보내주는 검출 결과를 받는 것
# 이 두 가지만 한다. 한 줄씩 무슨 일을 하는지 전부 설명을 달았다.
#
# 실행:
#   python3 minimal_example/run_yolov6n.py            # 기본 IP(169.254.1.222)로 접속
#   python3 minimal_example/run_yolov6n.py 169.254.1.222   # IP를 직접 줄 수도 있음
#   (끝내려면 키보드에서 Ctrl+C)
# ============================================================================

import sys                # 터미널에서 준 IP 같은 실행 인자를 읽으려고 씀
import depthai as dai      # OAK-D 카메라를 다루는 라이브러리. 이게 이 코드의 전부다


# ----------------------------------------------------------------------------
# 1단계. 어떤 장치에 연결할지 정한다
# ----------------------------------------------------------------------------
# sys.argv 는 ["파일이름", "첫번째 인자", ...] 식으로 들어온다.
# 즉 sys.argv[1] 은 터미널에서 파일 이름 뒤에 적은 첫 번째 값 (여기선 IP 주소).
# 아무것도 안 적었으면 len(sys.argv)가 1뿐이라, 뒤의 기본값 "169.254.1.222"를 쓴다.
if len(sys.argv) > 1:
    device_ip = sys.argv[1]
else:
    device_ip = "169.254.1.222"   # 이 프로젝트의 OAK-D가 고정으로 쓰는 IP (링크로컬)

# dai.DeviceInfo(ip) : "이 IP 주소에 있는 장치"라는 뜻의 정보 객체를 만든다.
# dai.Device(...)   : 그 정보를 가지고 실제로 장치에 연결한다.
# (자동으로 장치를 찾게 둘 수도 있지만, 이 카메라는 부팅 중일 때 자동 탐색이 자주 실패해서
#  항상 IP를 직접 지정한다.)
device = dai.Device(dai.DeviceInfo(device_ip))
print(f"장치 연결 성공: {device_ip}")


# ----------------------------------------------------------------------------
# 2단계. 파이프라인을 만든다
# ----------------------------------------------------------------------------
# "파이프라인"은 카메라 → 신경망 → 결과 로 이어지는 처리 흐름을 미리 설계해두는 것이다.
# with 문을 쓰면, 이 블록이 끝날 때 파이프라인이 알아서 깨끗하게 정리(종료)된다.
with dai.Pipeline(device) as pipeline:

    # --- 카메라 노드 ---
    # pipeline.create(dai.node.Camera) : "카메라"라는 부품 하나를 파이프라인에 추가한다.
    # .build() : 그 부품을 실제로 동작 가능한 상태로 완성한다 (기본 카메라 센서를 그대로 사용).
    camera = pipeline.create(dai.node.Camera).build()

    # --- 신경망(검출망) 노드 ---
    # dai.NNModelDescription("yolov6-nano") : "yolov6-nano"라는 이름의 예제 모델을 쓰겠다는 표시.
    #   이 이름만 주면, 아래 .build()가 호출되는 순간 depthai가 알아서
    #   Luxonis 모델 저장소에서 이 모델 파일(NNArchive)을 인터넷으로 받아온다
    #   (한 번 받으면 컴퓨터에 저장돼서, 다음부터는 다시 안 받는다).
    # pipeline.create(dai.node.DetectionNetwork) : "물체를 찾아내는 신경망" 부품을 추가한다.
    # .build(camera, 모델) : 그 신경망에 "카메라 영상을 입력으로 쓰고, 이 모델로 추론해라" 라고
    #   연결·설정을 끝내는 것. 이 한 줄이 끝나면 모델이 실제로 OAK-D 칩(Myriad X) 안에 올라간다.
    #   이후 카메라 프레임 크기 줄이기 → 신경망 계산 → 박스 정리(NMS)까지
    #   전부 칩 안에서 알아서 처리되고, 우리는 그 결과만 받으면 된다.
    detection_network = pipeline.create(dai.node.DetectionNetwork).build(
        camera, dai.NNModelDescription("yolov6-nano")
    )

    # --- 출력 큐 두 개 ---
    # "큐"는 칩이 보낸 결과를 순서대로 쌓아두는 우편함 같은 것이다.
    # 우리는 그 우편함에서 하나씩 꺼내 쓰면 된다.
    #
    # passthrough : 신경망이 실제로 봤던 영상 프레임 (여기선 화면에 안 그리지만, 그래도
    #               반드시 큐를 만들어서 계속 꺼내가야 한다. 안 그러면 칩 안에 데이터가
    #               쌓여서 장치가 스스로 연결을 끊어버린다 — 실제로 겪은 문제라 꼭 필요함).
    frame_queue = detection_network.passthrough.createOutputQueue()
    # out : 신경망이 찾아낸 물체 목록 (클래스 이름, 확신도, 박스 위치)이 나오는 곳.
    detection_queue = detection_network.out.createOutputQueue()

    # getClasses() : 이 모델이 구분할 수 있는 클래스 이름 목록을 가져온다.
    # 예: 0번=person, 2번=car, 9번=traffic light ... (COCO 데이터셋 80종)
    class_names = detection_network.getClasses()

    # --- 파이프라인 시작 ---
    # 지금까지는 "이렇게 하겠다"고 설계만 한 것이고, start()를 불러야 실제로 동작을 시작한다.
    pipeline.start()
    print("파이프라인 시작. 검출 결과를 기다리는 중... (Ctrl+C로 종료)")

    # ------------------------------------------------------------------------
    # 3단계. 결과를 계속 받아온다
    # ------------------------------------------------------------------------
    # pipeline.isRunning() : 파이프라인이 아직 살아있는 동안 계속 반복한다.
    while pipeline.isRunning():
        # .get() : 큐에 새 데이터가 올 때까지 기다렸다가 하나를 꺼낸다.
        # 순서를 맞추려고 프레임 큐도 반드시 하나 꺼내준다 (안 꺼내면 위에서 말한 대로
        # 칩 내부에 쌓여서 장치가 끊긴다).
        frame_queue.get()
        detections = detection_queue.get()

        # detections.detections : 이번에 찾아낸 물체들의 목록.
        # 각 물체(detection)마다 다음 값들이 이미 다 계산되어 들어있다 (우리가 계산 안 해도 됨):
        #   detection.label       -> 클래스 번호 (예: 0)
        #   detection.confidence  -> 확신도 (0.0 ~ 1.0)
        #   detection.xmin/ymin/xmax/ymax -> 박스 위치 (화면 비율로 0~1 사이 값)
        for detection in detections.detections:
            name = class_names[detection.label]
            confidence_percent = int(detection.confidence * 100)
            print(f"  검출: {name} ({confidence_percent}%)")
