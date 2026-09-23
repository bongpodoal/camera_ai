# luxonis/yolov6-nano:r2-coco-512x288

원본 아카이브: `/home/henes-ad/.cache/depthai/models/abfc46233063c04d37a9c548781af353cc638f00/yolov6n-r2-288x512.rvc2.tar.xz`

## ⑤ NNArchive

| 항목 | 값 |
| --- | --- |
| 파일 구성 | `config.json` (1,880 B), `buildinfo.json` (1,838 B), `yolov6n-r2-288x512.superblob` (8,721,232 B) |
| 모델 이름 (config) | `YOLOv6_Nano-R2_COCO_512x288` |
| 실제 입력 (getInputWidth/Height) | **512×288** |
| 입력 shape / layout | [1, 3, 288, 512] NCHW |
| 전처리 (config) | mean=[0.0, 0.0, 0.0] scale=[1.0, 1.0, 1.0] reverse_channels=False |
| 후처리 | parser=`YOLO` subtype=`yolov6r2` |
| 출력 텐서 | output1_yolov6r2, output2_yolov6r2, output3_yolov6r2 |
| 클래스 / 문턱 | 80개 · conf 0.5 · IoU 0.5 · 최대 300 |

## ④ blob

| 항목 | 값 |
| --- | --- |
| 파일 크기 | 8,721,232 B |
| 헤더 | 136 B (u64 × 17, 빅엔디언) |
| 기본 블롭 | 8,681,560 B · SHAVE [8]개로 컴파일 |
| SHAVE별 패치 | 1:11,121, 2:4,532, 3:3,996, 4:2,764, 5:2,528, 6:2,239, 7:2,286, 8:0, 9:1,123, 10:1,278, 11:1,277, 12:1,276, 13:1,295, 14:1,269, 15:1,276, 16:1,276 B |
| 크기 합 일치 | 예 |
| 컴파일 도구 | `2022.3.0` · 장치 `MYRIAD` · 입력 정밀도 `U8` |
| CMX 슬라이스 | 8 |

## ③ OpenVINO IR

IR 파일은 아카이브에 없다. 만든 명령만 남아 있다 (Model Optimizer `2022.3.0-9213-bdadcd7583c-releases/2022/3`):

```
mo --output_dir shared_with_container/outputs/yolov6n-r2-288x512_to_rvc2_2024_07_24_07_53_40/intermediate_outputs --output output1_yolov6r2,output2_yolov6r2,output3_yolov6r2 --input images[1,3,288,512]{f32} --mean_values images[0.0, 0.0, 0.0] --scale_values images[255.0, 255.0, 255.0] --reverse_input_channels --input_model shared_with_container/outputs/yolov6n-r2-288x512_to_rvc2_2024_07_24_07_53_40/intermediate_outputs/yolov6n-r2-288x512-simplified.onnx
```

## ② ONNX

| 항목 | 값 |
| --- | --- |
| 입력 ONNX (아카이브에 없음) | `yolov6n-r2-288x512-simplified.onnx` |
| 입력 | `images[1,3,288,512]{f32}` |
| 출력 | `output1_yolov6r2,output2_yolov6r2,output3_yolov6r2` |
| 변환 도구 | modelconverter `0.1.2` |

## ① PyTorch .pt

원본 가중치는 아카이브에 없다. 이름만 남아 있다: `YOLOv6_Nano-R2_COCO_512x288`
