# CAN 실측 2026-10-06 (yolov6n · Raw 끔 · 30초 · 5 fps · 클래식 CAN 500 kbps)

Ubuntu 카메라 PC(Kvaser Leaf v3) → Windows 노트북(VN1630A) 수신.

**수신 방법: CANoe 를 쓰지 않았다 (2026-10-06 사용자 확정).** CANoe 대신 python-can 기반 로거(`can_canoe/canoe_logger.py`)로 받았고, 시간축은 **VN1630A 하드웨어 수신 시각**(첫 프레임 = 0, 정수 ms)이다 (`meta.json` 의 `timestamp_source`). 실제 CANoe 가 만든 `.asc` 로는 확인하지 않았다.

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

**분석 (analyze.py, 워밍업 3초 제외):** 두 run 모두 송신=수신, 카메라 시계 드리프트 r1 7.5 ppm · r2 10.7 ppm. 데이터가 15초뿐이라 참고치이고 5분 이상 run 이 필요하다. 워밍업을 제외하지 않으면 시작 직후 3프레임 버스트 때문에 667~677 ppm 으로 인위적으로 커진다.
