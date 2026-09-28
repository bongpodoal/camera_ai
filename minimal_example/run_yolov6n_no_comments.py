#!/usr/bin/env python3
import sys
import depthai as dai

if len(sys.argv) > 1:
    device_ip = sys.argv[1]
else:
    device_ip = "169.254.1.222"

device = dai.Device(dai.DeviceInfo(device_ip))
print(f"장치 연결 성공: {device_ip}")

with dai.Pipeline(device) as pipeline:
    camera = pipeline.create(dai.node.Camera).build()

    detection_network = pipeline.create(dai.node.DetectionNetwork).build(
        camera, dai.NNModelDescription("yolov6-nano")
    )

    frame_queue = detection_network.passthrough.createOutputQueue()
    detection_queue = detection_network.out.createOutputQueue()

    class_names = detection_network.getClasses()

    pipeline.start()
    print("파이프라인 시작. 검출 결과를 기다리는 중... (Ctrl+C로 종료)")

    while pipeline.isRunning():
        frame_queue.get()
        detections = detection_queue.get()

        for detection in detections.detections:
            name = class_names[detection.label]
            confidence_percent = int(detection.confidence * 100)
            print(f"  검출: {name} ({confidence_percent}%)")
