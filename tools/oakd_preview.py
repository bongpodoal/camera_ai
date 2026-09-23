"""OAK-D 실시간 미리보기 (RGB + 스테레오 깊이).

`live_preview.py`가 v4l2 USB 카메라용이라면, 이쪽은 DepthAI(OAK-D) 전용이다.
RGB 화면과 깊이맵을 나란히 띄우고, RGB 쪽엔 설치 각도를 눈으로 가늠할 수 있게
`live_preview.py`와 같은 가로/세로 중앙 기준선을 그린다.

PoE 모델은 같은 서브넷에 있어야 자동 탐색(UDP 브로드캐스트)이 되고, 서브넷이 다르거나
브로드캐스트가 막힌 환경에선 `--ip`로 직접 지정해야 한다. DHCP 서버가 없으면 카메라는
169.254.1.222로 폴백하므로, PC를 169.254.1.10/16으로 두고 `--ip 169.254.1.222`로 붙는다.

사용법:
    python3 calibration/oakd_preview.py                    # 자동 탐색 (RGB + 깊이)
    python3 calibration/oakd_preview.py --ip 169.254.1.222 # PoE 직결 등 IP 직접 지정
    python3 calibration/oakd_preview.py --rgb-only         # RGB만 (스테레오 문제 시)
조작: Q 또는 ESC = 종료
"""
import argparse
import sys

import cv2
import depthai as dai
import numpy as np

PREVIEW_W, PREVIEW_H = 640, 480
DEPTH_W, DEPTH_H = 640, 400
FPS = 30
WINDOW_RGB = 'OAK-D RGB - Q: quit'
WINDOW_DEPTH = 'OAK-D Depth - Q: quit'


def draw_center_lines(frame):
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.line(frame, (0, cy), (w, cy), (0, 255, 0), 1)   # 화면 세로 중앙 (수평선 기준)
    cv2.line(frame, (cx, 0), (cx, h), (0, 255, 0), 1)   # 화면 가로 중앙
    return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rgb-only', action='store_true', help='깊이 스트림 없이 RGB만 표시')
    parser.add_argument('--ip', help='PoE 장치 IP를 직접 지정 (자동 탐색 실패 시)')
    args = parser.parse_args()

    if args.ip:
        device = dai.Device(dai.DeviceInfo(args.ip))
        print(f'IP 직접 연결: {args.ip} (DeviceId {device.getDeviceId()})')
    else:
        devices = dai.Device.getAllAvailableDevices()
        if not devices:
            print('OAK-D를 찾을 수 없습니다. PoE 전원(802.3af 인젝터/스위치)과 LAN 링크를 '
                  '확인하고, 서브넷이 다르면 --ip로 직접 지정하세요.')
            return 1
        print(f'장치 {len(devices)}개 발견: ' + ', '.join(d.getDeviceId() for d in devices))
        device = dai.Device(devices[0])

    with dai.Pipeline(device) as pipeline:
        cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        rgb_q = cam.requestOutput(
            (PREVIEW_W, PREVIEW_H), dai.ImgFrame.Type.BGR888i, fps=FPS
        ).createOutputQueue()

        depth_q = None
        if not args.rgb_only:
            try:
                stereo = pipeline.create(dai.node.StereoDepth).build(
                    autoCreateCameras=True, size=(DEPTH_W, DEPTH_H), fps=FPS
                )
                stereo.setRectifyEdgeFillColor(0)
                depth_q = stereo.depth.createOutputQueue()
            except Exception as exc:                      # 모노 카메라가 없는 모델 등
                print(f'스테레오 깊이 사용 불가 ({exc}) - RGB만 표시합니다.')
                depth_q = None

        pipeline.start()
        print('창에서 Q 또는 ESC로 종료')

        try:
            while pipeline.isRunning():
                rgb = rgb_q.tryGet()
                if rgb is not None:
                    cv2.imshow(WINDOW_RGB, draw_center_lines(rgb.getCvFrame()))

                if depth_q is not None:
                    depth = depth_q.tryGet()
                    if depth is not None:
                        # uint16 mm -> 보기 좋은 컬러맵. 0(깊이 없음)은 그대로 검게 남긴다.
                        raw = depth.getFrame()
                        norm = cv2.normalize(raw, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
                        colored = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
                        colored[raw == 0] = 0
                        cv2.imshow(WINDOW_DEPTH, colored)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    break
        finally:
            cv2.destroyAllWindows()
    return 0


if __name__ == '__main__':
    sys.exit(main())
