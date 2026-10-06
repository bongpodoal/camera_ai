# can_canoe — OAK-D 결과를 CAN 으로 보내 CANoe 로 받고, 시간축을 CANoe 시계로 통일

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
| Raw 화면 기준 인식 수준 (후처리) | `--raw on` 이 원본(AI 입력) 프레임에 박스를 그려 1초에 1장 저장 · `detections.csv` · `analyze.py` 의 검출 비율·평균 신뢰도·클래스별 개수 (**정답 비교 인식률은 아직 아님**) |
| CAN 으로 AI 출력 결과 | `oakd_canoe.dbc` 를 CANoe 에 넣으면 이름·값으로 보임 |
| Raw 수신 여부에 따른 연산/통신 속도, 3모델 | `run_matrix.sh` 가 3모델 × Raw 끔/켬 = 6번 → `compare.md` 의 FPS·지연·박스 그리기 시간·이더넷 MB/s·CAN 부하 |
| 시간축 (CAN 으로 다시 설정) | `t_axis_ms` = CANoe 수신 시각 · 카메라/PC 시계가 벌어지는 속도(ppm) 별도 보고 |

| 파일 | 역할 |
|---|---|
| `oakd_canoe.dbc` | 메시지 정의 FRAME_STATUS 0x300 · DET_BOX 0x310 · PERF 0x320 (클래식 프레임, ASCII 만) |
| `oakd_canoe_fd.dbc` | 같은 내용, 프레임 형식만 CAN FD (`--fd-frames` 로 보낼 때 사용) |
| `can_msgs.py` | 인코딩/디코딩 |
| `can_demo.py` (+`_no_comments`) | 카메라 → CAN 송신, 실행 기록 (`frames.csv`, `detections.csv`, `summary.csv`, `images/`) |
| `analyze.py` (+`_no_comments`) | CANoe 로그 + 실행 기록 → 시간축·드리프트·비교표 |
| `canoe_sim.py` | CANoe 흉내 (로그 저장). CANoe 없는 곳에서 시험용 |
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
