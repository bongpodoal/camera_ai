#!/usr/bin/env python3
# ============================================================================
# ⑦ 호스트 — ⑥ 실행에 "토출 데이터 기록"과 "처리한 이미지 저장"을 붙인 버전.
#
# 같은 폴더의 두 모듈을 불러 같이 돌린다 (OAK-D 는 한 프로그램만 연결할 수 있어서
# 기록 프로그램을 따로 실행하지 않고, 받은 메시지를 그대로 넘긴다):
#   data_logger.py : 받은 메시지마다 시각·주기·내용 → events.csv, 초당 개수 → fps.csv, 요약 → summary.json
#   image_saver.py : 박스를 그린 이미지를 1초에 N장(기본 5) → images/
# 저장 위치: 07_host_output/runs/<날짜_시각>/
#
# 실행:  python3 07_host_output/run_with_logging.py                  (q 로 끝낼 때까지)
#        python3 07_host_output/run_with_logging.py --duration 300   (5분 뒤 자동 종료)
#        옵션: [IP] --images-per-second 5
# ============================================================================

import argparse                     # 실행 인자(IP, --duration 등)를 읽으려고
import subprocess
import sys
import time
from pathlib import Path

import cv2
import depthai as dai

from data_logger import DataLogger  # 같은 폴더의 data_logger.py
from image_saver import ImageSaver  # 같은 폴더의 image_saver.py

ROOT = Path(__file__).resolve().parents[1]              # traffic_light 폴더
archive_path = ROOT / "05_nnarchive" / "traffic_light-512x288.tar.xz"


def find_camera(retries=15):
    """보이는 OAK 장치를 찾는다. 못 찾으면 이더넷을 카메라용 프로필(oak-poe)로 바꾸고 다시 찾는다."""
    for attempt in range(retries):
        devices = dai.Device.getAllAvailableDevices()
        if devices:
            return devices[0]
        if attempt % 5 == 0:
            print("카메라를 찾는 중... (이더넷을 oak-poe 프로필로 전환)")
            subprocess.run(["nmcli", "connection", "up", "oak-poe"], capture_output=True)
        time.sleep(1)
    sys.exit("카메라를 찾지 못했습니다. PoE 케이블/전원을 확인하세요.")


parser = argparse.ArgumentParser()
parser.add_argument("ip", nargs="?")                                # 안 적으면 자동 탐색
parser.add_argument("--duration", type=float)                       # 초. 안 적으면 q 를 누를 때까지
parser.add_argument("--images-per-second", type=float, default=5)   # 1초에 저장할 이미지 수
args = parser.parse_args()

device_info = dai.DeviceInfo(args.ip) if args.ip else find_camera()
device = dai.Device(device_info)
print(f"장치 연결 성공: {device_info.name}")

with dai.Pipeline(device) as pipeline:
    camera = pipeline.create(dai.node.Camera).build()
    detection_network = pipeline.create(dai.node.DetectionNetwork).build(
        camera, dai.NNArchive(str(archive_path))
    )
    frame_queue = detection_network.passthrough.createOutputQueue()
    detection_queue = detection_network.out.createOutputQueue()

    # 칩 온도·CPU 를 1초마다 보내는 노드. 늦게 꺼내도 장치가 멈추지 않게 오래된 건 버린다(blocking=False).
    system_logger = pipeline.create(dai.node.SystemLogger)
    system_logger.setRate(1.0)
    system_queue = system_logger.out.createOutputQueue(maxSize=4, blocking=False)

    class_names = detection_network.getClasses()                        # ['red', 'yellow', 'green', 'off']

    logger = DataLogger()                                               # runs/<날짜_시각>/ 생성
    saver = ImageSaver(logger.folder / "images", args.images_per_second)
    pipeline.start()
    end_time = time.monotonic() + args.duration if args.duration else None
    print("파이프라인 시작 (q 또는 Ctrl+C로 종료)")

    try:
        while pipeline.isRunning():
            # 꺼내자마자 기록기에 넘긴다: 받은 시각과 칩이 붙인 시각으로 토출 주기를 잰다.
            frame_message = frame_queue.get()
            logger.log("frame", frame_message)
            detections = detection_queue.get()
            logger.log("detections", detections)                        # 1개 = 모델 연산 1번
            for system_message in system_queue.tryGetAll():             # 쌓인 것만 기다리지 않고 꺼냄
                logger.log("system", system_message)

            frame = frame_message.getCvFrame()
            height, width = frame.shape[:2]
            for detection in detections.detections:
                x1, y1 = int(detection.xmin * width), int(detection.ymin * height)
                x2, y2 = int(detection.xmax * width), int(detection.ymax * height)
                label = f"{class_names[detection.label]} {int(detection.confidence * 100)}%"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, label, (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # 박스를 그린 이미지를 저장기에 넘긴다 (저장할 차례일 때만 실제로 저장).
            # 파일 이름에 칩 순번(seq)이 들어가서 events.csv 의 같은 행을 찾을 수 있다.
            saver.save(frame, frame_message.getSequenceNum())

            cv2.imshow("Traffic light", frame)
            if cv2.waitKey(1) == ord("q"):
                break
            if end_time and time.monotonic() >= end_time:
                print(f"{args.duration:.0f}초가 지나 종료합니다.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        # 어떻게 끝나든 파일을 닫고 요약을 남긴다.
        logger.close()
        saver.close()

cv2.destroyAllWindows()
