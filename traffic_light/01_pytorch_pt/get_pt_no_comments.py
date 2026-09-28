#!/usr/bin/env python3

import shutil
import sys
from pathlib import Path

from ultralytics import YOLO

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "camera" / "deploy" / "traffic_light.pt"
HERE = Path(__file__).resolve().parent
pt_path = HERE / "traffic_light.pt"

if not pt_path.exists():
    print(f"복사: {SOURCE}")
    shutil.copy2(SOURCE, pt_path)
print(f"저장 위치: {pt_path} ({pt_path.stat().st_size / 1e6:.1f} MB)")

model = YOLO(str(pt_path))
network = model.model
detect = network.model[-1]

print(f"task: {model.task}  (detect = 박스 검출)")
print(f"클래스 수: {len(model.names)}  {model.names}")
print(f"파라미터(가중치 숫자) 수: {sum(p.numel() for p in network.parameters()):,}")
print(f"학습 때 입력 크기(imgsz): {network.args.get('imgsz')}")
print(f"출력 층: {type(detect).__name__}, 격자 {detect.nl}개, stride {detect.stride.tolist()}, reg_max {detect.reg_max}")

parts = [name for name, _ in detect.named_children()]
print(f"출력 층 부품: {parts}")
if model.task != "detect" or type(detect).__name__ != "Detect" or parts != ["cv2", "cv3", "dfl"]:
    sys.exit("이 모델은 YOLOv8n 예제와 출력 층 구조가 달라서 ②의 chip_forward 를 그대로 쓸 수 없습니다.")
print("확인: YOLOv8n 예제와 같은 Detect 출력 층 → ②~⑦을 그대로 진행할 수 있다")
