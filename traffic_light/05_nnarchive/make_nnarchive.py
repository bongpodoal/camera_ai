#!/usr/bin/env python3
# ============================================================================
# ⑤ NNArchive — ④의 .blob 과 설명서(config.json)를 하나의 파일(.tar.xz)로 묶는다.
#
# NNArchive = depthai v3 가 모델을 받는 표준 묶음. config.json 에는
#   - 입력: 이름, 크기, 칩이 넣어줄 이미지 형식(BGR888p)
#   - 출력: 이름, 모양
#   - head: "이 출력은 YOLO(yolov8 방식)이니 칩에서 박스로 풀고(NMS 포함) 클래스 이름은 이것"
# 이 들어간다. 이 설명 덕분에 ⑥에서 DetectionNetwork 가 알아서 칩 위 디코딩을 켠다.
# 형식은 YOLOv8n 예제의 config.json 을 그대로 따랐고, 다른 점은 클래스(4종)와 문턱값뿐이다.
#
# 문턱값은 이 모델을 PC에서 실제로 쓰던 값(~/camera/deploy/camera_yolo.py)을 그대로 가져왔다:
#   conf 0.35 : 신호등은 작고 흐리게 찍혀 확신도가 낮게 나오는 일이 많아 예제(0.5)보다 낮춤
#   iou  0.5  : 예제와 같음
#
# 실행:  python3 05_nnarchive/make_nnarchive.py
# 결과:  05_nnarchive/config.json, traffic_light-512x288.tar.xz
# ============================================================================

import json
import tarfile                      # .tar.xz 묶음 파일을 만들려고
from pathlib import Path

import depthai as dai               # 만든 아카이브가 depthai 에서 열리는지 확인하려고
import onnx                         # ② ONNX 에서 입출력 모양을 읽으려고
from ultralytics import YOLO        # ① .pt 에서 클래스 이름 4개를 읽으려고

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
pt_path = ROOT / "01_pytorch_pt" / "traffic_light.pt"
onnx_path = ROOT / "02_onnx" / "traffic_light-512x288.onnx"
blob_path = ROOT / "04_blob" / "traffic_light-512x288.blob"
archive_path = HERE / "traffic_light-512x288.tar.xz"


def shape_of(tensor):
    """ONNX 텐서 정보에서 모양(예: [1, 9, 36, 64])을 꺼낸다."""
    return [d.dim_value for d in tensor.type.tensor_type.shape.dim]


# 입출력 이름과 모양은 ② ONNX 에서 그대로 읽는다 (손으로 적으면 틀리기 쉽다).
graph = onnx.load(str(onnx_path)).graph
input_shape = shape_of(graph.input[0])                  # [1, 3, 288, 512]
outputs = [(o.name, shape_of(o)) for o in graph.output]
output_names = [name for name, _ in outputs]
class_names = list(YOLO(str(pt_path)).names.values())  # ['red', 'yellow', 'green', 'off']

config = {
    "config_version": "1.0",
    "model": {
        "metadata": {"name": blob_path.stem, "path": blob_path.name, "precision": "float16"},
        "inputs": [{
            "name": graph.input[0].name, "dtype": "uint8", "input_type": "image",
            "shape": input_shape, "layout": "NCHW",
            # 전처리(÷255, BGR→RGB)는 ③에서 모델 안에 넣었으므로 여기선 "아무것도 안 함"(평균 0, 배율 1).
            "preprocessing": {"mean": [0, 0, 0], "scale": [1, 1, 1], "reverse_channels": False,
                              "interleaved_to_planar": False, "dai_type": "BGR888p"},
        }],
        "outputs": [{"name": name, "dtype": "float32", "shape": shape, "layout": "NCDE"}
                    for name, shape in outputs],
        "heads": [{
            "name": None,
            "parser": "YOLO",                           # 칩 위 YOLO 디코더를 쓴다
            "metadata": {
                "classes": class_names, "n_classes": len(class_names),
                "iou_threshold": 0.5,                   # NMS: 50% 넘게 겹치는 박스는 하나만 남김
                "conf_threshold": 0.35,                 # 신뢰도 35% 미만 박스는 버림
                "max_det": 300,
                "anchors": None,                        # YOLOv8·YOLO11 은 앵커 없는(anchor-free) 방식
                "yolo_outputs": output_names,
                "subtype": "yolov8",                    # ②에서 출력을 YOLOv8 모양으로 맞췄으므로
            },
            "outputs": output_names,
        }],
    },
}

config_path = HERE / "config.json"
config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

# config.json 과 blob 을 한 파일로 묶는다 (arcname = 묶음 안에서의 파일 이름).
with tarfile.open(archive_path, "w:xz") as archive:
    archive.add(config_path, arcname="config.json")
    archive.add(blob_path, arcname=blob_path.name)
print(f"저장: {archive_path} ({archive_path.stat().st_size / 1e6:.1f} MB)")

# 확인: depthai 가 이 아카이브를 읽을 수 있는지
nn_archive = dai.NNArchive(str(archive_path))
print(f"  depthai 에서 열림: 입력 {nn_archive.getInputWidth()}×{nn_archive.getInputHeight()},"
      f" 클래스 {len(class_names)}개 {class_names}, 출력 {output_names}")
