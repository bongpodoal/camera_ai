# 진행 기록

## 목적 (2026-09-23 재편)

OAK-D 공식 예제 모델(YOLOv6n)을 7단계로 나눠 분석한다. MATLAB·다른 모델은 다루지 않는다.
최종적으로 ⑦에서 토출 데이터를 시간축으로 5분 기록하고, 처리한 이미지로 확인하고,
CAN으로 받을 수 있는지 확인하고, 파라미터 50개 이상을 추출한다.

## 단계별 상태

| 단계 | 상태 | 근거 |
|---|---|---|
| ① .pt | 이름만 확인. 원본 출처 미확인 | `01_pytorch_pt/README.md` |
| ② ONNX | 이름·입출력 확인 (파일 없음) | `02_onnx/README.md` |
| ③ OpenVINO IR | 변환 명령 확인 (파일 없음) | `03_openvino_ir/README.md` |
| ④ .blob | superblob 구조 해석 완료 | `04_blob/README.md` |
| ⑤ NNArchive | 두 예제 추출·해석 완료 (2026-09-23) | `05_nnarchive/example/*/report.md` |
| ⑥ OAK-D 칩 | 예제 실행·FPS 분해 완료 (2026-09-16) | `06_oakd_chip/step01_record/NOTES.md` |
| ⑦ 호스트 | 밑작업 완료, 카메라 없이 검증 (2026-09-23). 실제 5분 기록·CAN 확인 예정 | `07_host_output/NOTES.md` |

## 신호등 모델 직접 변환 (2026-09-28, `traffic_light/`)

`~/camera` 의 `traffic_light.pt` (YOLO11s, red/yellow/green/off) 를 YOLOv8n 예제와 같은 절차로.

| 단계 | 결과 |
|---|---|
| ①~⑤ | ONNX `[1, 9, H, W]`×3 → IR(전처리 내장) → blob(SHAVE 8, 19.8 MB) → NNArchive(17.1 MB, conf 0.35) |
| 검증 | `chip_forward` = 원본 출력 층(오차 0.0008 px). 칩 경로 흉내(ONNX→FP16→depthai 해석기)로 합성 빨간불 `red 0.76`, 초록불 `green 0.81` — 원본과 동일 |
| ⑥⑦ | 5분 실측 (2026-09-29): 칩 9.75 FPS(9.65~9.81), 2916프레임 누락 없음, 지연 중앙 821 ms, 칩 42.1→53.4°C. 실제 신호등 인식률 미확인 |

## 지연 분해 측정 (2026-09-29, 두 번째 PC, `tools/latency_test.py`)

| 모델 | FPS | 엣지 | PC | 총 |
|---|---|---|---|---|
| YOLOv6n | 20.85 | 371 ms | 6.9 ms | 378 ms |
| YOLOv8n | 18.61 | 419 ms | 5.8 ms | 426 ms |
| 신호등 YOLO11s | 9.66 | 819 ms | 6.6 ms | 826 ms |

총 지연의 98~99% 가 칩 안. 원래 PC 와 총 지연 동일. 과정: Script 노드 크래시 2건(`getTimestamp()`, `setData(list)`) 해결 후 측정.

## 다음

1. ⑥ 실행 로그에서 실제 SHAVE 배분 확인
2. ⑦ 실제 카메라 20초 → 5분 기록, 파라미터 50개 이상 확인
3. ⑦ CAN: vcan0 → USB-CAN 어댑터
4. ① 원본 출처 확인
