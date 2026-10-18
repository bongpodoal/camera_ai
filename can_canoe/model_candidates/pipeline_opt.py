#!/usr/bin/env python3
"""A-YOLOM(n) 직결 파이프라인(카메라 → NeuralNetwork [+ 깊이])에서 깊이·NN 노드 설정이 fps·누락·지연에 미치는 영향을 잰다. 카메라 PC 에서 실행.
  지연 = dai.Clock.now() − 신경망 결과의 촬영 시각 (촬영→호스트 수신, 이더넷 포함). 누락 = 순번 건너뜀 횟수(한 번에 여러 장이면 장수 합).
깊이 설정 --depth:  none | node[:PRESET]   (Depth 노드. PRESET = DEFAULT FAST_ACCURACY FAST_DENSITY ROBOTICS ACCURACY DENSITY HIGH_DETAIL FACE)
                    | stereo:옵션,옵션…    (StereoDepth 노드 직접. 옵션: res=400|480|720  lr=0|1  sub=0|1  ext=0|1  med=0|3|5|7  fps=숫자)
NN 설정 --nn "스레드,NCE,SHAVE" (0 = 기본). 예) --nn 1,2,0
예) python3 pipeline_opt.py --depth node:FAST_ACCURACY --nn 2,0,0 --fps 5 --seconds 30
깊이 정렬은 can_demo 와 같이 카메라 별도 출력(512x288)에 맞춘다.
"""
import argparse
import statistics
import time
from pathlib import Path

import depthai as dai

from measure_log import LOG_DIR, append_row, git_state, link_mbps, now_iso

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--archive", default=str(Path.home() / "camera_ai/a_yolom/05_nnarchive/a_yolom_n_cam01_ft1-512x288-6shave.tar.xz"))
ap.add_argument("--depth", default="none")
ap.add_argument("--nn", default="0,0,0")
ap.add_argument("--fps", type=float, default=5)
ap.add_argument("--seconds", type=float, default=30)
ap.add_argument("--ip", default="169.254.1.222")
a = ap.parse_args()
W, H = 512, 288
start_time, link0 = now_iso(), link_mbps()
th, nce, shv = (int(x) for x in a.nn.split(","))
device = dai.Device(dai.DeviceInfo(a.ip))
with dai.Pipeline(device) as p:
    cam = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    net = p.create(dai.node.NeuralNetwork).build(cam, dai.NNArchive(a.archive), fps=a.fps)
    net.input.setMaxSize(1)
    net.input.setBlocking(False)
    if th:
        net.setNumInferenceThreads(th)
    if nce:
        net.setNumNCEPerInferenceThread(nce)
    if shv:
        net.setNumShavesPerInferenceThread(shv)
    dq = None
    if a.depth.startswith("node"):
        algo = dai.node.Depth.Algorithm.STEREO if ":" in a.depth else dai.node.Depth.Algorithm.AUTO     # 프리셋을 고정하려면 구체적 알고리즘(STEREO)이 필요하다
        d = p.create(dai.node.Depth).build(algo, a.fps, (W, H))
        if ":" in a.depth:
            d.setConfig(getattr(dai.node.StereoDepth.PresetMode, a.depth.split(":")[1]))
        d.setAlignTo(cam.requestOutput((W, H), dai.ImgFrame.Type.BGR888p, fps=a.fps))
        dq = d.depth.createOutputQueue(maxSize=4, blocking=False)
    elif a.depth.startswith("stereo"):
        o = dict(kv.split("=") for kv in a.depth.split(":", 1)[1].split(",") if kv) if ":" in a.depth else {}
        res = {"400": (640, 400), "480": (640, 480), "720": (1280, 720)}[o.get("res", "400")]
        dfps = float(o.get("fps", a.fps))
        left = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
        right = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
        st = p.create(dai.node.StereoDepth)
        left.requestOutput(res, dai.ImgFrame.Type.NV12, fps=dfps).link(st.left)
        right.requestOutput(res, dai.ImgFrame.Type.NV12, fps=dfps).link(st.right)
        st.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.DEFAULT)
        st.setLeftRightCheck(o.get("lr", "1") == "1")
        st.setSubpixel(o.get("sub", "0") == "1")
        st.setExtendedDisparity(o.get("ext", "0") == "1")
        med = int(o.get("med", "7"))
        st.initialConfig.setMedianFilter({0: dai.MedianFilter.MEDIAN_OFF, 3: dai.MedianFilter.KERNEL_3x3, 5: dai.MedianFilter.KERNEL_5x5, 7: dai.MedianFilter.KERNEL_7x7}[med])
        st.setDepthAlign(dai.CameraBoardSocket.CAM_A)
        st.setOutputSize(W, H)
        dq = st.depth.createOutputQueue(maxSize=4, blocking=False)
    q = net.out.createOutputQueue(maxSize=2, blocking=False)
    p.start()
    seqs, lat, t0 = [], [], time.monotonic()
    while time.monotonic() - t0 < a.seconds:
        m = q.get()
        seqs.append(m.getSequenceNum())
        lat.append((dai.Clock.now() - m.getTimestamp()).total_seconds() * 1000)
        if dq is not None:
            dq.tryGetAll()
    n, span = len(seqs), time.monotonic() - t0
    dropped = sum(max(b - a_ - 1, 0) for a_, b in zip(seqs, seqs[1:]))
    steady = lat[len(lat) // 4:]       # 앞 1/4(시작 직후 안정화) 제외
    append_row(LOG_DIR / "pipeline_opt_log.csv", dict(start_time=start_time, link_mbps_start=link0, link_mbps_end=link_mbps(), archive=Path(a.archive).name, depth=a.depth,
               nn_threads_nce_shaves=a.nn, fps_req=a.fps, seconds=a.seconds, fps_rx=round(n / span, 2), dropped=dropped, lat_median_ms=round(statistics.median(steady)),
               lat_p95_ms=round(sorted(steady)[int(len(steady) * .95) - 1]), lat_first_ms=round(lat[3]), lat_last_ms=round(lat[-1]), git=git_state()))
    print(f"RESULT depth={a.depth} nn={a.nn} fps_req={a.fps:g}: 수신 {n/span:.2f} fps · 누락 {dropped} ({100*dropped/max(seqs[-1]-seqs[0]+1,1):.0f}%) · "
          f"지연 중앙 {statistics.median(steady):.0f} / p95 {sorted(steady)[int(len(steady)*.95)-1]:.0f} ms (처음 {lat[3]:.0f} → 끝 {lat[-1]:.0f})")
