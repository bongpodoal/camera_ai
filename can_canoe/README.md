# can_canoe — OAK-D 결과를 CAN 으로 보내 받고(CANoe 대신 python-can 로거), 시간축을 수신 시각 하나로 통일

> **2026-10-06 사용자 확정: CANoe 는 쓰지 않는다.** 수신은 `canoe_logger.py`(VN1630A 하드웨어 수신 시각). 아래 "CANoe" 표현은 이 수신 시각 기준 지점을 가리킨다.

과제: 카메라 출력(CAN 수신) · 원본(Raw) 화면 기준 인식 수준(후처리) · Raw 수신 여부에 따른 연산/통신 속도 비교 · 3가지 모델.
지난 과제 지적: 카메라(엣지) 시계를 시간축으로 쓰면 시간이 갈수록 오차가 커진다 → **CANoe 가 받은 시각 하나로 통일**.
(AURIX 는 쓰지 않기로 함. 이전 작업은 `_aurix_unused/` 에 보관)

```
OAK-D --이더넷--> 카메라 PC (can_demo.py) --CAN 500 kbps--> CANoe PC (받은 시각을 로그에 찍음 = 시간축)
                      │                                         │
                  frames.csv 등                            canoe.asc / .blf
                      └────────────── analyze.py ───────────────┘
                     → frames_axis.csv (정수 ms 시간축) · compare.md (비교표) · drift.png
```

| 과제 문장 | 이 폴더에서 |
|---|---|
| 카메라 출력 (CAN 수신) | `can_demo.py` 가 FRAME_STATUS·DET_BOX·PERF 송신 → CANoe Trace 에 표시·로그 |
| Raw 화면 기준 인식 수준 (후처리) | `--raw on` 이 처리된 RGB 프레임에 박스를 그려 1초에 1장(과 깊이 프레임 PNG) 저장 · `detections.csv` · `analyze.py` 의 검출 비율·평균 신뢰도·클래스별 개수 (**정답 비교 인식률은 아직 아님**) |
| CAN 으로 AI 출력 결과 | `oakd_canoe.dbc` 를 CANoe 에 넣으면 이름·값으로 보임 |
| Raw 수신 여부에 따른 연산/통신 속도, 3모델 | `run_matrix.sh` 가 3모델 × Raw 끔/켬 = 6번 → `compare.md` 의 FPS·지연·이더넷 MB/s·CAN 부하 변화. **Raw 켬 = 카메라로 받을 수 있는 모든 데이터** (아래 표) |
| 시간축 (CAN 으로 다시 설정) | `t_axis_ms` = CANoe 수신 시각 · 카메라/PC 시계가 벌어지는 속도(ppm) 별도 보고 |

> **바로 측정하려면 `MEASURE.md` 를 따라가면 된다** (점검 `preflight.py` → 60초 확인 → `run_matrix.sh`).

## Raw 의 정의 (2026-10-07 교수님 설명으로 정정): "카메라로 받을 수 있는 모든 데이터를 다 받았을 때"
| | Raw 끔 | **Raw 켬 (깊이 포함 모든 데이터)** |
|---|---|---|
| 칩에서 도는 것 | 검출망 | 검출망 + **스테레오 깊이 + 깊이 포함 검출망(SpatialDetectionNetwork)** + 시스템 로거 |
| CAN 으로 | FRAME_STATUS · DET_BOX · PERF | 위 + DET_POS(X/Y/Z mm) · DET_ROI(깊이 ROI) · FRAME_META_A/B/C · FRAME_TIME_DEV/HOST · DEV_TEMP · DEV_MEM_A/B/C · CALIB_A/B/C · DEV_INFO |
| 이더넷으로 (CAN 불가) | 검출 결과만 | 처리된 RGB 프레임 + 깊이 프레임 (크기를 세고 1초 1장 저장) |
| 주기 | 프레임마다 | 프레임마다(메타·위치) · 1초(칩 상태) · 10초(보정·장치 정보) |

- 범위는 지난 과제의 89개 파라미터(`example/07_host_output/params.py`)와 같다. 거리·방위각·면적비 등 **다른 값에서 계산되는 값은 받는 쪽에서 계산**하므로 따로 보내지 않는다. 보내지 않는 것: `lens_pos_raw`(고정초점이라 의미 없음), `angle_deg`(OBB 모델 전용), 파일 경로.
- 로그에서 추가 메시지 풀기: `python3 extra_messages.py --log canoe.asc --out 추가메시지/` (메시지별 CSV, DEV_INFO 문자열 복원). `canoe_logger.py` 의 기존 CSV 는 그대로이고, 추가 메시지는 `canoe.asc` 에 이미 들어 있다.
- 예상(미측정): 깊이 계산은 칩 부하가 커서 지난 과제에서 30 fps 면 프레임이 25% 누락됐다. 5 fps 에서는 괜찮을 것으로 보지만 **실측 필요**.

| 파일 | 역할 |
|---|---|
| `oakd_canoe.dbc` | 메시지 정의 FRAME_STATUS 0x300 · DET_BOX 0x310 · PERF 0x320 (클래식 프레임, ASCII 만) |
| `oakd_canoe_fd.dbc` | 같은 내용, 프레임 형식만 CAN FD (`--fd-frames` 로 보낼 때 사용) |
| `can_msgs.py` | 인코딩/디코딩 |
| `can_demo.py` (+`_no_comments`) | 카메라 → CAN 송신, 실행 기록 (`frames.csv`, `detections.csv`, `summary.csv`, `images/`) |
| `oak_full.py` (+`_no_comments`) | `--raw on` 의 데이터 수집·CAN 메시지 변환 |
| `extra_messages.py` (+`_no_comments`) | 로그에서 `--raw on` 추가 메시지를 CSV 로 풀기 |
| `preflight.py` | 측정 전 점검 (패키지·DBC·카메라·모델 파일·CAN·이더넷 이름) |
| `analyze.py` (+`_no_comments`) | CANoe 로그 + 실행 기록 → 시간축·드리프트·비교표 |
| `canoe_sim.py` | CANoe 흉내 (로그 저장). CANoe 없는 곳에서 시험용 |
| `canoe_logger.py` (+`_no_comments`) | **Windows 노트북 수신 로거** (CANoe 없이 측정용). `canoe.asc` 저장 → `FRAME_STATUS/DET_BOX/PERF.csv`(t_axis_ms) · `runs_summary.csv/md`(실행별 FPS·결번·지연·박스 수·CAN 부하). 실행 구분은 analyze.py 와 같은 규칙. `--idle-exit N` 으로 자동 종료, `--summarize DIR` 로 표 재생성 |
| `selftest.py` | 카메라·CANoe 없이 전체 흐름 검증 |
| `run_matrix.sh` | 6번 측정을 한 번에 |

## CANoe 쪽 설정 (CANoe PC, Windows) — 일반적인 순서, 메뉴 이름은 버전에 따라 다를 수 있음
1. 새 설정 또는 기존 `Test1.cfg` 를 연다.
2. 데이터베이스에 `oakd_canoe.dbc` 를 추가한다 (기존 `AURIX_0920_INTEGRATED.dbc`, `OAKD_EdgeRaw_CANoe19_NoVAL.dbc` 는 이 측정에는 필요 없음).
3. CAN 채널 속도를 **500 kbps** 로, 카메라 PC 의 CAN 어댑터와 CAN_H/CAN_L 을 잇는다 (양 끝 120 Ω 종단).
4. Trace 창에 FRAME_STATUS 등이 이름·값으로 보이는지 확인한다.
5. Logging 블록을 켜고 저장 형식을 `.asc` (또는 `.blf`) 로 한다. **측정 시작 → run_matrix.sh 실행 → 끝나면 측정 중지** 순서.

> **2026-10-06 결정: 클래식 CAN 500 kbps 로 낮춤** (카메라 PC 의 Kvaser Leaf v3 의 FD 지원 불확실). CANoe 에는 `oakd_canoe.dbc` (FD 아님), 채널은 클래식 500 kbps. 아래 FD 내용은 참고용.

## 확정 구조 (2026-10-06): 카메라 PC → CAN FD → Windows 노트북 (Vector VN1630A + CANoe)
```
OAK-D ─이더넷→ Ubuntu 22.04.5 (can_demo.py) ─ FD 어댑터 ──CAN_H/CAN_L, 양 끝 120 Ω── Vector VN1630A ─ Windows 노트북 (CANoe 로깅)
```
| 항목 | 내용 |
|---|---|
| 속도 | 중재 구간 **500 kbps**, 데이터 구간 **2 Mbps**, 샘플 포인트 약 80% (두 쪽이 같아야 함) |
| 프레임 | `--fd-frames` (같은 8바이트를 CAN FD 프레임·BRS 로 보냄). CANoe 에는 **`oakd_canoe_fd.dbc`** 를 추가 |
| Vector VN1630A | Windows 에서만 동작 (드라이버·python-can `vector`). VN1600 계열은 CAN FD 지원으로 알고 있으나 **VN1630A 의 FD 지원은 데이터시트로 최종 확인 필요** |
| 카메라 PC 어댑터 | **socketcan 이 되는 FD 어댑터가 필요** (예: PEAK PCAN-USB FD). 모델 미확인 |
| 시간축 | Windows 노트북(Vector 하드웨어)이 프레임을 받은 시각 |

Ubuntu 쪽 (FD 켜기):
```bash
sudo ip link set can0 up type can bitrate 500000 sample-point 0.8 dbitrate 2000000 dsample-point 0.8 fd on
ip -details link show can0        # fd on, 속도 확인
```
Windows 노트북 (CANoe 19) — 메뉴 이름은 버전에 따라 다를 수 있음:
1. Vector Hardware Config 에서 VN1630A 의 채널 하나를 CANoe 의 CAN 1 채널에 할당한다.
2. CANoe 의 해당 CAN 채널을 **CAN FD 모드**로 두고 중재 500 kbps · 데이터 2000 kbps, 샘플 포인트 80% 로 맞춘다.
3. 데이터베이스에 `oakd_canoe_fd.dbc` 추가 → Trace 창 확인 → Logging 블록으로 `.asc` 저장.
4. **측정 시작 후** Ubuntu 에서 `can_demo.py` 실행.

CANoe 가 막히면 대안 (**미검증**): Windows 노트북에 Python 과 Vector 드라이버만 설치하고 CANoe 없이 받기.
```bash
pip install python-can cantools numpy
python canoe_sim.py --interface vector --channel 0 --fd --data-bitrate 2000000 --out canoe.asc
```
(채널 번호는 Vector Hardware Config 의 응용 채널 할당을 따르고, 필요하면 `--app-name` 으로 응용 이름을 지정)

| 아직 안 한 것 | |
|---|---|
| FD 64바이트 활용 | 한 프레임에 박스 여러 개 묶기 — 구현 안 함 |
| 실장비 시험 | 모든 CAN 경로가 맥의 가상 버스에서만 확인됨 |

## 카메라 PC 쪽 (Kvaser Leaf v3: `INTERFACE=kvaser CHANNEL=0`, 드라이버 설치는 PROGRESS.md 2026-10-06 추가 4)
Windows 노트북 절차는 `WINDOWS_SETUP.md`.
```bash
sudo ip link set can0 up type can bitrate 500000        # 클래식 (기본). FD 면: ... bitrate 500000 sample-point 0.8 dbitrate 2000000 dsample-point 0.8 fd on
cd can_canoe
NIC=<이더넷이름> V8_ARCHIVE=<T7의 yolov8n NNArchive> bash run_matrix.sh
# CANoe 로그를 가져온 뒤
python3 analyze.py --log canoe.asc --runs-root runs/<날짜_시각>
```
run_matrix.sh 는 기본이 **클래식 CAN 500 kbps** (FD=0, FD_FRAMES=0, 2026-10-06 변경) 다. CAN FD 로 하려면 `FD=1 FD_FRAMES=1`.

## 측정 시간 · EdgeMs (2026-10-06 수정)
- `--duration` 은 **첫 프레임이 온 뒤부터** 잰다. 카메라가 켜지는 시간(약 12~16초)은 `summary.csv` 의 `startup_s` 로 따로 기록 (`fps_avg`·`eth_MBps` 도 첫 프레임부터).
- 칩 지연값(EdgeMs)이 프레임보다 약 20 ms 늦게 오는 프레임이 10~18% 있다. 기본은 **기다리지 않고** 보내서(`--edge-wait 0`) 그 프레임의 EdgeMs 는 0 = **값 없음**(분석에서 제외, `frames.csv` 의 `edge_ms` 에는 값이 다 있음). `--edge-wait 0.25` 로 기다리면 EdgeMs 는 채워지지만 그 프레임 송신이 늦어 수신 간격 표준편차가 0.4 → 약 10 ms 로 커진다 (2026-10-06 A/B 측정).

## 비교 모델 (2026-10-07 변경)
`run_matrix.sh` 의 3모델 = **yolov6n**(COCO) · **traffic_light_v8n**(바탕화면 `last.pt`, YOLOv8n 신호등, red·green 2클래스) · **traffic_light**(YOLO11s, 4클래스). 기존 yolov8n(COCO) 자리를 `traffic_light_v8n`(ModelId 4)이 대신한다. 모델 파일은 `traffic_light/05_nnarchive/traffic_light_v8n-416x416.tar.xz` (git 제외, 이 PC 에서 `traffic_light/` ②~⑤ 로 만듦). Windows 로거는 `git pull` 로 `can_msgs.py` 의 ModelId 4 이름만 받으면 된다.

## PERF 는 별도 타이머로 정확히 1초마다 (2026-10-06)
- `can_demo.py` 의 PERF(0x320)는 프레임 도착과 상관없는 **별도 타이머 스레드**가, 첫 프레임 기준 **k초 + 50 ms (k=1,2,3…)** 에 보낸다 (이전에는 프레임이 올 때만 확인해서 약 1.2초 간격, 시각도 883·2081 ms 처럼 어긋남). 가상 채널 시험: 수신 시각 1.05·2.05·3.05… 초, 간격 1000 ms.
- +50 ms 는 수신 쪽에서 소수점을 버려 정수 초로 만들어도 k 로 안정적으로 떨어지게 하는 여유다.
- 수신 로그(`PERF.csv`)의 시간 열은 ms 가 아니라 **정수 초(소수점 버림)** 로 기록한다 (`t_axis_s`).

## 시간축이 이렇게 정해진다
| 값 | 무엇의 시계 | 용도 |
|---|---|---|
| `t_axis_ms` | **CANoe** (프레임을 받은 순간, 첫 프레임 = 0, 정수 ms) | 모든 그래프의 x축 |
| `cam_minus_canoe_ms` | 카메라 시계 − CANoe 시계 | 시간이 갈수록 커지는지 = 지난 과제 지적의 증거 (기울기 = ppm) |
| `edge_ms`, `pc_ms` | 같은 시계끼리 뺀 짧은 구간 | 드리프트 영향 거의 없음. 시간축으로는 쓰지 않음 |

## 검증 상태
| 항목 | 상태 |
|---|---|
| DBC 파싱·인코딩/디코딩 | 맥에서 cantools 로 확인 |
| `selftest.py` (가상 CAN, 4번 실행, 시계를 일부러 틀어 ppm 복원, 정수 ms 시간축, 송수신 일치) | 통과 |
| 실제 카메라 경로 (`OakSource`, `--raw off` 의 칩 위 버림 Script) | **미검증** (카메라 PC 필요) |
| 실제 CANoe 에서 DBC 로드·Logging·`.asc` 읽기 | **미검증** (CANoe 필요. 읽기는 python-can 의 LogReader 사용 — CANoe 가 만든 `.asc`/`.blf` 로 확인 필요) |
| 인식률(정답 비교) | 아직 안 함 (나중에 별도 논의) |
