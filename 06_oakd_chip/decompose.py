"""공식 예제의 FPS가 무엇을 측정한 값인지 분해한다.

`detection_network_original.py`를 그대로 돌리면 21.35 FPS가 나오는데, 이 숫자에는
NN 추론 말고도 (a) 카메라 영상을 호스트로 전송하는 비용, (b) OpenCV 렌더링 비용이
섞여 있다. 어디까지가 모델 성능인지 알려면 하나씩 떼어내 봐야 한다.

  full     예제 그대로 — passthrough 영상 수신 + cv2.imshow
  nodisplay  영상은 받되 화면에 그리지 않음 -> 렌더링 비용 분리
  detonly    passthrough 큐 자체를 안 만듦 -> 영상 전송 비용까지 분리

예제의 FPS 계산은 누적 평균(counter / 전체경과)이라 부팅 시간이 섞여 실제보다 낮게 나온다.
여기서는 누적값과 함께 **최근 구간 기준 순간 FPS**도 같이 낸다.

사용법: python3 decompose.py --mode full|nodisplay|detonly [--seconds 40]
"""
import argparse
import time
from collections import deque

import cv2
import depthai as dai


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("full", "nodisplay", "detonly"), default="full")
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--warmup", type=float, default=5.0)
    ap.add_argument("--ip", default=None, help="PoE 장치 IP (자동 탐색이 실패할 때)")
    ap.add_argument("--model", default="yolov6-nano",
                    help="모델 주 슬러그. 해상도를 바꾸려면 변형을 명시한다 "
                         "(예: luxonis/yolov6-nano:r2-coco-512x288)")
    args = ap.parse_args()

    device = dai.Device(dai.DeviceInfo(args.ip)) if args.ip else None
    pipeline = dai.Pipeline(device) if device else dai.Pipeline()

    with pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        det = pipeline.create(dai.node.DetectionNetwork).build(
            cam, dai.NNModelDescription(args.model))

        qDet = det.out.createOutputQueue()
        # detonly 모드는 passthrough 큐를 아예 만들지 않는다 -> 영상이 호스트로 안 온다.
        qRgb = det.passthrough.createOutputQueue() if args.mode != "detonly" else None

        pipeline.start()

        t0 = time.monotonic()
        warm_until = t0 + args.warmup
        end = warm_until + args.seconds

        counter = 0            # 워밍업 이후 누적 검출 메시지 수
        steady_t0 = None
        recent = deque(maxlen=60)   # 순간 FPS용 최근 타임스탬프

        while pipeline.isRunning() and time.monotonic() < end:
            if qRgb is not None:
                frame = qRgb.get().getCvFrame()
            inDet = qDet.get()
            now = time.monotonic()

            if now < warm_until:
                continue
            if steady_t0 is None:
                steady_t0 = now

            counter += 1
            recent.append(now)

            if args.mode == "full" and qRgb is not None:
                for d in inDet.detections:
                    h, w = frame.shape[:2]
                    p1 = (int(d.xmin * w), int(d.ymin * h))
                    p2 = (int(d.xmax * w), int(d.ymax * h))
                    cv2.rectangle(frame, p1, p2, (255, 0, 0), 2)
                cv2.imshow("decompose", frame)
                if cv2.waitKey(1) == ord("q"):
                    break

        elapsed = time.monotonic() - steady_t0 if steady_t0 else 0
        inst = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 1 else 0
        cv2.destroyAllWindows()

    print(f"[{args.mode}] {args.model} · 워밍업 {args.warmup}s 제외")
    print(f"  누적 FPS : {counter/elapsed:.2f}  ({counter}개 / {elapsed:.1f}s)")
    print(f"  순간 FPS : {inst:.2f}  (최근 {len(recent)}개 구간)")


if __name__ == "__main__":
    main()
