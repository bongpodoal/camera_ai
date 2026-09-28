# traffic_light — 신호등 모델을 OAK-D 칩에 올리기 (①~⑦)

`~/camera` 프로젝트에서 직접 학습한 신호등 검출 모델을 YOLOv8n 예제와 **같은 절차**로 OAK-D(Myriad X / RVC2)에 올린다.
파일마다 설명 버전(`*.py`)과 주석 없는 버전(`*_no_comments.py`)이 있고, 두 버전의 결과 파일은 바이트 단위로 같다.

```
① .pt → ② ONNX → ③ OpenVINO IR → ④ .blob → ⑤ NNArchive → ⑥ OAK-D 칩 → ⑦ 호스트 기록
```

## 모델

| 항목 | 값 |
|---|---|
| 원본 | `~/camera/deploy/traffic_light.pt` (= `~/camera/runs/detect/traffic_light/weights/best.pt`) |
| 구조 | YOLO11s, 9.4M 파라미터, 출력 층 `Detect`(cv2·cv3·dfl) — YOLOv8n 과 같아서 ②의 `chip_forward` 를 그대로 씀 |
| 클래스 | 4종: `red` `yellow` `green` `off` |
| 학습 | 960px, HuggingFace `lincolnn2026/traffic_light_dataset` (세로형 신호등 위주) |
| 학습 성능 (PC, 960px) | red mAP50 0.990 · green 0.975 · yellow 0.902 · off 0.779 |

## 실행 순서 (이 폴더에서)

| 단계 | 파일 | 만드는 것 |
|---|---|---|
| ① | `01_pytorch_pt/get_pt.py` | `traffic_light.pt` 복사 + 칩에 올릴 수 있는 구조인지 확인 |
| ② | `02_onnx/export_onnx.py` | `traffic_light-512x288.onnx` — 출력 3개 `[1, 9, H, W]` (박스4 + 신뢰도1 + 클래스4) |
| ③ | `03_openvino_ir/convert_ir.py` | `.xml`/`.bin` — Luxonis 서버(OpenVINO 2022.1), ÷255·BGR→RGB를 모델 안에 |
| ④ | `04_blob/compile_blob.py` | `traffic_light-512x288.blob` — SHAVE 8, 입력 U8 |
| ⑤ | `05_nnarchive/make_nnarchive.py` | `config.json` + `traffic_light-512x288.tar.xz` (YOLO, subtype yolov8, conf 0.35, IoU 0.5) |
| ⑥ | `06_oakd_chip/run_on_chip.py` | 칩 실행 + 화면 표시 |
| ⑦ | `07_host_output/run_with_logging.py` | ⑥ + 시간축 기록(`data_logger.py`) + 이미지 저장(`image_saver.py`) → `runs/<시각>/` |

```bash
cd traffic_light
python3 06_oakd_chip/run_on_chip.py                        # 카메라 PC: ⑤까지 끝난 상태면 바로 실행
python3 07_host_output/run_with_logging.py --duration 300  # 5분 기록
```

①~⑤는 카메라 없이 된다. ③·④는 인터넷(`blobconverter.luxonis.com`)이 필요하다. 필요한 패키지: `requirements.txt`.

## 예제(YOLOv8n)와 다른 점

| 항목 | YOLOv8n 예제 | 신호등 | 이유 |
|---|---|---|---|
| 출력 채널 | 85 (클래스 80) | 9 (클래스 4) | 클래스 수 |
| 신뢰도 문턱 | 0.5 | 0.35 | `~/camera/deploy/camera_yolo.py` 의 실사용 값 |
| 계산량 | 8.7 GFLOPs (640²) | 21.4 GFLOPs (640²) | yolo11s 가 약 2.5배 → 칩 FPS 가 더 낮을 것 |
| 입력 | 512×288 | 512×288 | 예제와 같음. 학습은 960 이라 먼 신호등은 놓치기 쉬움 |

## 검증 (2026-09-28, 카메라 없이)

| 검증 | 결과 |
|---|---|
| ② `chip_forward` = 원본 YOLO11 출력 층 | 박스 최대 오차 0.0008 px, 클래스 확률 오차 1e-7 |
| ③ 전처리가 모델 안에 들어갔는지 | 첫 합성곱 가중치 = 원래 ÷255·채널 뒤집음 (오차 0.03%, FP16 반올림) |
| ④ blob | OpenVINO 2022.1, SHAVE 8, CMX 8, 입력 U8 [512, 288, 3], 출력 [W, H, 9] × 3 |
| ⑤ depthai 해석기가 config 를 읽는 값 | subtype yolov8, 클래스 4, conf 0.35, IoU 0.5, stride [8, 16, 32] |
| 칩 경로 흉내 (ONNX → FP16 → depthai 해석기, PC) | 합성 빨간불 `red 0.76`, 초록불 `green 0.81` — 원본 모델과 점수·박스 동일 |
| 설명판 = 주석 없는 판 | ①~⑤ 결과 6개 파일 SHA-256 동일 |

depthai 해석기의 NMS(겹친 박스 정리)는 **클래스 구분 없이** 동작한다. 같은 자리에 red·green 이 겹쳐 나오면 높은 쪽만 남는다 (원본 PC 추론은 클래스별이라 둘 다 남음).

## 아직 확인 못 한 것 (카메라 필요)

| 항목 | 확인 방법 |
|---|---|
| 칩 FPS (목표 5 fps 이상) | `07_host_output/run_with_logging.py --duration 60` → `summary.json` 의 `detections.rate_hz` |
| 실제 신호등 인식률 | 한국 가로형 4구 신호등은 학습 데이터(세로형)와 달라 떨어질 수 있음. 떨어지면 현장 영상으로 파인튜닝 |
| 입력 크기 | FPS 여유가 있으면 640×352 로 올려 먼 신호등 검출률 비교 (②의 `WIDTH, HEIGHT` 와 이후 파일 이름) |

원본 프로젝트의 2단계 판정(YOLO 박스 안에서 HSV 로 켜진 색 재확인)은 넣지 않았다 — 필요하면 ⑦ 호스트 코드에 추가한다.

## git 에 있는 것 / 없는 것

| 파일 | git |
|---|---|
| 스크립트, `.xml`, `config.json` | 있음 |
| `.onnx`, `.bin`, `.blob` | 없음 (②~④로 다시 만듦) |
| `traffic_light.pt`, `.tar.xz` | 커밋 여부 미정 — 카메라 PC 로 옮기려면 둘 중 하나는 필요 |
| `07_host_output/runs/` | 없음 |
