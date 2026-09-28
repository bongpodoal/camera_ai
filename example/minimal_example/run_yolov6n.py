#!/usr/bin/env python3
# ============================================================================
# OAK-D에서 예제 YOLOv6n 모델을 돌리는 "최소 코드".
#   1) 카메라를 자동으로 찾아 연결하고
#   2) 모델을 칩에 올리고
#   3) 칩이 보내주는 검출 결과를 받아 화면에 그리고
#   4) 받은 데이터를 data_logger.py 로 시간축 기록(FPS·토출 주기)하고
#   5) 처리한 이미지를 image_saver.py 로 1초에 5장씩 저장한다.
# 한 줄씩 무슨 일을 하는지 전부 설명을 달았다.
#
# 실행:
#   python3 minimal_example/run_yolov6n.py                 # 카메라를 자동으로 찾아 접속
#   python3 minimal_example/run_yolov6n.py 169.254.1.222   # IP를 직접 줄 수도 있음
#   python3 minimal_example/run_yolov6n.py --duration 300  # 5분 뒤 자동 종료
#   (끝내려면 화면 창에서 q, 또는 터미널에서 Ctrl+C)
#   기록은 minimal_example/runs/<날짜_시각>/ 에, 처리한 이미지는 그 안의 images/ 에 저장된다.
# ============================================================================

import argparse           # 실행 인자(IP, --duration 등)를 읽으려고 씀
import subprocess         # 네트워크 프로필을 바꾸는 명령(nmcli)을 실행하려고 씀
import sys                # 카메라를 못 찾았을 때 프로그램을 끝내려고 씀 (sys.exit)
import time               # 카메라를 다시 찾기 전에 잠깐 기다리려고 씀
import cv2                # 카메라 화면을 창에 띄우고 박스를 그리려고 씀 (OpenCV)
import depthai as dai      # OAK-D 카메라를 다루는 라이브러리
from data_logger import DataLogger   # 같은 폴더의 data_logger.py : 토출 데이터를 시간축으로 기록
from image_saver import ImageSaver    # 같은 폴더의 image_saver.py : 처리한 이미지를 1초에 N장 저장


# ----------------------------------------------------------------------------
# 1단계. 카메라를 찾아서 연결한다
# ----------------------------------------------------------------------------
# 예전에는 IP(169.254.1.222)를 코드에 적어두고 그 주소로만 붙었다. 그런데 카메라가 재부팅하며
# 이더넷이 잠깐 끊기면, PC의 다른 네트워크 프로필(LIDAR)이 그 포트를 가져가 버려서
# 카메라가 안 보이는 일이 자주 생겼다. 그래서 이제는 실행할 때마다 카메라를 직접 찾는다.
def find_camera(retries=15):
    for attempt in range(retries):
        # getAllAvailableDevices() : 지금 네트워크/USB에서 보이는 OAK 장치 목록을 돌려준다.
        devices = dai.Device.getAllAvailableDevices()
        if devices:
            return devices[0]          # 찾았으면 첫 번째 장치 정보(IP 포함)를 쓴다
        if attempt % 5 == 0:
            # 못 찾았으면 이더넷 포트를 카메라용 프로필(oak-poe)로 바꿔준다.
            # (nmcli = 우분투 네트워크 설정 명령. sudo 없이 되도록 미리 설정돼 있다.)
            print("카메라를 찾는 중... (이더넷을 oak-poe 프로필로 전환)")
            subprocess.run(["nmcli", "connection", "up", "oak-poe"], capture_output=True)
        time.sleep(1)                  # 1초 쉬고 다시 찾기 (최대 retries초)
    sys.exit("카메라를 찾지 못했습니다. PoE 케이블/전원을 확인하세요.")


# 실행 인자 읽기 (argparse = 터미널에서 파일 이름 뒤에 적은 값들을 정리해 주는 도구)
#   ip                  : 적으면 그 주소로 바로 접속, 안 적으면 자동으로 찾는다
#   --duration 300      : 300초(5분)가 지나면 저절로 끝낸다. 안 적으면 q를 누를 때까지
#   --images-per-second : 1초에 몇 장 저장할지 (기본 5장)
parser = argparse.ArgumentParser()
parser.add_argument("ip", nargs="?")
parser.add_argument("--duration", type=float)
parser.add_argument("--images-per-second", type=float, default=5)
args = parser.parse_args()

if args.ip:
    device_info = dai.DeviceInfo(args.ip)   # "이 IP 주소에 있는 장치"라는 정보 객체
else:
    device_info = find_camera()

# dai.Device(...) : 그 정보를 가지고 실제로 장치에 연결한다.
device = dai.Device(device_info)
print(f"장치 연결 성공: {device_info.name}")    # .name 에 실제 연결된 IP가 들어있다


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
    # passthrough : 신경망이 실제로 봤던 영상 프레임 (화면에 띄우는 것도 이것. 그리고
    #               반드시 큐를 만들어서 계속 꺼내가야 한다. 안 그러면 칩 안에 데이터가
    #               쌓여서 장치가 스스로 연결을 끊어버린다 — 실제로 겪은 문제라 꼭 필요함).
    frame_queue = detection_network.passthrough.createOutputQueue()
    # out : 신경망이 찾아낸 물체 목록 (클래스 이름, 확신도, 박스 위치)이 나오는 곳.
    detection_queue = detection_network.out.createOutputQueue()

    # --- 시스템 로거 노드 ---
    # 칩 온도·CPU 사용률을 장치가 직접 재서 보내주는 부품. setRate(1.0) = 1초에 한 번.
    # 모델 결과와는 별개로 "카메라가 켜져 있는 동안 칩이 무엇을 보내는지" 기록하려고 추가했다.
    # maxSize=4, blocking=False : 우리가 늦게 꺼내도 장치가 멈추지 않게, 오래된 건 버린다.
    system_logger = pipeline.create(dai.node.SystemLogger)
    system_logger.setRate(1.0)
    system_queue = system_logger.out.createOutputQueue(maxSize=4, blocking=False)

    # getClasses() : 이 모델이 구분할 수 있는 클래스 이름 목록을 가져온다.
    # 예: 0번=person, 2번=car, 9번=traffic light ... (COCO 데이터셋 80종)
    class_names = detection_network.getClasses()

    # --- 기록 시작 ---
    # DataLogger() 를 만들면 runs/날짜_시각/ 폴더가 생기고 기록 준비가 끝난다.
    # 카메라 코드와 따로 실행하지 않는 이유: OAK-D에는 한 번에 한 프로그램만 붙을 수 있어서,
    # 카메라 코드가 받은 메시지를 로거에 그대로 넘겨주는 방식으로 "같이" 돈다.
    logger = DataLogger()
    # 이미지 저장기: 로거가 만든 같은 실행 폴더 안에 images/ 폴더를 만들어 저장한다.
    saver = ImageSaver(logger.folder / "images", args.images_per_second)

    # --- 파이프라인 시작 ---
    # 지금까지는 "이렇게 하겠다"고 설계만 한 것이고, start()를 불러야 실제로 동작을 시작한다.
    pipeline.start()
    # --duration 을 줬으면 "지금 + 그 초"를 끝낼 시각으로 정해둔다.
    end_time = time.monotonic() + args.duration if args.duration else None
    print("파이프라인 시작. 검출 결과를 기다리는 중... (q 또는 Ctrl+C로 종료)")

    # ------------------------------------------------------------------------
    # 3단계. 결과를 계속 받아와서 기록하고 화면에 그린다
    # ------------------------------------------------------------------------
    # try/finally : q로 끝내든 Ctrl+C로 끝내든 오류가 나든, 마지막에 logger.close()가
    # 반드시 불려서 기록 파일이 닫히고 요약(summary.json)이 저장되게 한다.
    try:
        # pipeline.isRunning() : 파이프라인이 아직 살아있는 동안 계속 반복한다.
        while pipeline.isRunning():
            # .get() : 큐에 새 데이터가 올 때까지 기다렸다가 하나를 꺼낸다.
            # 프레임 큐도 반드시 꺼내준다 (안 꺼내면 칩 내부에 쌓여서 장치가 끊긴다).
            # 꺼내자마자 logger.log(종류, 메시지) 로 넘겨서 받은 시각·주기를 기록한다.
            frame_message = frame_queue.get()
            logger.log("frame", frame_message)
            detections = detection_queue.get()
            logger.log("detections", detections)     # 이게 1개 올 때마다 모델 연산 1번
            # tryGetAll() : 기다리지 않고 "지금까지 쌓인 것"만 전부 꺼낸다 (1초에 1개꼴로 옴).
            for system_message in system_queue.tryGetAll():
                logger.log("system", system_message)

            # getCvFrame() : 칩이 보낸 프레임을 OpenCV가 그릴 수 있는 이미지 배열로 바꾼다.
            frame = frame_message.getCvFrame()
            height, width = frame.shape[:2]

            # detections.detections : 이번에 찾아낸 물체들의 목록.
            # 각 물체(detection)마다 다음 값들이 이미 다 계산되어 들어있다 (우리가 계산 안 해도 됨):
            #   detection.label       -> 클래스 번호 (예: 0)
            #   detection.confidence  -> 확신도 (0.0 ~ 1.0)
            #   detection.xmin/ymin/xmax/ymax -> 박스 위치 (화면 비율로 0~1 사이 값)
            for detection in detections.detections:
                name = class_names[detection.label]
                confidence_percent = int(detection.confidence * 100)

                # 박스 위치는 0~1 비율이라, 화면 크기(픽셀)를 곱해 실제 좌표로 바꾼다.
                x1, y1 = int(detection.xmin * width), int(detection.ymin * height)
                x2, y2 = int(detection.xmax * width), int(detection.ymax * height)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)     # 파란 박스
                cv2.putText(frame, f"{name} {confidence_percent}%", (x1 + 5, y1 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)  # 흰 글씨

            # 박스까지 그린 이미지를 저장기에 넘긴다. 0.2초마다 한 장씩만 실제로 저장된다.
            # 칩 순번(seq)을 같이 넘겨서 파일 이름에 넣는다 → events.csv 의 같은 행을 찾을 수 있다.
            saver.save(frame, frame_message.getSequenceNum())

            # imshow : "YOLOv6n" 이라는 창에 이미지를 띄운다.
            # waitKey(1) : 1ms 동안 키 입력을 확인한다 (이걸 불러야 창이 실제로 그려진다).
            cv2.imshow("YOLOv6n", frame)
            if cv2.waitKey(1) == ord("q"):
                break
            # 정해둔 시간이 지났으면 끝낸다.
            if end_time and time.monotonic() >= end_time:
                print(f"{args.duration:.0f}초가 지나 종료합니다.")
                break
    except KeyboardInterrupt:
        pass                          # Ctrl+C 는 정상 종료로 취급
    finally:
        logger.close()                # 파일 닫고 요약 출력·저장
        saver.close()                 # 저장한 이미지 장 수 출력

cv2.destroyAllWindows()               # 띄웠던 창 닫기
