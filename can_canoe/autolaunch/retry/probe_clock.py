"""호스트 모드로 칩 Script(LEON_CSS)에서 Clock.now() 와 getTimestampDevice() 가 되는지 확인 (DepthAI v2)."""
import time
import depthai as dai
S = """
import time
for i in range(3):
    m = node.io['det'].get()
    for name, f in (("Clock.now", lambda: Clock.now()), ("tsDevice", lambda: m.getTimestampDevice()), ("ts", lambda: m.getTimestamp()), ("diff", lambda: (Clock.now() - m.getTimestampDevice()).total_seconds())):
        try:
            node.warn(name + " = " + repr(f()))
        except Exception as e:
            node.warn(name + " ERR " + repr(e))
"""
p = dai.Pipeline()
cam = p.create(dai.node.ColorCamera); cam.setPreviewSize(416, 416); cam.setInterleaved(False); cam.setFps(5)
nn = p.create(dai.node.YoloDetectionNetwork)
nn.setBlobPath("/home/kwakjunyoung/camera_ai/traffic_light/04_blob/traffic_light_v8n-416x416.blob")
nn.setNumClasses(2); nn.setCoordinateSize(4); nn.setAnchors([]); nn.setAnchorMasks({}); nn.setConfidenceThreshold(0.35); nn.setIouThreshold(0.5)
cam.preview.link(nn.input)
s = p.create(dai.node.Script); s.setProcessor(dai.ProcessorType.LEON_CSS); s.setScript(S)
nn.out.link(s.inputs["det"])
with dai.Device(dai.DeviceInfo("169.254.1.222")) as dev:
    dev.setLogLevel(dai.LogLevel.WARN); dev.setLogOutputLevel(dai.LogLevel.WARN)
    dev.startPipeline(p); time.sleep(8)
