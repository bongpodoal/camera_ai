#!/usr/bin/env python3
# ============================================================================
# ⑥ OAK-D 칩 — ⑤의 NNArchive 를 칩에 올려 실행하고, 검출 박스를 화면에 그린다.
#
# 모델 계산, 박스 디코딩, NMS(겹친 박스 정리)는 전부 칩 안에서 끝난다.
# PC(호스트)는 칩이 보낸 결과를 받아 화면에 그리기만 한다.
# 기록·이미지 저장이 붙은 버전은 ⑦ 07_host_output/run_with_logging.py.
#
# 실행:  python3 06_oakd_chip/run_on_chip.py              (카메라 자동 탐색)
#        python3 06_oakd_chip/run_on_chip.py 169.254.1.222  (IP 직접 지정)
#        끝내려면 화면 창에서 q, 또는 터미널에서 Ctrl+C
# ============================================================================

import subprocess                   # 네트워크 프로필을 바꾸는 명령(nmcli)을 실행하려고
import sys                          # 실행 인자(IP) 읽기, 카메라를 못 찾으면 끝내기
import time
from pathlib import Path

import cv2                          # 화면 창과 박스 그리기 (OpenCV)
import depthai as dai               # OAK-D 를 다루는 라이브러리

ROOT = Path(__file__).resolve().parents[1]              # traffic_light 폴더
archive_path = ROOT / "05_nnarchive" / "traffic_light-512x288.tar.xz"


def find_camera(retries=15):
    """보이는 OAK 장치를 찾는다. 못 찾으면 이더넷을 카메라용 프로필(oak-poe)로 바꾸고 다시 찾는다.
    (카메라가 재부팅하는 사이 다른 프로필 LIDAR 가 이더넷을 가져가는 일이 자주 있다.)"""
    for attempt in range(retries):
        devices = dai.Device.getAllAvailableDevices()
        if devices:
            return devices[0]
        if attempt % 5 == 0:
            print("카메라를 찾는 중... (이더넷을 oak-poe 프로필로 전환)")
            subprocess.run(["nmcli", "connection", "up", "oak-poe"], capture_output=True)
        time.sleep(1)
    sys.exit("카메라를 찾지 못했습니다. PoE 케이블/전원을 확인하세요.")


device_info = dai.DeviceInfo(sys.argv[1]) if len(sys.argv) > 1 else find_camera()
device = dai.Device(device_info)
print(f"장치 연결 성공: {device_info.name}")

with dai.Pipeline(device) as pipeline:
    # 카메라 → 신경망. NNArchive 를 넘기면 입력 크기(512×288)에 맞춰 카메라 출력이 자동으로 맞춰지고,
    # config.json 의 head(YOLO, yolov8) 설명대로 칩 위 디코딩이 켜진다.
    camera = pipeline.create(dai.node.Camera).build()
    detection_network = pipeline.create(dai.node.DetectionNetwork).build(
        camera, dai.NNArchive(str(archive_path))
    )

    # 출력 큐. passthrough(신경망이 본 프레임)는 화면에 안 쓰더라도 반드시 꺼내야 한다
    # — 안 꺼내면 칩 안에 쌓여서 장치가 연결을 끊는다.
    frame_queue = detection_network.passthrough.createOutputQueue()
    detection_queue = detection_network.out.createOutputQueue()
    class_names = detection_network.getClasses()        # ['red', 'yellow', 'green', 'off']

    pipeline.start()
    print("파이프라인 시작 (q 또는 Ctrl+C로 종료)")

    try:
        while pipeline.isRunning():
            frame = frame_queue.get().getCvFrame()      # 칩이 보낸 프레임 → OpenCV 이미지
            detections = detection_queue.get()          # 같은 프레임의 검출 결과
            height, width = frame.shape[:2]

            # 박스 좌표(xmin 등)는 0~1 비율이라 화면 크기를 곱해 픽셀로 바꾼다.
            for detection in detections.detections:
                x1, y1 = int(detection.xmin * width), int(detection.ymin * height)
                x2, y2 = int(detection.xmax * width), int(detection.ymax * height)
                label = f"{class_names[detection.label]} {int(detection.confidence * 100)}%"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, label, (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow("Traffic light", frame)
            if cv2.waitKey(1) == ord("q"):              # waitKey 를 불러야 창이 실제로 그려진다
                break
    except KeyboardInterrupt:
        pass

cv2.destroyAllWindows()
