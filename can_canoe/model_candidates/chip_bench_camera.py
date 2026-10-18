#!/usr/bin/env python3
"""카메라 → NeuralNetwork 직결 파이프라인의 fps 와 지연을 잰다 (호스트가 이미지를 넣는 chip_bench.py 와 비교용). 카메라 PC 에서 실행.
  지연 = dai.Clock.now() − 결과 메시지의 촬영 시각(getTimestamp)  (촬영→호스트 수신, 이더넷 포함)
예) python3 chip_bench_camera.py --blob x.blob --width 512 --height 288 --fps 5 --seconds 30 [--depth]
"""
import argparse
import statistics
import time
from pathlib import Path

import depthai as dai

from measure_log import LOG_DIR, append_row, git_state, link_mbps, now_iso

from chip_bench import wrap_blob

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--blob", required=True)
ap.add_argument("--width", type=int, required=True)
ap.add_argument("--height", type=int, required=True)
ap.add_argument("--fps", type=float, default=5)
ap.add_argument("--seconds", type=float, default=30)
ap.add_argument("--depth", action="store_true", help="스테레오 깊이를 같은 fps 로 같이 돌린다 (깊이 켬)")
ap.add_argument("--ip", default="169.254.1.222")
a = ap.parse_args()
start_time, link0 = now_iso(), link_mbps()
archive_path, blob = wrap_blob(Path(a.blob).expanduser(), a.width, a.height)
device = dai.Device(dai.DeviceInfo(a.ip))
with dai.Pipeline(device) as pipeline:
    cam = pipeline.create(dai.node.Camera).build()
    net = pipeline.create(dai.node.NeuralNetwork).build(cam, dai.NNArchive(str(archive_path)), fps=a.fps)
    try:
        net.input.setMaxSize(1)
        net.input.setBlocking(False)       # can_demo 와 같은 최신화 큐
    except AttributeError:
        pass
    q = net.out.createOutputQueue()
    if a.depth:
        depth = pipeline.create(dai.node.Depth).build(dai.node.Depth.Algorithm.AUTO, a.fps)
        dq = depth.depth.createOutputQueue(maxSize=2, blocking=False)
    pipeline.start()
    seqs, lat, t_rx = [], [], []
    t0 = time.monotonic()
    while time.monotonic() - t0 < a.seconds:
        m = q.get()
        t_rx.append(time.monotonic())
        seqs.append(m.getSequenceNum())
        lat.append((dai.Clock.now() - m.getTimestamp()).total_seconds() * 1000)
        if a.depth:
            dq.tryGetAll()
    span = t_rx[-1] - t_rx[0]
    gaps = [b - a_ for a_, b in zip(seqs, seqs[1:])]
    print(f"{Path(a.blob).name}: SHAVE {blob.numShaves}, 입력 {a.width}x{a.height}, 목표 {a.fps:g} fps, 깊이 {'켬' if a.depth else '끔'}: "
          f"결과 {len(seqs)}개 / {a.seconds:.0f}초, 수신 {len(seqs) / span:.2f} fps, 지연 중앙 {statistics.median(lat):.1f} ms · p95 {sorted(lat)[int(len(lat) * .95) - 1]:.1f} ms "
          f"(첫 3개 제외 중앙 {statistics.median(lat[3:]):.1f}), 순번 건너뜀 {sum(1 for g in gaps if g > 1)}회")
append_row(LOG_DIR / "chip_bench_camera_log.csv", dict(start_time=start_time, link_mbps_start=link0, link_mbps_end=link_mbps(), blob=Path(a.blob).name, shaves=blob.numShaves,
           width=a.width, height=a.height, fps_req=a.fps, depth="on" if a.depth else "off", seconds=a.seconds, results=len(seqs), fps_rx=round(len(seqs) / span, 2),
           lat_median_ms=round(statistics.median(lat), 1), lat_p95_ms=round(sorted(lat)[int(len(lat) * .95) - 1], 1), seq_gaps=sum(1 for g in gaps if g > 1), git=git_state()))
