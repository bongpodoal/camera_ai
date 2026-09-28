#!/usr/bin/env python3
# ============================================================================
# ③ OpenVINO IR — ②의 ONNX 를 OpenVINO IR(.xml + .bin)로 바꾼다.
#
# IR = Intel OpenVINO 가 쓰는 중간 형식. .xml = 신경망 구조(글자), .bin = 가중치(숫자).
# 요즘 Python(3.12)에는 OAK-D(MYRIAD)를 지원하는 OpenVINO 2022 가 설치되지 않아서,
# Luxonis 온라인 변환 서버(blobconverter)의 Model Optimizer(OpenVINO 2022.1)를 쓴다. → 인터넷 필요
#
# 변환하면서 전처리 두 가지를 모델 안에 넣는다 (YOLOv8n 예제와 같은 방식):
#   --scale_values=[255,255,255] : 픽셀 0~255 를 0~1 로 나누기
#   --reverse_input_channels     : 카메라의 BGR 순서를 모델이 배운 RGB 순서로 바꾸기
# 그래서 ⑤ config.json 에는 전처리를 적지 않는다 (둘 다 하면 검출이 0개가 된다).
#
# 실행:  python3 03_openvino_ir/convert_ir.py
# 결과:  03_openvino_ir/traffic_light-512x288.xml, .bin
# ============================================================================

import zipfile                      # 서버가 돌려준 zip 을 풀려고
from pathlib import Path

import blobconverter                # Luxonis 변환 서버에 파일을 보내고 결과를 받는 도구

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
onnx_path = ROOT / "02_onnx" / "traffic_light-512x288.onnx"

blobconverter.set_defaults(silent=True)                 # 진행 막대 출력 끄기
# download_ir=True : blob 만이 아니라 중간 결과인 IR 도 zip 으로 받는다.
zip_path = Path(blobconverter.from_onnx(
    model=str(onnx_path),
    data_type="FP16",                                   # 가중치를 16비트 실수로 (칩이 FP16 으로 계산)
    shaves=8,
    optimizer_params=["--scale_values=[255,255,255]",
                      "--reverse_input_channels",
                      "--output=output1_yolov8,output2_yolov8,output3_yolov8"],
    download_ir=True,
    output_dir=str(HERE),
    use_cache=False,
))

# zip 에서 .xml 과 .bin 만 꺼낸다 (같이 들어있는 .blob 은 ④에서 IR 로부터 따로 만든다).
with zipfile.ZipFile(zip_path) as archive:
    for name in archive.namelist():
        if name.endswith((".xml", ".bin")):
            archive.extract(name, HERE)
            print(f"저장: {HERE / name} ({(HERE / name).stat().st_size / 1e6:.2f} MB)")
zip_path.unlink()
