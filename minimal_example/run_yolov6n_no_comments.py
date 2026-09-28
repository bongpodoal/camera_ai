#!/usr/bin/env python3
import argparse
import subprocess
import sys
import time
import cv2
import depthai as dai
from data_logger_no_comments import DataLogger
from image_saver_no_comments import ImageSaver


def find_camera(retries=15):
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
parser.add_argument("ip", nargs="?")
parser.add_argument("--duration", type=float)
parser.add_argument("--images-per-second", type=float, default=5)
args = parser.parse_args()

if args.ip:
    device_info = dai.DeviceInfo(args.ip)
else:
    device_info = find_camera()

device = dai.Device(device_info)
print(f"장치 연결 성공: {device_info.name}")

with dai.Pipeline(device) as pipeline:
    camera = pipeline.create(dai.node.Camera).build()

    detection_network = pipeline.create(dai.node.DetectionNetwork).build(
        camera, dai.NNModelDescription("yolov6-nano")
    )

    frame_queue = detection_network.passthrough.createOutputQueue()
    detection_queue = detection_network.out.createOutputQueue()

    system_logger = pipeline.create(dai.node.SystemLogger)
    system_logger.setRate(1.0)
    system_queue = system_logger.out.createOutputQueue(maxSize=4, blocking=False)

    class_names = detection_network.getClasses()

    logger = DataLogger()
    saver = ImageSaver(logger.folder / "images", args.images_per_second)
    pipeline.start()
    end_time = time.monotonic() + args.duration if args.duration else None
    print("파이프라인 시작. 검출 결과를 기다리는 중... (q 또는 Ctrl+C로 종료)")

    try:
        while pipeline.isRunning():
            frame_message = frame_queue.get()
            logger.log("frame", frame_message)
            detections = detection_queue.get()
            logger.log("detections", detections)
            for system_message in system_queue.tryGetAll():
                logger.log("system", system_message)

            frame = frame_message.getCvFrame()
            height, width = frame.shape[:2]

            for detection in detections.detections:
                name = class_names[detection.label]
                confidence_percent = int(detection.confidence * 100)

                x1, y1 = int(detection.xmin * width), int(detection.ymin * height)
                x2, y2 = int(detection.xmax * width), int(detection.ymax * height)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, f"{name} {confidence_percent}%", (x1 + 5, y1 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            saver.save(frame, frame_message.getSequenceNum())
            cv2.imshow("YOLOv6n", frame)
            if cv2.waitKey(1) == ord("q"):
                break
            if end_time and time.monotonic() >= end_time:
                print(f"{args.duration:.0f}초가 지나 종료합니다.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        logger.close()
        saver.close()

cv2.destroyAllWindows()
