#!/usr/bin/env python3
"""플래시한 자동 실행 파이프라인을 지운다 (DepthAI v2 환경). 지운 뒤에는 카메라가 평소처럼 PC 연결을 기다린다.

예) python3 clear_v2.py [--camera-ip 169.254.1.222]
"""
import argparse

import depthai as dai

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--camera-ip", default="169.254.1.222")
a = ap.parse_args()
bootloader = dai.DeviceBootloader(dai.DeviceInfo(a.camera_ip))
ok, msg = bootloader.flashClear()
print("지움:", ok, msg)
