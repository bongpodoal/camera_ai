#!/usr/bin/env python3
"""detection_network_original.py 실행용 사본. 차이: 장치를 IP로 지정.
    python3 06_oakd_chip/run_example.py [IP]   (q로 종료)
"""

from pathlib import Path
import cv2
import depthai as dai
import numpy as np
import time

import sys

# [변경] 원본과 다른 곳은 이 3줄뿐: 자동 탐색 대신 IP로 장치 지정 (이 PoE 구성에선 자동 탐색 실패)
IP = sys.argv[1] if len(sys.argv) > 1 else "169.254.1.222"
# dai.DeviceInfo(IP) : "이 IP에 있는 장치"라고 못박아 알려준다. 자동 탐색(mDNS/브로드캐스트)은
#   PoE 장치가 부팅 중일 때는 응답이 없어 실패하는 경우가 있어서, 확실하게 IP로 붙는다.
device = dai.Device(dai.DeviceInfo(IP))

# ============================== 여기서부터 "NNArchive를 실제로 OAK-D 칩에 올리는" 부분 ==============================
# Create pipeline
# dai.Pipeline(device) : 이 장치 위에서 실행될 처리 그래프(파이프라인)를 새로 만든다.
#   with 블록을 벗어나면 파이프라인 리소스가 자동 정리된다.
with dai.Pipeline(device) as pipeline:
    # 1) 카메라 노드: 장치의 RGB 센서를 하나의 파이프라인 노드로 등록한다.
    #    .build()는 기본 소켓(CAM_A)·기본 해상도로 카메라를 실제로 구성하는 단계다.
    cameraNode = pipeline.create(dai.node.Camera).build()

    # 2) 검출망 노드: 여기서 "모델을 칩에 올리는" 실제 동작이 일어난다.
    #    dai.NNModelDescription("yolov6-nano")는 모델 이름만 준 것 — 내부적으로
    #    05_nnarchive/fetch_example.py의 dai.getModelFromZoo(...)와 똑같은 다운로드를
    #    자동으로 수행해 NNArchive를 받아온다 (이미 받았으면 캐시 재사용).
    #    .build(cameraNode, model)이 하는 일:
    #      - NNArchive 안의 config.json으로 전처리(scale/mean)·후처리(parser=yolov6r2,
    #        conf/IoU 문턱, 클래스 수)를 읽는다
    #      - superblob 헤더를 보고 장치의 여유 SHAVE 코어 수에 맞는 블롭(기본+패치)을 골라 조립
    #      - 그 블롭을 장치로 전송해 Myriad X에 적재하고, cameraNode 출력을 입력으로 연결
    #    이 한 줄 이후로는 카메라 프레임 리사이즈 → 추론 → YOLO 디코딩 → NMS까지
    #    전부 칩(Myriad X) 안에서 일어난다. 호스트는 관여하지 않는다.
    detectionNetwork = pipeline.create(dai.node.DetectionNetwork).build(cameraNode, dai.NNModelDescription("yolov6-nano"))
    labelMap = detectionNetwork.getClasses()  # 칩이 아는 클래스 이름 목록 (config.json 유래, 예: COCO 80종)

    # 3) 출력 큐: 칩이 만든 결과를 호스트가 꺼내볼 "우편함"을 각각 만든다.
    #    passthrough = 신경망이 실제로 처리한 프레임 원본 (그림 표시·기록용)
    #    out         = 검출 결과 (클래스·신뢰도·박스), 디코딩·NMS까지 끝난 최종본
    #    주의(실측, 06_oakd_chip/README.md): 이 큐들을 만들지 않거나 계속 읽지 않으면
    #    장치 내부에 데이터가 쌓여 keepalive ping을 놓치고 연결이 끊긴다.
    qRgb = detectionNetwork.passthrough.createOutputQueue()
    qDet = detectionNetwork.out.createOutputQueue()

    # 4) 파이프라인 시작: 지금까지 구성만 해둔 그래프를 실제로 장치에서 돌리기 시작한다.
    #    이 시점에 장치가 한 번 재부팅하듯 몇 초간 링크가 끊겼다 돌아온다 (실측).
    pipeline.start()
    # ============================== 여기부터는 "호스트가 결과를 받아 쓰는" 부분 (아래 while 루프) ==============================

    frame = None
    detections = []
    startTime = time.monotonic()
    counter = 0
    color2 = (255, 255, 255)

    # nn data, being the bounding box locations, are in <0..1> range - they need to be normalized with frame width/height
    def frameNorm(frame, bbox):
        normVals = np.full(len(bbox), frame.shape[0])
        normVals[::2] = frame.shape[1]
        return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)

    def displayFrame(name, frame):
        color = (255, 0, 0)
        for detection in detections:
            bbox = frameNorm(
                frame,
                (detection.xmin, detection.ymin, detection.xmax, detection.ymax),
            )
            cv2.putText(
                frame,
                labelMap[detection.label],
                (bbox[0] + 10, bbox[1] + 20),
                cv2.FONT_HERSHEY_TRIPLEX,
                0.5,
                255,
            )
            cv2.putText(
                frame,
                f"{int(detection.confidence * 100)}%",
                (bbox[0] + 10, bbox[1] + 40),
                cv2.FONT_HERSHEY_TRIPLEX,
                0.5,
                255,
            )
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
        # Show the frame
        cv2.imshow(name, frame)

    # --- 아래부터 호스트 쪽 최소 예제 (본격적인 기록용 코드는 07_host_output/edge_logger.py) ---
    lastPrintTime = 0.0
    while pipeline.isRunning():
        # qRgb.get() / qDet.get() : 큐가 빌 때까지 기다렸다가(blocking) 하나씩 꺼낸다.
        #   프레임과 검출결과는 별도 큐라 순서가 딱 맞물려 오지 않을 수 있다 —
        #   이 데모는 "최신 값"만 화면에 겹쳐 그리는 단순한 방식이라 seq로 짝을 맞추지 않는다.
        #   (edge_logger.py는 seq 번호로 프레임↔검출을 정확히 짝지어 기록한다.)
        inRgb: dai.ImgFrame = qRgb.get()
        inDet: dai.ImgDetections = qDet.get()
        if inRgb is not None:
            frame = inRgb.getCvFrame()  # 장치가 보낸 압축/raw 프레임을 OpenCV BGR 배열로 변환
            cv2.putText(
                frame,
                "NN fps: {:.2f}".format(counter / (time.monotonic() - startTime)),
                (2, frame.shape[0] - 4),
                cv2.FONT_HERSHEY_TRIPLEX,
                0.4,
                color2,
            )

        if inDet is not None:
            # inDet.detections : 이미 칩에서 디코딩·NMS까지 끝난 박스 리스트.
            #   각 원소가 label(클래스 번호)·confidence·xmin/ymin/xmax/ymax(정규화 0~1)를 가진다.
            #   호스트는 이 값을 그리기만 할 뿐, 신경망 출력 텐서를 직접 해석하지 않는다.
            detections = inDet.detections
            counter += 1

        if frame is not None:
            displayFrame("rgb", frame)
            now = time.monotonic()
            if now - lastPrintTime >= 1.0:
                print("FPS: {:.2f}".format(counter / (now - startTime)))
                lastPrintTime = now
        if cv2.waitKey(1) == ord("q"):
            # 종료 시 장치가 크래시 덤프를 남기는 경우가 잦다 (실측, README.md).
            # 데이터 유실은 없지만 다음 실행 전 15~20초 정도 장치가 복구될 시간을 준다.
            pipeline.stop()
            break
