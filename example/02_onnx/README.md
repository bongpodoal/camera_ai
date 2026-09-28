# ② ONNX — 표준 형식으로 내보낸 모델

ONNX 파일은 **받은 파일에 없다.** 변환 기록(`buildinfo.json`)에 이름과 입출력만 남아 있다.
근거: `05_nnarchive/example/*/report.md` 의 ② 절.

| 항목 | yolov6-nano (기본값) | r2-coco-512x288 |
|---|---|---|
| ONNX 파일명 | `yolov6n-r2-384x512-simplified.onnx` | `yolov6n-r2-288x512-simplified.onnx` |
| 입력 | `images` [1, 3, 384, 512] f32 | `images` [1, 3, 288, 512] f32 |
| 출력 | `output1_yolov6r2`, `output2_yolov6r2`, `output3_yolov6r2` | 동일 |
| 변환 도구 | modelconverter 0.4.4 | modelconverter 0.1.2 |

`-simplified` = ONNX 그래프 단순화(onnxsim)를 거친 것. 출력 3개는 스케일이 다른 검출 헤드 3개다
(원래 YOLO 헤드를 칩 디코더 형식 `yolov6r2`로 바꾼 것).

이 폴더에는 아직 파일이 없다.
