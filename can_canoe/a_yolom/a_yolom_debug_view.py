#!/home/kwakjunyoung/venvs/camera_ai/bin/python
"""A-YOLOM(n) 디버그 창: 실시간 영상 + 검출 박스 + 차선·주행영역 오버레이 (측정 전 카메라 위치·화면 확인용).

측정(can_demo.py --model a_yolom_n)과 같은 파이프라인(카메라 → NeuralNetwork, 6 SHAVE 블롭)을 쓰지만 CAN 송신·기록은 하지 않는다.
카메라를 점유하므로 **측정을 시작하기 전에 반드시 닫는다** (Q 또는 ESC).

사용법:
    ./a_yolom_debug_view.py                         # 영상 + 박스 + 차선(자홍) + 주행영역(초록) 오버레이
    ./a_yolom_debug_view.py --no-seg                # 박스만
    ./a_yolom_debug_view.py --depth                 # 깊이맵 창도 같이 (깊이를 켜면 칩 부하가 늘어 fps 가 4 근처로 내려감)
    ./a_yolom_debug_view.py --fps 4 --archive <경로>.tar.xz   # 카메라 FPS, 다른 모델/변형
조작: Q 또는 ESC = 종료
"""
import argparse
import os
import sys
import time
from pathlib import Path

# depthai 3 이 있는 venv 로 다시 실행
VENV = os.path.expanduser("~/venvs/camera_ai")
if os.path.realpath(sys.prefix) != os.path.realpath(VENV) and os.path.exists(f"{VENV}/bin/python"):
    os.execv(f"{VENV}/bin/python", [f"{VENV}/bin/python", os.path.abspath(__file__), *sys.argv[1:]])

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import postprocess as base            # noqa: E402
import postprocess_variants as pv     # noqa: E402
from a_yolom_source import input_size_of, variant_of   # noqa: E402

DEFAULT_ARCHIVE = HERE.parent.parent / "a_yolom/05_nnarchive/a_yolom_n_cam01_ft1-512x288-6shave.tar.xz"
COLORS = {"person": (255, 128, 0), "car": (0, 165, 255), "tl_red": (0, 0, 255), "tl_green": (0, 220, 0), "tl_yellow": (0, 255, 255)}   # BGR
SCALE_UP = 2


def overlay(frame, mask, color, alpha=0.4):
    if mask is None or not mask.any():
        return frame
    tint = frame.copy()
    tint[mask] = color
    return cv2.addWeighted(tint, alpha, frame, 1 - alpha, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", default="169.254.1.222")
    ap.add_argument("--fps", type=float, default=5)
    ap.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    ap.add_argument("--variant")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--no-seg", action="store_true", help="차선·주행영역 오버레이를 그리지 않는다")
    ap.add_argument("--depth", action="store_true", help="깊이맵 창을 같이 띄운다")
    a = ap.parse_args()

    import depthai as dai
    path = Path(a.archive).expanduser()
    variant, (w, h) = variant_of(path, a.variant), input_size_of(path)
    if path.suffix == ".blob":
        sys.path.insert(0, str(HERE.parent / "model_candidates"))
        from chip_bench import wrap_blob
        archive = dai.NNArchive(str(wrap_blob(path, w, h)[0]))
    else:
        archive = dai.NNArchive(str(path))
    info = (1.0, 0, 0, w, h)
    device = dai.Device(dai.DeviceInfo(a.ip))
    print(f"연결: DeviceId {device.getDeviceId()} · 모델 {path.name} (변형 {variant}) · {w}x{h} · Q/ESC 종료")
    with dai.Pipeline(device) as pipeline:
        cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        net = pipeline.create(dai.node.NeuralNetwork).build(cam, archive, fps=a.fps)
        net.input.setMaxSize(1)
        net.input.setBlocking(False)
        out_q = net.out.createOutputQueue(maxSize=2, blocking=False)
        frame_q = net.passthrough.createOutputQueue(maxSize=2, blocking=False)
        depth_q = None
        if a.depth:
            depth = pipeline.create(dai.node.Depth).build(dai.node.Depth.Algorithm.AUTO, a.fps, (w, h))
            depth.setAlignTo(cam.requestOutput((w, h), dai.ImgFrame.Type.BGR888p, fps=a.fps))
            depth_q = depth.depth.createOutputQueue(maxSize=2, blocking=False)
        pipeline.start()
        t_win, n_win, fps = time.monotonic(), 0, 0.0
        depth_img = None
        while pipeline.isRunning():
            msg = out_q.get()
            frame_msg = frame_q.get()
            outs = {nm: np.asarray(msg.getTensor(nm, dequantize=True), np.float32) for nm in msg.getAllLayerNames()}
            det, dmask, lmask = pv.postprocess(variant, outs, info, w, h, conf=a.conf)
            img = frame_msg.getCvFrame()
            if not a.no_seg:
                img = overlay(overlay(img, dmask, (0, 200, 0)), lmask, (255, 0, 255), 0.6)
            img = cv2.resize(img, (w * SCALE_UP, h * SCALE_UP), interpolation=cv2.INTER_LINEAR)
            cv2.line(img, (0, img.shape[0] // 2), (img.shape[1], img.shape[0] // 2), (0, 255, 0), 1)
            cv2.line(img, (img.shape[1] // 2, 0), (img.shape[1] // 2, img.shape[0]), (0, 255, 0), 1)
            for x1, y1, x2, y2, conf, c in det:
                name = base.NAMES[int(c)]
                p0, p1 = (int(x1 * img.shape[1]), int(y1 * img.shape[0])), (int(x2 * img.shape[1]), int(y2 * img.shape[0]))
                cv2.rectangle(img, p0, p1, COLORS[name], 2)
                cv2.putText(img, f"{name} {conf:.2f}", (p0[0], max(p0[1] - 5, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[name], 1)
            n_win += 1
            now = time.monotonic()
            if now - t_win >= 1.0:
                fps, n_win, t_win = n_win / (now - t_win), 0, now
            lat = (dai.Clock.now() - msg.getTimestamp()).total_seconds() * 1000
            seg_txt = "" if dmask is None else f"  lane {int(lmask.sum()) >= 50 and 'O' or '-'}  drivable {int(dmask.sum()) >= 50 and 'O' or '-'}"
            cv2.putText(img, f"{fps:.1f} FPS  {lat:.0f} ms  박스 {len(det)}{seg_txt}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("A-YOLOM debug (Q/ESC)", img)
            if depth_q is not None:
                for d in depth_q.tryGetAll():
                    arr = d.getFrame().astype(np.float32)
                    depth_img = cv2.applyColorMap(cv2.convertScaleAbs(np.clip(arr, 0, 8000), alpha=255 / 8000), cv2.COLORMAP_JET)
                if depth_img is not None:
                    cv2.imshow("depth (0~8 m)", depth_img)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    sys.exit(main())
