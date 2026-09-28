#!/usr/bin/env python3

import subprocess
import sys
import time
from pathlib import Path

import cv2
import depthai as dai

ROOT = Path(__file__).resolve().parents[1]
archive_path = ROOT / "05_nnarchive" / "traffic_light-512x288.tar.xz"


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


device_info = dai.DeviceInfo(sys.argv[1]) if len(sys.argv) > 1 else find_camera()
device = dai.Device(device_info)
print(f"장치 연결 성공: {device_info.name}")

with dai.Pipeline(device) as pipeline:
    camera = pipeline.create(dai.node.Camera).build()
    detection_network = pipeline.create(dai.node.DetectionNetwork).build(
        camera, dai.NNArchive(str(archive_path))
    )

    frame_queue = detection_network.passthrough.createOutputQueue()
    detection_queue = detection_network.out.createOutputQueue()
    class_names = detection_network.getClasses()

    pipeline.start()
    print("파이프라인 시작 (q 또는 Ctrl+C로 종료)")

    try:
        while pipeline.isRunning():
            frame = frame_queue.get().getCvFrame()
            detections = detection_queue.get()
            height, width = frame.shape[:2]

            for detection in detections.detections:
                x1, y1 = int(detection.xmin * width), int(detection.ymin * height)
                x2, y2 = int(detection.xmax * width), int(detection.ymax * height)
                label = f"{class_names[detection.label]} {int(detection.confidence * 100)}%"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, label, (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow("Traffic light", frame)
            if cv2.waitKey(1) == ord("q"):
                break
    except KeyboardInterrupt:
        pass

cv2.destroyAllWindows()
