#!/usr/bin/env python3
"""블롭을 칩에 올려 **순수 추론 속도와 지연**을 잰다 (카메라 센서 없이 PC 가 같은 이미지를 반복해서 넣는다). 카메라 PC 에서 실행.

학습하지 않은 모델도 구조만 같으면 속도는 같으므로, 후보 모델을 학습하기 전에 지연 100 ms 를 맞출 수 있는지 걸러내는 용도다.
  - 지연(ms)  : 이미지 한 장을 넣고 결과가 돌아올 때까지 (하나씩, 앞 장이 끝난 뒤에 다음 장)  ← 칩 지연의 하한에 가깝다
  - 처리량(fps): 이미지를 inflight 장씩 겹쳐 넣었을 때 초당 결과 수                            ← 칩 한계 FPS
예) python3 chip_bench.py --blob ~/camera_work/blobs/a_yolom_n_512x288.blob --width 512 --height 288 --n 200
    python3 chip_bench.py --blob x.blob --width 512 --height 288 --ip 169.254.1.222 --inflight 2
주의: 맥에서 작성했고 **실카메라로 실행해 보지 않았다.** 호스트 입력 큐(createInputQueue)·NNArchive 래핑은 depthai 3.x 가정이다.
"""
import argparse
import json
import statistics
import tarfile
import tempfile
import time
from pathlib import Path

import numpy as np


def wrap_blob(blob_path, width, height):
    """블롭 하나를 최소 NNArchive(.tar.xz)로 감싼다. 칩 위 해석기(parser)는 쓰지 않고 원시 출력을 받는다."""
    import depthai as dai
    blob = dai.OpenVINO.Blob(str(blob_path))
    name = Path(blob_path).stem
    config = {"config_version": "1.0", "model": {
        "metadata": {"name": name, "path": Path(blob_path).name, "precision": "float16"},
        "inputs": [{"name": next(iter(blob.networkInputs)), "dtype": "uint8", "input_type": "image",
                    "shape": [1, 3, height, width], "layout": "NCHW",
                    "preprocessing": {"mean": [0, 0, 0], "scale": [1, 1, 1], "reverse_channels": False,
                                      "interleaved_to_planar": False, "dai_type": "BGR888p"}}],
        "outputs": [{"name": n, "dtype": "float32"} for n in blob.networkOutputs],
        "heads": []}}
    tmp = Path(tempfile.mkdtemp())
    (tmp / "config.json").write_text(json.dumps(config, indent=2))
    archive = tmp / f"{name}.tar.xz"
    with tarfile.open(archive, "w:xz") as t:
        t.add(tmp / "config.json", arcname="config.json")
        t.add(blob_path, arcname=Path(blob_path).name)
    return archive, blob


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blob", required=True)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--ip", default="169.254.1.222")
    ap.add_argument("--n", type=int, default=200, help="잴 장수")
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--inflight", type=int, default=2, help="처리량 측정에서 동시에 칩에 넣어 둘 장수")
    ap.add_argument("--out", help="결과를 한 줄 CSV 로 덧붙일 파일")
    a = ap.parse_args()

    import depthai as dai
    archive_path, blob = wrap_blob(Path(a.blob).expanduser(), a.width, a.height)
    img = (np.random.rand(a.height, a.width, 3) * 255).astype(np.uint8)

    def frame():
        f = dai.ImgFrame()
        f.setCvFrame(img, dai.ImgFrame.Type.BGR888p)
        return f

    device = dai.Device(dai.DeviceInfo(a.ip))
    with dai.Pipeline(device) as pipeline:
        net = pipeline.create(dai.node.NeuralNetwork)
        net.setNNArchive(dai.NNArchive(str(archive_path)))
        in_q = net.input.createInputQueue()
        out_q = net.out.createOutputQueue()
        pipeline.start()
        for _ in range(a.warmup):
            in_q.send(frame())
            out_q.get()
        lat = []
        for _ in range(a.n):                               # 지연: 한 장씩
            t0 = time.perf_counter()
            in_q.send(frame())
            out_q.get()
            lat.append((time.perf_counter() - t0) * 1000)
        sent = got = 0                                       # 처리량: inflight 장씩 겹쳐서
        t0 = time.perf_counter()
        while got < a.n:
            while sent - got < a.inflight and sent < a.n:
                in_q.send(frame())
                sent += 1
            out_q.get()
            got += 1
        fps = a.n / (time.perf_counter() - t0)
    med = statistics.median(lat)
    p95 = sorted(lat)[int(len(lat) * 0.95) - 1]
    print(f"{Path(a.blob).name}: SHAVE {blob.numShaves}, 입력 {a.width}x{a.height}, 지연 중앙 {med:.1f} ms · p95 {p95:.1f} ms, 처리량 {fps:.1f} fps (inflight {a.inflight})")
    if a.out:
        new = not Path(a.out).exists()
        with open(a.out, "a", encoding="utf-8") as fh:
            if new:
                fh.write("blob,shaves,width,height,latency_ms_median,latency_ms_p95,fps,inflight\n")
            fh.write(f"{Path(a.blob).name},{blob.numShaves},{a.width},{a.height},{med:.1f},{p95:.1f},{fps:.1f},{a.inflight}\n")


if __name__ == "__main__":
    main()
