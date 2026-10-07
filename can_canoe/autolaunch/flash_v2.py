#!/usr/bin/env python3
"""파이프라인을 카메라 플래시에 써서 **전원이 들어오면 PC 없이 자동 실행**되게 한다 (DepthAI v2 가 설치된 환경에서 실행).

예) python3 flash_v2.py --blob traffic_light-416x416-6shave.blob --dest-ip 169.254.1.10 --dest-port 5005 [--camera-ip 169.254.1.222]
주의: 카메라 설정(플래시)을 바꾼다. 되돌리는 방법 = clear_v2.py. 처음에는 사용자가 카메라 앞에 있을 때 해 볼 것. 실카메라 미검증.
"""
import argparse

import depthai as dai

from build_pipeline_v2 import build

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--blob", required=True)
ap.add_argument("--dest-ip", required=True, help="결과를 받을 PC 의 IP (카메라와 같은 링크의 PC 주소)")
ap.add_argument("--dest-port", type=int, default=5005)
ap.add_argument("--camera-ip", default="169.254.1.222")
ap.add_argument("--width", type=int, default=416)
ap.add_argument("--height", type=int, default=416)
ap.add_argument("--classes", type=int, default=4)
ap.add_argument("--fps", type=float, default=5)
a = ap.parse_args()

pipeline = build(a.blob, a.dest_ip, a.dest_port, a.width, a.height, a.classes, fps=a.fps)
info = dai.DeviceInfo(a.camera_ip)
bootloader = dai.DeviceBootloader(info)
print(f"부트로더 버전: {bootloader.getVersion()}")
bootloader.flash(lambda p: print(f"\r플래시 {p * 100:5.1f}%", end="", flush=True), pipeline)
print("\n완료. 카메라 전원을 껐다 켜면 PC 없이 시작한다. 결과는 UDP 로 온다: python3 listen_udp.py --port", a.dest_port)
