#!/usr/bin/env python3
"""파이프라인을 카메라 플래시에 써서 **전원이 들어오면 PC 없이 자동 실행**되게 한다 (DepthAI v2 가 설치된 환경에서 실행).

예) python3 flash_v2.py --blob traffic_light-416x416-6shave.blob --dest-ip 169.254.1.10 --dest-port 5005 [--camera-ip 169.254.1.222]
주의: 카메라 설정(플래시)을 바꾼다. 되돌리는 방법 = clear_v2.py. 처음에는 사용자가 카메라 앞에 있을 때 해 볼 것. 실카메라 미검증.
"""
# 명령줄 인자(--blob 등)를 읽는 표준 라이브러리.
import argparse

# DepthAI v2 (카메라·부트로더 제어).
import depthai as dai

# 같은 폴더의 build_pipeline_v2.py 에서 파이프라인 조립 함수를 가져온다.
from build_pipeline_v2 import build

# 인자 파서를 만든다(설명은 파일 맨 위 docstring).
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
# [필수] 칩에 올릴 신경망 .blob 파일 경로.
ap.add_argument("--blob", required=True)
# [필수] 결과 UDP 를 받을 PC 의 IP(카메라와 같은 링크의 주소).
ap.add_argument("--dest-ip", required=True, help="결과를 받을 PC 의 IP (카메라와 같은 링크의 PC 주소)")
# 결과를 받을 UDP 포트(기본 5005).
ap.add_argument("--dest-port", type=int, default=5005)
# 플래시를 쓸 카메라의 IP(기본 169.254.1.222).
ap.add_argument("--camera-ip", default="169.254.1.222")
# 신경망 입력 폭(기본 416).
ap.add_argument("--width", type=int, default=416)
# 신경망 입력 높이(기본 416).
ap.add_argument("--height", type=int, default=416)
# 클래스 수(기본 4).
ap.add_argument("--classes", type=int, default=4)
# 카메라 fps(기본 5).
ap.add_argument("--fps", type=float, default=5)
# 입력된 인자를 읽어 a 에 담는다.
a = ap.parse_args()

# 인자로 파이프라인을 조립한다(카메라 → YOLO → Script). 아직 카메라에는 아무것도 안 올라갔다.
pipeline = build(a.blob, a.dest_ip, a.dest_port, a.width, a.height, a.classes, fps=a.fps)
# 대상 카메라를 IP 로 지정.
info = dai.DeviceInfo(a.camera_ip)
# 그 카메라의 부트로더(전원 직후 먼저 도는 프로그램, 플래시 쓰기 담당)에 연결.
bootloader = dai.DeviceBootloader(info)
# 부트로더 버전을 화면에 출력(시험 기록용, 이 환경에서는 0.0.28).
print(f"부트로더 버전: {bootloader.getVersion()}")
# 조립한 파이프라인(블롭과 Script 코드 포함)을 카메라 플래시에 쓴다. 진행률(%)을 한 줄에 덮어쓰며 출력한다. 링크가 끊기면 중간에 실패할 수 있다.
bootloader.flash(lambda p: print(f"\r플래시 {p * 100:5.1f}%", end="", flush=True), pipeline)
# 완료 메시지. 이제 카메라 전원을 껐다 켜면 PC 없이 시작하고 결과가 UDP 로 온다(listen_udp.py 로 확인).
print("\n완료. 카메라 전원을 껐다 켜면 PC 없이 시작한다. 결과는 UDP 로 온다: python3 listen_udp.py --port", a.dest_port)




