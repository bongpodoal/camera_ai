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

## CAN 어댑터와 CAN FD (2026-10-06 정리)
| 항목 | 내용 |
|---|---|
| Vector 어댑터 | 드라이버(XL Driver Library)가 **Windows 전용**이고 python-can 의 `vector` 인터페이스도 Windows 만 지원 (검색 결과 기준, Linux 지원 여부는 Vector 문서로 재확인 필요). → **Vector 는 CANoe PC(Windows) 쪽에 두는 것이 안전** |
| 카메라 PC (Ubuntu 22.04.5) | 송신용으로 **socketcan 이 되는 FD 어댑터**가 따로 필요 (예: PEAK PCAN-USB FD 등). 어떤 어댑터를 쓰는지 미확인 |
| 카메라 PC 를 Windows 로 | depthai 는 Windows 에서도 되고 `--interface vector` 로 보낼 수 있음. 다만 같은 Vector 채널을 CANoe 와 동시에 쓰는 구성은 확인 못 함 |
| CAN FD 모드 | 버스를 FD 로 열고(`--fd --data-bitrate 2000000`), CANoe 채널의 중재 속도(500k)·데이터 속도(2M)와 **같아야** 함 |
| 프레임 형식 | 기본은 클래식 8바이트 프레임(FD 버스에서도 통용). `--fd-frames` 를 주면 같은 8바이트를 FD 프레임(BRS)으로 보냄. 이때는 `oakd_canoe_fd.dbc` 를 CANoe 에 사용 |
| 아직 안 한 것 | FD 의 64바이트 활용(한 프레임에 박스 여러 개 묶기)은 구현 안 함 |

Ubuntu 에서 FD 어댑터 켜기 (socketcan):
```bash
sudo ip link set can0 up type can bitrate 500000 dbitrate 2000000 fd on
```

## 카메라 PC 쪽
```bash
sudo ip link set can0 up type can bitrate 500000        # PCAN 등 socketcan 어댑터일 때
cd can_canoe
NIC=<이더넷이름> V8_ARCHIVE=<T7의 yolov8n NNArchive> bash run_matrix.sh
# CANoe 로그를 가져온 뒤
python3 analyze.py --log canoe.asc --runs-root runs/<날짜_시각>
```
Vector 어댑터면 `INTERFACE=vector CHANNEL=0` 같이 지정한다 (python-can 의 vector 드라이버, 설정은 어댑터에 따라 다름).

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
