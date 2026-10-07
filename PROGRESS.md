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
3. ⑦ CAN: `can_canoe/` 로 대체 (2026-10-06, 아래 절)
4. ① 원본 출처 확인

## 2026-10-01 — 지연 측정 준비 · 416 변환 · YOLO11n 재학습 준비

| 항목 | 내용 |
|---|---|
| 지연 원인 정리 | 엣지 지연 ≈ 추론 간격 × 8장 (3모델 공통) → 칩 안 큐 대기로 추정. 문서 "OAK-D 지연 원인 정리" (CLAUDE.md 8절) |
| 측정 스크립트 | `tools/latency_latest.py`, `run_latest_3models.sh`: 카메라 5 fps · AI 입력 큐 크기 1 비차단 · 화면 창 끔 · 5분. 가짜 depthai 로 흐름 검증, **실측 전** |
| 입력 크기 | YOLOv6n 512×384 그대로 (Luxonis 저장소에 416 없음), YOLOv8n·신호등 416×416 으로 ②~⑤ 재변환 |
| 416 검증 | ONNX vs 원본 .pt 최고 후보 신뢰도·박스 일치 (YOLOv8n 1장 0.7744, 신호등 3장). depthai 가 416×416 으로 읽음 |
| 변환 스크립트 | ②~⑤ 에 `[크기 [이름]]` 인자 추가 (기본 512x288 traffic_light) |
| YOLO11n 결정 | 11s 과도 → 11n 재학습. 공개 모델 없음. 맥 M5 학습 4~5.5시간(960) 실측 → RTX 4080 PC 에서 학습 |
| 학습 스크립트 | `traffic_light/00_train/train_yolo.py` (+ `_no_comments`): 데이터셋 자동 다운로드, 11s 와 같은 설정, 960·416 평가. 합성 데이터 1 epoch 로 흐름 검증 |

## 2026-10-06 — CAN 과제 (`can_canoe/`, AURIX 대신 CANoe)

| 항목 | 내용 |
|---|---|
| 과제 | 카메라 출력 CAN 수신 · 원본 화면 기준 인식 수준(후처리) · Raw 수신 여부별 연산/통신 속도 · 3모델 |
| 지적 사항 | 카메라(엣지) 시계를 시간축으로 쓰면 시간이 갈수록 오차가 커짐 |
| 계획 변경 | AURIX 사용 안 함 → 수신·시간축은 CANoe (`_aurix_unused/` 에 이전 작업 보관) |
| 구성 | PC 가 검출 결과를 CAN 500 kbps 로 송신 → CANoe 가 받은 시각을 로그에 찍음 = 시간축(정수 ms). 카메라·PC 시계는 CANoe 시계에서 벌어지는 속도(ppm)만 따로 보고 |
| DBC | `oakd_canoe.dbc`: FRAME_STATUS 0x300 · DET_BOX 0x310 · PERF 0x320 (값 이름표 없음, ASCII) |
| Raw | 원본 = AI 입력 프레임. `--raw on` 이더넷으로 받아 박스 그림, `--raw off` 칩 위 Script 가 버림 |
| 측정 | `run_matrix.sh` 3모델 × Raw 끔/켬 = 6번 → `analyze.py` 가 `compare.md` · `frames_axis.csv` · `drift.png` |
| 검증 | 맥에서 `selftest.py` 통과 (가상 CAN, 4번 실행을 한 로그에서 분리·짝짓기, ppm 복원, 시간축 정수 ms) |
| 미검증 | 실제 카메라 경로, 실제 CANoe 의 DBC 로드·로그 읽기, 6회 실측 |
| 보류 | 인식률(정답 비교) 테스트 — 합성 영상·LISA·AI Hub 후보, 나중에 논의 |

## 2026-10-06 (추가) — 장비 구조 확정, CAN FD 옵션

| 항목 | 내용 |
|---|---|
| 구조 | 카메라 PC(Ubuntu 22.04.5) → CAN → Windows PC(CANoe, Vector 어댑터) 로깅 |
| Vector | 드라이버·python-can `vector` 가 Windows 전용 (검색 근거) → Windows 쪽에 연결 |
| CAN FD | 선택. `--fd`, `--data-bitrate`, `--fd-frames`, `oakd_canoe_fd.dbc` 추가. 맥 selftest 에서 FD 프레임 로그·분석 통과. 실장비 미확인 |
| 다음 | Ubuntu PC 에서 `can_canoe/README.md` 순서대로 (vcan0 → 실제 CAN → 6회 실측) |

## 2026-10-06 (추가 2) — 장비 확정: Windows 노트북 + Vector VN1630A, CAN FD

| 항목 | 내용 |
|---|---|
| 구조 | 카메라 PC(Ubuntu) → CAN FD → Windows 노트북(VN1630A, CANoe 로깅) |
| FD 설정 | 500 kbps / 2 Mbps / 샘플 포인트 80%. `run_matrix.sh` 기본이 FD, DBC 는 `oakd_canoe_fd.dbc` |
| 코드 | vector 채널 번호(정수) 처리, `canoe_sim.py --app-name`. 맥 selftest 통과 (가상 버스) |
| 미확인 | 카메라 PC 의 FD 어댑터 모델, VN1630A 의 FD 지원(데이터시트), 실제 CANoe 로그 읽기, 실제 카메라 경로 |

## 2026-10-06 (추가 3) — 클래식 CAN 으로 낮춤

| 항목 | 내용 |
|---|---|
| 변경 | `run_matrix.sh` 기본 FD=0 · FD_FRAMES=0 (클래식 500 kbps), CANoe 는 `oakd_canoe.dbc` |
| 이유 | 카메라 PC 어댑터 Kvaser Leaf v3 의 FD 지원 불확실 |
| 막힘 | 이 PC 에서 Leaf v3 가 `can0` 로 안 잡힘 (커널 kvaser_usb 가 ID 0117 미지원) → LinuxCAN 드라이버 또는 다른 어댑터 |
| 준비됨 | Python 환경, 카메라 ping, 모델 3개 (T7 원본과 동일) |

## 2026-10-06 (추가 4) — Kvaser 드라이버 설치, Windows 인계

| 항목 | 내용 |
|---|---|
| 문제 | Leaf v3 (USB `0bfd:0117`) 를 커널 `kvaser_usb` 가 지원 안 해 `can0` 없음 |
| 설치 | Kvaser LinuxCAN 5.52 (`linuxcan_5_52_563`) — gcc-12 필요(`sudo apt install gcc-12`), `make` → `sudo make install` → `sudo make load`. 비밀번호 없으면 불가 |
| 확인 | `listChannels`: ch0 = Kvaser Leaf v3 (s/n 17930), ch1·2 = Kvaser Virtual CAN. `/usr/lib/libcanlib.so` |
| 코드 | python-can `kvaser` 가 Leaf v3 에서 `canIoCtl LOCAL_TXACK` 에러 → `can_msgs.open_bus()` 로 무시 (`can_demo`, `canoe_sim` 적용) |
| 시험 | 가상 채널 ch1 송신(`can_demo --fake`) → ch2 수신(`canoe_sim`) 10초: 송신 137 · 수신 130 프레임, 에러 0. 실제 버스(VN1630A) 는 미확인 |
| Windows | `can_canoe/WINDOWS_SETUP.md` 신규. 클래식 500 kbps · `oakd_canoe.dbc` |
| 다음 | Windows CANoe 설정 + 배선 → `--fake` Trace 확인 → 실카메라 1모델 → `run_matrix.sh` 6회 |

## 2026-10-06 (추가 5) — 실카메라 CAN 실측 2건, can_demo 수정, Windows 협업

| 항목 | 내용 |
|---|---|
| 협업 | 두 PC Claude 세션 크로스 세션 메시지로 조율. 막힌 원인: Windows `crossSessionInbound` 미설정 + 권한 모드 차이(bypass↔auto)로 메시지 보류 → 양쪽 `accept` 로 해결 |
| 프로토콜 | 사용자 요청 → Ubuntu `START` → Windows 로거 켜고 `READY` → Ubuntu 카메라 실행 → `RESULT` → Windows `LOGGED` |
| 실측 | yolov6n Raw 끔 30초 2회: 송신 112 = 수신 112, 결번 0, 에러 0, 수신 5.02~5.03 fps, EdgeMs 중앙값 69~70 ms (`results/can_canoe/20261006/`) |
| 발견 | 카메라 시작 지연 약 12초가 `--duration`·`fps_avg` 에 섞임(3.1). 처음 프레임 EdgeMs 0 전송(r2 8개), 처음 2프레임 pc_ms 음수. 검출 3~4개는 화면 전체급 박스(bicycle·motorcycle) → 오검출 의심 |
| 수정 | `can_demo.py`(+`_no_comments`): duration 을 첫 프레임부터, `startup_s` 기록, EdgeMs 대기(0.25초). Kvaser 가상 채널 송수신: EdgeMs 0 프레임 101개 중 0개, selftest 통과 |
| 점검 | Windows 로거 피드백: 타임스탬프 출처(VN1630A 하드웨어), 절대시각 meta, 드리프트는 5분 이상 필요. 이 노트북에 CANoe 미설치 → 대체 로거 사용 명시 또는 CANoe PC 에서 1회 필요 (사용자 결정 대기) |
| 다음 | 사용자 지시 시: Raw 켬 60초 확인 → DURATION=300 으로 6회 (약 40분) |

## 2026-10-06 (추가 6) — Windows 노트북 수신 확인 · 로거 구성

| 항목 | 내용 |
|---|---|
| 노트북 | Git 2.55 · python-can 4.6.1 · cantools 설치. VN1630A 인식 (s/n 60643, 채널 1·2). CANoe 는 설치 안 됨 → Python 로거로 대체 |
| 실수신 | Kvaser Leaf v3 → VN1630A ch1, 클래식 500 kbps. `--fake` 257프레임, 실카메라 yolov6n raw off 255프레임 (5.0 fps, 결번 0, 박스 93/93), DBC 해석 실패 0 |
| 로거 | `can_canoe/canoe_logger.py` (+`_no_comments`): `canoe.asc` + 메시지별 CSV(t_axis_ms) + `runs_summary` + `meta.json`. 저장 기본값 바탕화면 `can_logs\<날짜_시각>`. `--idle-exit`/`STOP` 종료, `--summarize` 재생성 |
| 시간축 | 타임스탬프 = VN1630A 하드웨어 수신 시각 (python-can vector, Vector XL 드라이버 `timeStamp`). 절대 시각 기준점만 버스를 연 순간의 PC 시계. `meta.json` 의 `timestamp_source` 에 기록 |
| 피드백 반영 | `EdgeMs=0` 제외, 첫 PERF 제외, 첫 2프레임 제외 간격, `fps_10s`, ID별 개수, 클래스 이름, `gap_before_s`·`t_start_wall_iso`, `definitions`. `meta.json` 을 UTF-8 로 통일(한글로 요약이 죽던 버그) |
| 시험 | 가상 버스 다실행 분리·결번 검출, 실측 2건 재요약 (`results/can_canoe/20261006/logs/`) |
| 미확인 | 6회·5분 실측, 실제 CANoe 가 만든 .asc, 로거의 `--raw on` 실카메라 경로, 실제 VN1630A 경로의 새 `meta.json` 항목 |

## 2026-10-06 (추가 7) — CANoe 미사용 확정, 드리프트 워밍업 제외

| 항목 | 내용 |
|---|---|
| 결정 | CANoe 는 쓰지 않는다 (사용자 확정). 수신·시간축 = `canoe_logger.py` (python-can, VN1630A 하드웨어 수신 시각). 문서에 명시 |
| 합치기 | git 에서 Windows 로그 pull → `analyze.py` 로 r1 92/92, r2 93/93 합치기 성공. Windows 로거 `.asc` 를 python-can 이 정상 읽음 |
| 발견 | 드리프트 667~677 ppm 은 시작 직후 3프레임 버스트(cam_minus_canoe 0→82 ms 후 평탄)로 생긴 인위적 값 |
| 수정 | `analyze.py`(+`_no_comments`): 직선 맞춤에서 시작 후 `--warmup-s`(기본 3초) 제외 → r1 7.5 · r2 10.7 ppm. selftest 통과 |
| 다음 | 사용자 지시: Raw 켬 60초 → 5분 이상 측정 (Windows 로거 먼저 켜고 READY 후 Ubuntu 실행) |

## 2026-10-06 (추가 8) — r3 시험으로 EdgeMs 대기의 부작용 발견, 기본값 되돌림

| 항목 | 내용 |
|---|---|
| r3 (yolov6n Raw 끔 30초, 수정된 can_demo) | 송신 183 = 수신 183, 결번 0, edge_zero_frames 0, rx 29.67초, fps_10s 5.2/5.0, startup_s 12.1 |
| 발견 | 수신 간격 표준편차 r2 5.38 → r3 20.13 ms. 카메라 간격은 200 ms 그대로(std 0) → Ubuntu 송신 쪽 지터 |
| 원인 | EdgeMs 대기(최대 0.25초): 칩 지연값이 프레임보다 약 20 ms 늦게 오는 프레임이 10~18% 있어 그 프레임 송신이 늦어짐 |
| A/B (가상 채널, 실카메라 20초) | 대기 켬: 송신 간격 std 9.5 ms (179~221) · 대기 끔: 0.4 ms (199~201), 늦은 프레임 14~18% |
| 결정 | `--edge-wait` 옵션 신설, **기본 0 (안 기다림)** → 지터 방지. 그 프레임 EdgeMs=0=값 없음(분석 제외), Ubuntu `frames.csv` 에는 값이 다 있음. 필요하면 `--edge-wait 0.25` |

## 2026-10-06 (추가 9) — r3 로그 합치기

| 항목 | 내용 |
|---|---|
| 합치기 | r3 송신 151 / 수신 151, `analyze.py` 정상. results 에 Ubuntu 송신 기록 추가 |
| 드리프트 | r3 −90.5 ppm (r1 7.5 · r2 10.7): EdgeMs 대기 켠 상태의 송신 지터(±20 ms)가 직선 맞춤에 섞인 값 → 신뢰 안 함. 대기 끈 기본값으로 5분 이상 재측정 필요 |

## 2026-10-06 (추가 10) — PERF 를 별도 타이머로, 정수 초 기록

| 항목 | 내용 |
|---|---|
| 문제 | PERF 간격이 약 1.2초 (프레임이 올 때만 1초 경과를 확인, 시각 883·2081 ms…) |
| 수정 | `can_demo.py`(+`_no_comments`): 타이머 스레드가 첫 프레임 기준 k초+50 ms 에 정확히 1초 간격 송신. 메인 루프와 공유하는 값·CAN 송신은 RLock 으로 보호 |
| 검증 | Kvaser 가상 채널 fake 12초: PERF 수신 1.05~11.05초, 간격 1000 ms 11개, 내림하면 1~11. selftest 통과 |
| 기록 | `PERF.csv` 시간 열을 ms 대신 정수 초(소수점 버림, `t_axis_s`)로 — Windows 로거 수정 요청 |

## 2026-10-07 (추가 11) — 2번째 모델을 YOLOv8n(COCO) → 바탕화면 `last.pt`(신호등 YOLOv8n)로 교체

| 항목 | 내용 |
|---|---|
| 요청 | 3모델 비교의 yolov8n 자리를 바탕화면의 `lask.pt` 로 (실제 파일명 `~/Desktop/last.pt`, 오타로 판단) |
| 모델 정보 (체크포인트) | YOLOv8n detect, 파라미터 3.0 M, **클래스 2개 (red·green)**, 640 학습, epoch 39(40 epochs), 학습일 2026-07-29, 데이터 `dataset_fixed_v2`. `01_pytorch_pt/traffic_light_v8n.pt` 와 바이트 동일 (git 제외) |
| 변환 (traffic_light/ ②~⑤, 416×416) | ② ONNX 출력 `[1,7,52,52]·[1,7,26,26]·[1,7,13,13]` (7 = 박스 4 + 신뢰도 1 + 클래스 2) → ③ IR(6.0 MB) → ④ blob(SHAVE 8, 6.1 MB) → ⑤ NNArchive 5.5 MB, depthai 에서 열림 (입력 416×416, 클래스 red·green). 이름 `traffic_light_v8n` |
| 환경 | 이 PC 에 `~/venvs/tl_convert` (시스템 패키지 + depthai 3.10 + onnx · onnxruntime · blobconverter · matplotlib) 신규. 시스템 matplotlib 이 numpy 2 와 충돌해 venv 안에 따로 설치 |
| 코드 | `can_msgs.MODEL_IDS` 에 `traffic_light_v8n: 4`, DBC ModelId 설명 `4=traffic_light_v8n`, `can_demo`(ARCHIVES), `analyze`(라벨 red·green), `run_matrix.sh` 모델 목록 = yolov6n · traffic_light_v8n · traffic_light (yolov8n 제거, `V8_ARCHIVE` 삭제) |
| 시험 | 실카메라 20초 (가상 CAN): 5 fps, 엣지 지연 80.3 ms (yolov6n 69.5), 검출 0개 (장면에 신호등 없음, 정상). 실제 신호등 인식은 미확인 |
| 공개 | 가중치·NNArchive 는 git 에 올리지 않음 (사용자가 공개 여부 결정) |

## 2026-10-07 (추가 12) — 3모델 5분 측정 완료 (Raw 끔)

| 항목 | 내용 |
|---|---|
| 조건 | 각 300초, 5 fps, 클래식 CAN 500 kbps, Raw 끔, 기본 `--edge-wait 0`, PERF 별도 타이머. 순서 yolov6n → traffic_light_v8n(last.pt) → traffic_light(YOLO11s). 카메라 위치는 사용자가 디버그 창(`~/Desktop/oakd_debug_view.py`)으로 맞춤 |
| 송신=수신 | 11,629 / 1,822 / 1,918 프레임 모두 일치, CAN 결번 0 |
| 엣지 지연 중앙 | 71 / 80 / 154 ms |
| 검출 | yolov6n 박스 10,276개(DET_BOX 9,823, 프레임당 8개 제한으로 453 잘림) · v8n 20개(red 11·green 9, 검출 없는 프레임 98.7%) · 11s 116개(green 106·red 8·off 2, 93.8%) |
| PERF | 세 run 모두 t_axis_s 1~300 연속, 중복·누락 0, 간격 1000.0 ms(std 0.1). 새 열(frame_seq·edge_ms·det_count·box_*) 채워짐 |
| 시간 | 수신 구간 300.05초, fps_rx 5.0(10초 구간 모두 5.0~5.1), 간격 std(처음 2프레임 제외) 1.13 / 1.22 / 0.97 ms |
| EdgeMs=0 비율 | 12.6% / 7.9% / 11.8% (늦게 오는 칩 지연값, 값 없음 처리) |
| 문제 | 2/3 첫 시도 카메라 시작 실패(`Couldn't open stream`) → 30초 후 재시도 성공. 1/3 `seconds` 305.4(종료 시간 혼입) |
| Windows 로거 개선(미커밋) | 기대 박스 수=sum(min(DetCount,8)), `det_count_sum`·`frames_det_over8`, `cam_dropped_seqgap`·`can_lost_frames` 구분 열 |
| 사용자 결정 대기 | 첫 PERF 제외 규칙 제거, Windows 로그 git 업로드(허락 시 `results/can_canoe/20261007/`) |
| 미완 | Raw 켬 시험(이미지로 검출 확인), 인식률(정답 비교), `can_demo` seconds 보정 |

## 2026-10-07 (추가 13) — 5분 3모델 합치기, 드리프트 실측, 첫 PERF 제외 규칙 제거 승인

| 항목 | 내용 |
|---|---|
| 로그 | 사용자가 Windows 로그를 push 함(45336c5, `results/can_canoe/20261007/logs/`), 로거 수정판 52fb619. 이 PC 에 Ubuntu 송신 기록을 `results/can_canoe/20261007/runs/` 로 복사 (미커밋) |
| 합치기 (`analyze.py`, 워밍업 3초 제외) | 송신 = 수신: 1501/1501, 1502/1502, 1502/1502 |
| **카메라 시계 드리프트** | yolov6n 13.1 · traffic_light_v8n 15.0 · traffic_light 14.1 ppm — 일관되게 약 14 ppm(카메라가 빠름), 300초 누적 3.7 · 5.3 · 4.0 ms (1시간이면 약 50 ms) |
| PC 시계 드리프트 | 3.2 · 6.9 · 8.0 ppm (300초 누적 1.0 · 2.0 · 2.4 ms) |
| 결론 | 지난 과제 지적(카메라 시계를 시간축으로 쓰면 오차가 누적)의 정량 근거. 시간축은 VN1630A 수신 시각 하나로 통일 |
| 사용자 결정 | 첫 PERF 제외 규칙 제거 승인 → Windows 로거에서 제거 요청함 (표본 3개 −0.4/0.0/+0.1 ms) |
| 대기 | Windows 로거 수정·`results/can_canoe/20261007/` 커밋·푸시는 사용자 지시 후. `can_demo` seconds 보정, Raw 켬 시험, 인식률은 미완 |

## 2026-10-07 (추가 14) — Raw 정의 정정: "카메라로 받을 수 있는 모든 데이터" (깊이 포함)

| 항목 | 내용 |
|---|---|
| 정정 | 교수님 설명: Raw = 카메라로 받을 수 있는 모든 데이터를 받았을 때를 측정 (깊이 포함, 영상 아님). 이전 `--raw on`(원본 영상만 저장)은 이 정의와 달라 교체 |
| Raw 켬 | 스테레오 깊이 + SpatialDetectionNetwork + SystemLogger. CAN: DET_POS·DET_ROI·FRAME_META_A/B/C·FRAME_TIME_DEV/HOST(프레임), DEV_TEMP·DEV_MEM_A/B/C(1초), CALIB_A/B/C·DEV_INFO(10초). 이더넷: RGB·깊이 프레임(크기만 셈, 1초 1장 저장) |
| DBC | `oakd_canoe.dbc`·`oakd_canoe_fd.dbc` 에 14개 메시지 추가 (0x330~0x370). 기존 OAKD_EdgeRaw DBC 는 없음(없어도 됨, 우리가 정의) |
| 코드 | `oak_full.py`(수집·변환), `can_demo.py`(`--raw on` 교체, telemetry.csv·session.json·깊이 PNG), `extra_messages.py`(로그에서 추가 메시지 풀기) |
| 검증 | 맥 selftest 통과 (가상 CAN: 추가 메시지 개수 일치, 장치 ID 문자열 복원, Raw 켬 CAN 부하 3.0% vs 끔 0.7%) |
| 미검증 | 실카메라 깊이 파이프라인(NNArchive 416×416 + SpatialDetectionNetwork, 최신화 큐 적용 여부), 5 fps 에서의 칩 부하·지연, 실제 로그 |

## 2026-10-07 (추가 15) — Raw 켬 측정 준비 완료

| 항목 | 내용 |
|---|---|
| 문서 | `can_canoe/MEASURE.md`: 양쪽 준비 → 점검 → YOLO11s 60초 확인 → 6회 본 측정 → 정리, 합격 기준·대처·알려진 위험 |
| 도구 | `preflight.py`(패키지·DBC·ping·모델 파일·CAN·NIC 점검), `run_matrix.sh` 에 `MODELS`·`RAWS` 선택·완료 안내 추가 |
| 5 fps 전망 | yolov6n·v8n 여유 큼(과거: 깊이 켬 20 fps 정상), YOLO11s 는 추정 한계 5.7~8.2 fps (모델 한계 9.75 fps + 깊이 오버헤드 추정) → 첫 60초 확인 필수 |
| 상태 | 맥 selftest 통과. 실카메라·실로거 미검증. 장비 세팅 후 사용자 지시로 측정 |
