# accuracy — 칩에 사진을 직접 넣어 3모델 인식률(정답 비교) 측정

센서를 거치지 않고, **같은 검증 사진을 3모델에 똑같이** 넣어 칩이 낸 검출을 정답 라벨과 비교한다.
(카메라 경로의 렌즈·조명·모니터 반사 영향이 빠진 "칩 위 모델 자체의 인식 수준" 비교. 카메라 영상 경로 검증은 별도.)

| 파일 | 역할 | 어디서 |
|---|---|---|
| `eval_core.py` | IoU 짝짓기, 정밀도·재현율·F1, AP50, 색 혼동 계산 (+`selftest_eval.py` 검증) | 어디서나 |
| `eval_accuracy.py` | 예측 CSV + 정답 라벨 → 비교표(`accuracy_summary.csv/.md`) | 어디서나 |
| `chip_infer.py` | **사진을 칩 입력 큐로 보내 칩의 검출을 CSV 로 저장** | 카메라 PC (실카메라 미검증) |
| `pt_infer.py` | PyTorch 모델로 같은 CSV 를 만듦 (기준선·평가 코드 검증) | 맥 등 |

## 정답 데이터
신호등 데이터셋 검증 사진 567장 (HF `lincolnn2026/traffic_light_dataset`, `images/val`·`labels/val`). 맥에서는 val 만 `~/camera_eval_data/` 에 받아 두었다.
```bash
pip install huggingface_hub
python3 -c "from huggingface_hub import snapshot_download as s; s('lincolnn2026/traffic_light_dataset', repo_type='dataset', allow_patterns=['images/val/*','labels/val/*'], local_dir='$HOME/camera_eval_data')"
```
라벨 0 red · 1 yellow · 2 green · 3 off. **채점은 red·green 만** (yellow·off 정답에 맞은 예측은 오검출로 세지 않음) — traffic_light_v8n 이 red·green 두 클래스뿐이기 때문.
> 주의: traffic_light_v8n(`last.pt`)은 `dataset_fixed_v2` 로 학습됐다. 이 검증셋과 겹치는지 **확인하지 못했다** → 겹치면 v8n 점수가 부풀 수 있으므로 결과에 명시.

## 카메라 PC 에서 실행 (링크가 100 Mbps 이상으로 정상일 때)
깊이 노드를 쓰지 않으므로 **기존 8 SHAVE NNArchive 그대로** 쓴다 (6 SHAVE 변환본 불필요).
```bash
cd can_canoe/accuracy
python3 chip_infer.py --model yolov6n           --images ~/camera_eval_data/images/val --out out/yolov6n_chip.csv --limit 20   # 먼저 20장 확인
python3 chip_infer.py --model yolov6n           --images ~/camera_eval_data/images/val --out out/yolov6n_chip.csv
python3 chip_infer.py --model traffic_light_v8n --images ~/camera_eval_data/images/val --out out/traffic_light_v8n_chip.csv
python3 chip_infer.py --model traffic_light     --images ~/camera_eval_data/images/val --out out/traffic_light_chip.csv
python3 eval_accuracy.py --images ~/camera_eval_data/images/val --labels ~/camera_eval_data/labels/val \
    --preds out/yolov6n_chip.csv out/traffic_light_v8n_chip.csv out/traffic_light_chip.csv --out out/
```
- `--resize letterbox`(기본, 학습과 같은 비율 유지) 와 `stretch` 를 둘 다 돌려 차이를 보면 좋다 (실제 카메라 경로가 어느 쪽인지 미확인).
- 칩 문턱값을 0.05 로 낮춰 모아 두고 평가에서 운영 문턱값(yolov6n 0.5, 신호등 0.35)으로 거른다. 정밀도·재현율은 운영 문턱값, AP50 은 전체.

## 읽는 법
| 열 | 뜻 |
|---|---|
| 정밀도 / 재현율 / F1 | 위치(IoU≥0.5)가 맞은 비율 — **색은 무시** (3모델 공통, COCO 모델 포함) |
| 색 정확도 | 위치가 맞은 것 중 색까지 맞은 비율 (신호등 모델만) |
| red↔green 뒤바뀜 | 가장 치명적인 오류 횟수 |
| 색까지 맞춘 재현율 | 정답 중 위치와 색이 모두 맞은 비율 |
| AP50 red/green | 학습 때 평가(mAP50)와 같은 방식의 클래스별 점수 |

## 검증 상태
| 항목 | 상태 |
|---|---|
| `eval_core.py` | 손으로 계산한 사례 14개 일치 (`python3 selftest_eval.py`) |
| 평가 코드 vs 학습 때 mAP | 맥에서 YOLO11s PyTorch 예측으로 비교 (아래 기록) |
| `chip_infer.py` | **실카메라 미검증** (호스트 입력 큐 `net.input.createInputQueue()` 와 `setCvFrame(…, BGR888p)` 가정) |
