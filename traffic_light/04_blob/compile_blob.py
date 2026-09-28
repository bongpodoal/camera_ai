#!/usr/bin/env python3
# ============================================================================
# ④ .blob — ③의 IR 을 OAK-D 칩(Myriad X)이 직접 실행하는 .blob 으로 컴파일한다.
#
# .blob = 특정 칩 전용으로 번역을 끝낸 실행 파일. 칩 안의 계산 코어(SHAVE) 몇 개를 쓸지도
# 이때 정해진다. YOLOv6n·YOLOv8n 예제의 기본 블롭과 같은 8개로 한다.
# 컴파일도 ③과 같은 Luxonis 서버(compile_tool, OpenVINO 2022.1)를 쓴다. → 인터넷 필요
#   -ip U8 (blobconverter 기본값) : 입력을 8비트 정수(0~255 픽셀)로 받는다
#
# 실행:  python3 04_blob/compile_blob.py
# 결과:  04_blob/traffic_light-512x288.blob
# ============================================================================

from pathlib import Path

import blobconverter
import depthai as dai               # 만든 blob 을 열어서 내용을 확인하려고

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
# 서버가 붙인 긴 이름(…_openvino_2022.1_8shave.blob)을 짧게 바꾼다.
Path(compiled).replace(blob_path)
print(f"저장: {blob_path} ({blob_path.stat().st_size / 1e6:.1f} MB)")

# 확인: depthai 로 blob 을 열어 칩이 읽을 정보를 본다.
blob = dai.OpenVINO.Blob(str(blob_path))
print(f"  OpenVINO 버전: {blob.version}, SHAVE {blob.numShaves}개, CMX 슬라이스 {blob.numSlices}개")
for name, tensor in blob.networkInputs.items():
    print(f"  입력  {name}: {tensor.dims} {tensor.dataType}")      # dims 는 [너비, 높이, 채널, 배치] 순서
for name, tensor in blob.networkOutputs.items():
    print(f"  출력  {name}: {tensor.dims}")
