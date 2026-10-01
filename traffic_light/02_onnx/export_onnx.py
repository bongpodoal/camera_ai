#!/usr/bin/env python3
# ============================================================================
# ② ONNX — ①의 traffic_light.pt 를 ONNX 파일로 내보낸다.
#
# ONNX = 어떤 프레임워크(PyTorch 등)에서 만든 신경망이든 같은 형식으로 저장하는 표준 파일.
# OpenVINO(③)는 .pt 를 직접 못 읽고 ONNX 를 읽는다.
#
# 그냥 내보내지 않고 "출력 층"을 바꾸는 이유:
#   OAK-D 칩은 YOLO 결과를 칩 안에서 박스로 정리(디코딩 + NMS)해 줄 수 있는데, 그러려면
#   출력이 칩이 아는 모양이어야 한다. YOLOv8n 예제와 같은 모양으로 맞춘다:
#     격자 크기별 출력 3개, 각각 [1, 9, 높이, 너비]
#     9 = 박스 4 (격자 중심에서 왼·위·오른·아래까지 거리) + 신뢰도 1 + 클래스 4 (red·yellow·green·off)
#   이 모델은 yolo11s 에서 학습했지만 출력 층(Detect)은 YOLOv8 과 같아서 chip_forward 를 그대로 쓴다.
#
# 입력 크기 512×288 = YOLOv8n 예제와 같다 (카메라 16:9, 32의 배수).
#   이 모델은 960 에서 학습했다(멀리 있는 작은 신호등을 잡으려고). 512 로 줄이면 먼 신호등은 놓치기 쉽지만,
#   yolo11s 는 yolov8n 보다 계산이 약 3배라 칩 속도(5 fps 이상)를 먼저 확보하려고 예제와 같은 크기로 시작한다.
#
# 실행:  python3 02_onnx/export_onnx.py  [크기 [이름]]   예) 416x416 traffic_light_11n (없으면 512x288 traffic_light)
# 결과:  02_onnx/<이름>-<크기>.onnx
# ============================================================================

import types                        # 출력 층의 forward 함수를 바꿔 끼우려고
import sys                          # 실행 인자(입력 크기·모델 이름) 읽기
from pathlib import Path

import onnxruntime                  # 만든 ONNX 파일이 제대로 읽히는지 확인하려고
import torch                        # PyTorch: 모델 실행과 ONNX 내보내기
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                      # traffic_light 폴더

# 입력 크기. 카메라 화면이 16:9 라서 512×288 로 정했다 (YOLO는 32의 배수여야 함).
# 실행 인자로 바꿀 수 있다. 예) 416x416 (2026-10-01 지연 비교용). 인자가 없으면 512x288.
SIZE = sys.argv[1] if len(sys.argv) > 1 else "512x288"
# 모델 이름 = 01_pytorch_pt/<이름>.pt 와 결과 파일 이름. 예) traffic_light_11n. 인자가 없으면 traffic_light (YOLO11s).
NAME = sys.argv[2] if len(sys.argv) > 2 else "traffic_light"
WIDTH, HEIGHT = map(int, SIZE.split("x"))
pt_path = ROOT / "01_pytorch_pt" / f"{NAME}.pt"
onnx_path = HERE / f"{NAME}-{WIDTH}x{HEIGHT}.onnx"
OUTPUT_NAMES = ["output1_yolov8", "output2_yolov8", "output3_yolov8"]   # ⑤ config.json 에 같은 이름을 쓴다

network = YOLO(str(pt_path)).model.float().eval()       # eval() = 학습 모드 끄기
network.fuse()                                          # Conv + BatchNorm 을 하나로 합침 (계산 줄이기)
detect = network.model[-1]                              # 출력 층


def chip_forward(self, x):
    """원래 출력 층 대신 쓸 계산. x = 격자 크기별 특징 지도 3개."""
    outputs = []
    for i in range(self.nl):
        box = self.cv2[i](x[i])                         # 박스: [1, 64, H, W] (경계 4개 × 16구간 확률)
        cls = self.cv3[i](x[i]).sigmoid()               # 클래스: [1, 4, H, W], sigmoid 로 0~1 확률로
        b, _, h, w = box.shape
        # DFL: 16구간 확률의 기대값으로 경계까지 거리 하나를 구한다 → [1, 4, H, W] (격자 칸 단위)
        box = self.dfl(box.view(b, 4 * self.reg_max, h * w)).view(b, 4, h, w)
        conf = cls.max(1, keepdim=True)[0]              # 가장 높은 클래스 확률을 신뢰도로 사용
        outputs.append(torch.cat([box, conf, cls], 1))  # [1, 9, H, W]
    return outputs


# 출력 층의 forward 를 위 함수로 바꿔 끼운다 (가중치는 그대로, 계산 순서만 바꿈).
detect.forward = types.MethodType(chip_forward, detect)

dummy = torch.zeros(1, 3, HEIGHT, WIDTH)                # 모양만 알려주는 빈 이미지
torch.onnx.export(network, dummy, str(onnx_path),
                  opset_version=12,                     # ③ OpenVINO 2022.1 이 읽을 수 있는 버전
                  input_names=["images"], output_names=OUTPUT_NAMES,
                  dynamo=False)                         # 예전 방식 내보내기 (OpenVINO 2022 와 호환)
print(f"저장: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)")

# 확인: ONNX Runtime 으로 파일을 열어 입출력 모양을 본다.
session = onnxruntime.InferenceSession(str(onnx_path))
for tensor in session.get_inputs() + session.get_outputs():
    print(f"  {tensor.name:16s} {tensor.shape}")
