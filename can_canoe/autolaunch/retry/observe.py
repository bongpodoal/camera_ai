#!/usr/bin/env python3
"""1초마다 카메라 상태를 시각과 함께 기록한다 (DepthAI v2 환경). 앱이 도는지 알아보는 관측기.
기록: ping, 부트로더 탐색 상태(X_LINK_BOOTLOADER=부트로더 대기, X_LINK_FLASH_BOOTED=플래시된 앱 실행 중, X_LINK_UNBOOTED 등), UDP 수신 개수.
예) python3 observe.py --seconds 120 --port 5005 > obs.log
"""
import argparse
import socket
import subprocess
import time

import depthai as dai

ap = argparse.ArgumentParser()
ap.add_argument("--seconds", type=float, default=120)
ap.add_argument("--port", type=int, default=5005)
ap.add_argument("--ip", default="169.254.1.222")
a = ap.parse_args()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", a.port))
sock.settimeout(0.05)
t0, n_udp, first = time.monotonic(), 0, None
last = None
while time.monotonic() - t0 < a.seconds:
    loop = time.monotonic()
    ping = subprocess.run(["ping", "-c1", "-W1", a.ip], capture_output=True).returncode == 0
    bl = [x.state.name for x in dai.DeviceBootloader.getAllAvailableDevices()]
    dv = [x.state.name for x in dai.Device.getAllAvailableDevices()]
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            n_udp += 1
            first = first or round(time.monotonic() - t0, 1)
    except socket.timeout:
        pass
    row = (ping, tuple(bl), tuple(dv), n_udp)
    if row != last:
        print(f"{time.strftime('%H:%M:%S')} +{time.monotonic() - t0:6.1f}s ping={'up' if ping else 'down'} bootloader={bl} device={dv} udp={n_udp}", flush=True)
        last = row
    time.sleep(max(0, 1 - (time.monotonic() - loop)))
print(f"끝: udp {n_udp}개, 첫 UDP {first}")
