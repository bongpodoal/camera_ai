# yolov6-nano

원본 아카이브: `/home/henes-ad/.cache/depthai/models/98fa008f114a052fc110a400b9f2526e541e7c72/YOLOv6_Nano-R2_COCO_512x288.rvc2.tar.xz`

## ⑤ NNArchive

| 항목 | 값 |
| --- | --- |
| 파일 구성 | `yolov6n-r2-384x512.superblob` (8,726,870 B), `buildinfo.json` (1,878 B), `config.json` (5,855 B) |
| 모델 이름 (config) | `yolov6n-r2-384x512` |
| 실제 입력 (getInputWidth/Height) | **512×384** |
| 입력 shape / layout | [1, 3, 384, 512] NCHW |
| 전처리 (config) | mean=[0.0, 0.0, 0.0] scale=[1.0, 1.0, 1.0] reverse_channels=False |
| 후처리 | parser=`YOLO` subtype=`yolov6r2` |
| 출력 텐서 | output1_yolov6r2, output2_yolov6r2, output3_yolov6r2 |
| 클래스 / 문턱 | 80개 · conf 0.5 · IoU 0.5 · 최대 300 |

## ④ blob

| 항목 | 값 |
| --- | --- |
| 파일 크기 | 8,726,870 B |
| 헤더 | 136 B (u64 × 17, 빅엔디언) |
| 기본 블롭 | 8,685,208 B · SHAVE [8]개로 컴파일 |
| SHAVE별 패치 | 1:11,562, 2:4,769, 3:4,242, 4:3,543, 5:3,298, 6:2,275, 7:1,523, 8:0, 9:1,788, 10:1,146, 11:1,199, 12:1,258, 13:1,351, 14:1,177, 15:1,202, 16:1,193 B |
| 크기 합 일치 | 예 |
| 컴파일 도구 | `2022.3.0` · 장치 `MYRIAD` · 입력 정밀도 `U8` |
| CMX 슬라이스 | 8 |

## ③ OpenVINO IR

IR 파일은 아카이브에 없다. 만든 명령만 남아 있다 (Model Optimizer `2022.3.0-9052-9752fafe8eb-releases/2022/3`):

```
mo --output_dir shared_with_container/outputs/YOLOv6_Nano-R2_COCO_512x288_to_rvc2_2025_10_01_11_04_32/intermediate_outputs --output output1_yolov6r2,output2_yolov6r2,output3_yolov6r2 --compress_to_fp16 --input images[1 3 384 512]{f32} --mean_values images[0.0, 0.0, 0.0] --scale_values images[255.0, 255.0, 255.0] --reverse_input_channels --input_model shared_with_container/outputs/YOLOv6_Nano-R2_COCO_512x288_to_rvc2_2025_10_01_11_04_32/intermediate_outputs/yolov6n-r2-384x512-simplified.onnx
```

## ② ONNX

| 항목 | 값 |
| --- | --- |
| 입력 ONNX (아카이브에 없음) | `yolov6n-r2-384x512-simplified.onnx` |
| 입력 | `images[1 3 384 512]{f32}` |
| 출력 | `output1_yolov6r2,output2_yolov6r2,output3_yolov6r2` |
| 변환 도구 | modelconverter `0.4.4` |

## ① PyTorch .pt

원본 가중치는 아카이브에 없다. 이름만 남아 있다: `yolov6n-r2-384x512`
