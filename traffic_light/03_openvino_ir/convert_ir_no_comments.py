#!/usr/bin/env python3

import zipfile
import sys
from pathlib import Path

import blobconverter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SIZE = sys.argv[1] if len(sys.argv) > 1 else "512x288"
NAME = sys.argv[2] if len(sys.argv) > 2 else "traffic_light"
onnx_path = ROOT / "02_onnx" / f"{NAME}-{SIZE}.onnx"

blobconverter.set_defaults(silent=True)
zip_path = Path(blobconverter.from_onnx(
    model=str(onnx_path),
    data_type="FP16",
    shaves=8,
    optimizer_params=["--scale_values=[255,255,255]",
                      "--reverse_input_channels",
                      "--output=output1_yolov8,output2_yolov8,output3_yolov8"],
    download_ir=True,
    output_dir=str(HERE),
    use_cache=False,
))

with zipfile.ZipFile(zip_path) as archive:
    for name in archive.namelist():
        if name.endswith((".xml", ".bin")):
            archive.extract(name, HERE)
            print(f"저장: {HERE / name} ({(HERE / name).stat().st_size / 1e6:.2f} MB)")
zip_path.unlink()
