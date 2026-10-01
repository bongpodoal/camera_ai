#!/usr/bin/env python3

import types
import sys
from pathlib import Path

import onnxruntime
import torch
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

SIZE = sys.argv[1] if len(sys.argv) > 1 else "512x288"
NAME = sys.argv[2] if len(sys.argv) > 2 else "traffic_light"
WIDTH, HEIGHT = map(int, SIZE.split("x"))
pt_path = ROOT / "01_pytorch_pt" / f"{NAME}.pt"
onnx_path = HERE / f"{NAME}-{WIDTH}x{HEIGHT}.onnx"
OUTPUT_NAMES = ["output1_yolov8", "output2_yolov8", "output3_yolov8"]

network = YOLO(str(pt_path)).model.float().eval()
network.fuse()
detect = network.model[-1]


def chip_forward(self, x):
    outputs = []
    for i in range(self.nl):
        box = self.cv2[i](x[i])
        cls = self.cv3[i](x[i]).sigmoid()
        b, _, h, w = box.shape
        box = self.dfl(box.view(b, 4 * self.reg_max, h * w)).view(b, 4, h, w)
        conf = cls.max(1, keepdim=True)[0]
        outputs.append(torch.cat([box, conf, cls], 1))
    return outputs


detect.forward = types.MethodType(chip_forward, detect)

dummy = torch.zeros(1, 3, HEIGHT, WIDTH)
torch.onnx.export(network, dummy, str(onnx_path),
                  opset_version=12,
                  input_names=["images"], output_names=OUTPUT_NAMES,
                  dynamo=False)
print(f"저장: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)")

session = onnxruntime.InferenceSession(str(onnx_path))
for tensor in session.get_inputs() + session.get_outputs():
    print(f"  {tensor.name:16s} {tensor.shape}")
