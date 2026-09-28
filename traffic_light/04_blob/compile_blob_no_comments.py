#!/usr/bin/env python3

from pathlib import Path

import blobconverter
import depthai as dai

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ir_folder = ROOT / "03_openvino_ir"
blob_path = HERE / "traffic_light-512x288.blob"

blobconverter.set_defaults(silent=True)
compiled = blobconverter.from_openvino(
    xml=str(ir_folder / "traffic_light-512x288.xml"),
    bin=str(ir_folder / "traffic_light-512x288.bin"),
    data_type="FP16",
    shaves=8,
    output_dir=str(HERE),
    use_cache=False,
)
Path(compiled).replace(blob_path)
print(f"저장: {blob_path} ({blob_path.stat().st_size / 1e6:.1f} MB)")

blob = dai.OpenVINO.Blob(str(blob_path))
print(f"  OpenVINO 버전: {blob.version}, SHAVE {blob.numShaves}개, CMX 슬라이스 {blob.numSlices}개")
for name, tensor in blob.networkInputs.items():
    print(f"  입력  {name}: {tensor.dims} {tensor.dataType}")
for name, tensor in blob.networkOutputs.items():
    print(f"  출력  {name}: {tensor.dims}")
