# CAN 실측 2026-10-06 (yolov6n · Raw 끔 · 30초 · 5 fps · 클래식 CAN 500 kbps)

Ubuntu 카메라 PC(Kvaser Leaf v3) → Windows 노트북(VN1630A, `canoe_logger.py` 대체 로거) 수신.

| 폴더 | 내용 | 누가 올림 |
|---|---|---|
| `runs/<run_id>/` | 송신 기록 `frames.csv` · `detections.csv` · `summary.csv` (이미지 제외) | Ubuntu |
| `logs/<run_id>/` | 수신 로그 `canoe.asc` · `*.csv` · `runs_summary.*` · `meta.json` | Windows |

합치기: `cd can_canoe && python3 analyze.py --log ../results/can_canoe/20261006/logs/<run_id>/canoe.asc --runs-root ../results/can_canoe/20261006/runs`
(runs-root 아래에 이 run 폴더만 두고 실행하거나, 6회를 한 로그로 받은 경우 runs 전체를 쓴다)

| run | 송신 | 수신 | 결번 | 비고 |
|---|---|---|---|---|
| 20261006_yolov6n_off_30s | 112 | 112 | 0 | 0x300 92 · 0x310 4 · 0x320 16 |
| 20261006_yolov6n_off_30s_r2 | 112 | 112 | 0 | 0x300 93 · 0x310 3 · 0x320 16 (Windows 로거 설정 변경 후) |

**주의 (이 두 run 은 수정 전 can_demo 로 잰 것):** `--duration` 이 카메라 시작 지연(약 12초)을 포함해 `fps_avg` 3.1 로 낮게 나왔고
(수신 구간 5.02 fps 가 정상 구간 값), 시작 직후 EdgeMs 가 0 으로 간 프레임이 있다 (값 없음으로 취급). 검출 박스는 화면 전체급(bicycle 2·motorcycle 1, COCO)이라 오검출 의심 — Raw 켬 이미지로 확인 필요.
