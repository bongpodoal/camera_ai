"""신호등 증분학습 YOLOv8n을 OAK-D에 올려 실행한다.

Step 01의 공식 예제와 같은 구조지만, 모델 주 슬러그 대신 **로컬 NNArchive**를 넘긴다.
직접 학습한 모델을 엣지에 올릴 때의 차이는 이 한 줄뿐이다.

    Step 01:  dai.NNModelDescription("yolov6-nano")      <- 모델 주에서 자동 다운로드
    여기:     dai.NNArchive("....tar.xz")                <- 직접 변환한 파일

사용법:
    python3 run_traffic.py                    # 화면 표시
    python3 run_traffic.py --seconds 30       # 측정만 (FPS 출력)
    python3 run_traffic.py --no-display       # 렌더링 없이
"""
import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import depthai as dai

ARCHIVE = (Path(__file__).resolve().parents[2]
           / "benchmark/models/yolov8n_traffic_288x512_onchip_fixed.tar.xz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default=str(ARCHIVE))
    ap.add_argument("--ip", default=None)
    ap.add_argument("--seconds", type=float, default=0.0, help="0이면 Q 누를 때까지")
    ap.add_argument("--warmup", type=float, default=5.0)
    ap.add_argument("--no-display", action="store_true")
    args = ap.parse_args()

    archive = dai.NNArchive(args.archive)
    print(f"모델: {Path(args.archive).name}  입력 {archive.getInputWidth()}x{archive.getInputHeight()}")

    device = dai.Device(dai.DeviceInfo(args.ip)) if args.ip else None
    pipeline = dai.Pipeline(device) if device else dai.Pipeline()

    with pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        nn = pipeline.create(dai.node.DetectionNetwork).build(cam, archive)
        labels = nn.getClasses()

        qRgb = nn.passthrough.createOutputQueue()
        qDet = nn.out.createOutputQueue()

        pipeline.start()

        t0 = time.monotonic()
        warm_until = t0 + args.warmup
        end = warm_until + args.seconds if args.seconds else float("inf")
        counter, steady_t0 = 0, None
        recent = deque(maxlen=60)

        while pipeline.isRunning() and time.monotonic() < end:
            frame = qRgb.get().getCvFrame()
            dets = qDet.get().detections
            now = time.monotonic()

            if now >= warm_until:
                if steady_t0 is None:
                    steady_t0 = now
                counter += 1
                recent.append(now)

            if not args.no_display:
                h, w = frame.shape[:2]
                for d in dets:
                    p1 = (int(d.xmin * w), int(d.ymin * h))
                    p2 = (int(d.xmax * w), int(d.ymax * h))
                    cv2.rectangle(frame, p1, p2, (255, 0, 0), 2)
                    cv2.putText(frame, f"{labels[d.label]} {int(d.confidence*100)}%",
                                (p1[0] + 6, p1[1] + 18), cv2.FONT_HERSHEY_TRIPLEX,
                                0.45, (255, 0, 0))
                if recent:
                    fps = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 1 else 0
                    cv2.putText(frame, f"NN fps: {fps:.2f}", (2, h - 5),
                                cv2.FONT_HERSHEY_TRIPLEX, 0.45, (255, 255, 255))
                cv2.imshow("traffic", frame)
                if cv2.waitKey(1) == ord("q"):
                    break

        elapsed = time.monotonic() - steady_t0 if steady_t0 else 0
        inst = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 1 else 0
        cv2.destroyAllWindows()

    if elapsed:
        print(f"  누적 FPS : {counter/elapsed:.2f}  ({counter}개 / {elapsed:.1f}s)")
        print(f"  순간 FPS : {inst:.2f}")


if __name__ == "__main__":
    main()
