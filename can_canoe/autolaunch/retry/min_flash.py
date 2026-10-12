#!/usr/bin/env python3
"""단계별 최소 파이프라인을 플래시하는 시험용 스크립트 (DepthAI v2 환경).
step 1: ColorCamera → XLinkOut (Script 없음)    → 앱이 뜨면 상태가 X_LINK_FLASH_BOOTED 로 보이고 호스트가 스트림을 받을 수 있다
step 2: Script 만 (UDP "hello" 1초마다, 카메라 없음)
step 2b: Script 만 (socket 대신 아무것도 안 함, 오류 처리만) — socket import 가 원인인지 구분
예) python3 min_flash.py --step 1
"""
import argparse

import depthai as dai

ap = argparse.ArgumentParser()
ap.add_argument("--step", default="1")
ap.add_argument("--camera-ip", default="169.254.1.222")
ap.add_argument("--dest-ip", default="169.254.1.10")
ap.add_argument("--dest-port", type=int, default=5005)
a = ap.parse_args()

HELLO = """
import socket, time
n = 0
sock = None
while True:
    n += 1
    try:
        if sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(("hello %d" % n).encode(), ("{ip}", {port}))
    except Exception as e:
        node.warn("send err " + repr(e))
        sock = None
    time.sleep(1)
"""
NOSOCK = """
import time
n = 0
while True:
    n += 1
    node.warn("alive %d" % n)
    time.sleep(1)
"""


def build(step):
    p = dai.Pipeline()
    if step == "1":
        cam = p.create(dai.node.ColorCamera)
        cam.setPreviewSize(416, 416)
        cam.setFps(5)
        out = p.create(dai.node.XLinkOut)
        out.setStreamName("preview")
        cam.preview.link(out.input)
    elif step == "2":
        s = p.create(dai.node.Script)
        s.setProcessor(dai.ProcessorType.LEON_CSS)   # socket 은 LEON_CSS 에서만 import 된다 (기본 LEON_MSS 에는 없음)
        s.setScript(HELLO.format(ip=a.dest_ip, port=a.dest_port))
    elif step == "2b":
        s = p.create(dai.node.Script)
        s.setScript(NOSOCK)
    else:
        raise SystemExit("step 1 | 2 | 2b")
    return p


bl = dai.DeviceBootloader(dai.DeviceInfo(a.camera_ip))
print(f"부트로더 {bl.getVersion()} 플래시 시작 step={a.step}")
ok, msg = bl.flash(lambda pr: print(f"\r플래시 {pr * 100:5.1f}%", end="", flush=True), build(a.step))
print("\n결과:", ok, msg)
bl.close()
