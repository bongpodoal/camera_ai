"""호스트 모드로 칩 Script 에서 어떤 모듈을 import 할 수 있는지 조사 (DepthAI v2). 결과는 장치 로그(node.warn)로 나온다."""
import time

import depthai as dai

S = """
import sys
mods = ["socket", "_socket", "usocket", "select", "http", "http.server", "json", "time", "struct", "os", "sys", "errno", "network", "urllib", "ssl"]
for m in mods:
    try:
        __import__(m)
        node.warn("OK   " + m)
    except Exception as e:
        node.warn("FAIL " + m + " : " + str(e))
node.warn("sys.modules: " + str(sorted(sys.modules.keys()))[:600])
node.warn("version: " + str(sys.version))
"""
p = dai.Pipeline()
s = p.create(dai.node.Script)
s.setProcessor(dai.ProcessorType.LEON_CSS)
s.setScript(S)
with dai.Device(dai.DeviceInfo("169.254.1.222")) as dev:
    dev.setLogLevel(dai.LogLevel.WARN)
    dev.setLogOutputLevel(dai.LogLevel.WARN)
    dev.startPipeline(p)
    time.sleep(6)
