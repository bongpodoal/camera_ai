#!/usr/bin/env python3
# ============================================================================
# ① .pt — 직접 학습한 신호등 모델(traffic_light.pt)을 가져와서 무엇이 들어있는지 확인한다.
#
# .pt 파일 = PyTorch로 학습을 끝낸 모델(구조 + 숫자 가중치)을 통째로 저장한 파일.
# 이 모델은 인터넷에 공개된 게 아니라 ~/camera 프로젝트에서 직접 학습한 것이라
# (yolo11s 에서 시작, 신호등 4종: red / yellow / green / off), 다운로드 대신 파일을 복사해 온다.
#
# 이 단계에서 "OAK-D 칩에 올릴 수 있는 모델인가"도 같이 확인한다:
#   - task 가 detect(박스 검출)여야 한다. seg(분할)면 마스크 부품이 있어 ②의 방식이 안 통한다
#   - 출력 층이 Detect 이고 cv2(박스)·cv3(클래스)·dfl(거리 계산) 세 부품만 있어야 한다
#     → YOLOv8n 예제와 같은 구조라서 ②의 chip_forward 를 그대로 쓸 수 있다
#
# 실행:  python3 01_pytorch_pt/get_pt.py                       (기본: ~/camera/deploy/traffic_light.pt)
#        python3 01_pytorch_pt/get_pt.py /어딘가/best.pt       (다른 위치의 파일을 쓸 때)
# 결과:  01_pytorch_pt/traffic_light.pt   (다음 단계 ② 가 이 파일을 읽는다)
# ============================================================================

import shutil                       # 파일을 복사하려고
import sys                          # 실행 인자(원본 경로) 읽기, 맞지 않는 모델이면 끝내기
from pathlib import Path            # 파일 경로를 다루려고

from ultralytics import YOLO        # .pt 파일을 읽어 모델로 만들어 주는 라이브러리

# 원본 위치. ~/camera/deploy/traffic_light.pt 는 ~/camera/runs/detect/traffic_light/weights/best.pt 와 같은 파일이다.
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "camera" / "deploy" / "traffic_light.pt"
HERE = Path(__file__).resolve().parent          # 이 파일이 있는 폴더
pt_path = HERE / "traffic_light.pt"

# 1. 가져오기 (이미 가져왔으면 건너뜀)
if not pt_path.exists():
    print(f"복사: {SOURCE}")
    shutil.copy2(SOURCE, pt_path)
print(f"저장 위치: {pt_path} ({pt_path.stat().st_size / 1e6:.1f} MB)")

# 2. 읽어서 내용 확인
model = YOLO(str(pt_path))
network = model.model                   # 실제 PyTorch 신경망
detect = network.model[-1]              # 신경망의 마지막 층 = 박스와 클래스를 내는 "출력 층"

print(f"task: {model.task}  (detect = 박스 검출)")
print(f"클래스 수: {len(model.names)}  {model.names}")
print(f"파라미터(가중치 숫자) 수: {sum(p.numel() for p in network.parameters()):,}")
print(f"학습 때 입력 크기(imgsz): {network.args.get('imgsz')}")
# stride : 출력 층이 원본 이미지를 몇 배로 줄인 격자에서 박스를 찾는지. 8·16·32 세 가지 크기로 찾는다.
# reg_max: 박스 경계 하나를 16개 구간의 확률로 표현한다 (DFL). ②에서 이 부분을 칩에 맞게 바꾼다.
print(f"출력 층: {type(detect).__name__}, 격자 {detect.nl}개, stride {detect.stride.tolist()}, reg_max {detect.reg_max}")

# 3. 칩에 올릴 수 있는 구조인지 확인
parts = [name for name, _ in detect.named_children()]
print(f"출력 층 부품: {parts}")
if model.task != "detect" or type(detect).__name__ != "Detect" or parts != ["cv2", "cv3", "dfl"]:
    sys.exit("이 모델은 YOLOv8n 예제와 출력 층 구조가 달라서 ②의 chip_forward 를 그대로 쓸 수 없습니다.")
print("확인: YOLOv8n 예제와 같은 Detect 출력 층 → ②~⑦을 그대로 진행할 수 있다")
