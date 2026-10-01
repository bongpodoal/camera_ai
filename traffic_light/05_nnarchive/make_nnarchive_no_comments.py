#!/usr/bin/env python3

import json
import tarfile
import sys
from pathlib import Path

import depthai as dai
import onnx
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SIZE = sys.argv[1] if len(sys.argv) > 1 else "512x288"
NAME = sys.argv[2] if len(sys.argv) > 2 else "traffic_light"
pt_path = ROOT / "01_pytorch_pt" / f"{NAME}.pt"
onnx_path = ROOT / "02_onnx" / f"{NAME}-{SIZE}.onnx"
blob_path = ROOT / "04_blob" / f"{NAME}-{SIZE}.blob"
archive_path = HERE / f"{NAME}-{SIZE}.tar.xz"


def shape_of(tensor):
    return [d.dim_value for d in tensor.type.tensor_type.shape.dim]


graph = onnx.load(str(onnx_path)).graph
input_shape = shape_of(graph.input[0])
outputs = [(o.name, shape_of(o)) for o in graph.output]
output_names = [name for name, _ in outputs]
class_names = list(YOLO(str(pt_path)).names.values())

config = {
    "config_version": "1.0",
    "model": {
        "metadata": {"name": blob_path.stem, "path": blob_path.name, "precision": "float16"},
        "inputs": [{
            "name": graph.input[0].name, "dtype": "uint8", "input_type": "image",
            "shape": input_shape, "layout": "NCHW",
            "preprocessing": {"mean": [0, 0, 0], "scale": [1, 1, 1], "reverse_channels": False,
                              "interleaved_to_planar": False, "dai_type": "BGR888p"},
        }],
        "outputs": [{"name": name, "dtype": "float32", "shape": shape, "layout": "NCDE"}
                    for name, shape in outputs],
        "heads": [{
            "name": None,
            "parser": "YOLO",
            "metadata": {
                "classes": class_names, "n_classes": len(class_names),
                "iou_threshold": 0.5,
                "conf_threshold": 0.35,
                "max_det": 300,
                "anchors": None,
                "yolo_outputs": output_names,
                "subtype": "yolov8",
            },
            "outputs": output_names,
        }],
    },
}

config_path = HERE / "config.json"
config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

with tarfile.open(archive_path, "w:xz") as archive:
    archive.add(config_path, arcname="config.json")
    archive.add(blob_path, arcname=blob_path.name)
print(f"저장: {archive_path} ({archive_path.stat().st_size / 1e6:.1f} MB)")

nn_archive = dai.NNArchive(str(archive_path))
print(f"  depthai 에서 열림: 입력 {nn_archive.getInputWidth()}×{nn_archive.getInputHeight()},"
      f" 클래스 {len(class_names)}개 {class_names}, 출력 {output_names}")
