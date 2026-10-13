#!/usr/bin/env python3
"""플래시한 자동 실행 파이프라인을 지운다 (DepthAI v2 환경). 지운 뒤에는 카메라가 평소처럼 PC 연결을 기다린다.

예) python3 clear_v2.py [--camera-ip 169.254.1.222]
"""
# 명령줄 인자를 읽는 표준 라이브러리.
import argparse

# DepthAI v2.
import depthai as dai

# 인자 파서(설명은 맨 위 docstring).
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
# 플래시를 지울 카메라의 IP.
ap.add_argument("--camera-ip", default="169.254.1.222")
# 인자를 읽는다.
a = ap.parse_args()
# 그 카메라의 부트로더에 연결.
bootloader = dai.DeviceBootloader(dai.DeviceInfo(a.camera_ip))
# 플래시에 저장된 파이프라인(자동 실행 앱)을 지운다. 지우면 카메라가 평소처럼 PC 연결을 기다린다.
ok, msg = bootloader.flashClear()
# 성공 여부와 메시지를 출력.
print("지움:", ok, msg)
