"""호스트 모드로 LEON_CSS Script 의 UDP 송신이 실제로 되는지 확인 (DepthAI v2). 오류는 node.warn 으로 보인다. 수신은 5005."""
import socket as pysock
import time

import depthai as dai

S = """
import socket, time
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    node.warn("socket ok")
    for n in range(5):
        sock.sendto(("hello %d" % n).encode(), ("169.254.1.10", 5005))
        node.warn("sent %d" % n)
        time.sleep(1)
except Exception as e:
    node.warn("ERR " + repr(e))
"""
rx = pysock.socket(pysock.AF_INET, pysock.SOCK_DGRAM)
rx.bind(("", 5005)); rx.settimeout(0.3)
p = dai.Pipeline()
s = p.create(dai.node.Script)
s.setProcessor(dai.ProcessorType.LEON_CSS)
s.setScript(S)
got = []
with dai.Device(dai.DeviceInfo("169.254.1.222")) as dev:
    dev.setLogLevel(dai.LogLevel.WARN)
    dev.setLogOutputLevel(dai.LogLevel.WARN)
    dev.startPipeline(p)
    t0 = time.time()
    while time.time() - t0 < 9:
        try:
            got.append(rx.recvfrom(100))
        except pysock.timeout:
            pass
print("수신:", got)
