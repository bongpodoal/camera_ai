# Windows 노트북 설정 (Vector VN1630A + CANoe 19) — git pull 후 이 순서대로

역할: 카메라 PC(Ubuntu)가 보낸 CAN 프레임을 **받아서 시각을 기록**한다 (시간축 = 이 노트북이 받은 시각).
이 노트북에는 카메라·모델 파일이 필요 없다. 필요한 것: 이 폴더의 `oakd_canoe.dbc`, (대안용) `canoe_sim.py`, (분석용) `analyze.py`.

## 결정 사항 (2026-10-06)
| 항목 | 값 |
|---|---|
| CAN 종류 | **클래식 CAN 500 kbps** (FD 아님). DBC = `oakd_canoe.dbc` |
| 송신 (Ubuntu 카메라 PC) | Kvaser Leaf v3 → `python-can` `--interface kvaser --channel 0` |
| 수신 (이 노트북) | Vector VN1630A (COM2 에 연결), CANoe 19 |
| 배선 | Leaf v3 CAN_H/CAN_L ↔ VN1630A CAN_H/CAN_L, 버스 양 끝 120 Ω 종단 |

## 1. 저장소 받기
```
git clone https://github.com/bongpodoal/camera_ai.git
cd camera_ai\can_canoe
```
이미 받았으면 `git pull`.

## 2. 드라이버·장치 확인
1. Vector Driver Setup (CANoe 19 설치 시 포함) 확인 → **Vector Hardware Config** 에서 VN1630A 가 보이는지.
2. 사용할 채널 하나를 **CANoe 의 CAN 1** 에 할당 (어느 채널인지 적어 둘 것 — 그 채널에 배선).
3. (선택) Python 으로 보이는지:
   ```
   pip install python-can cantools numpy
   python -c "import can; print(can.detect_available_configs('vector'))"
   ```

## 3. CANoe 설정 (메뉴 이름은 버전에 따라 다를 수 있음)
1. 새 설정 또는 기존 `Test1.cfg` 열기.
2. CAN 채널을 **클래식 CAN, 500 kbps** 로 (CAN FD 끄기).
3. 데이터베이스에 **`oakd_canoe.dbc`** 추가 (`oakd_canoe_fd.dbc` 아님. 기존 AURIX 계열 DBC 는 불필요).
4. Trace 창 열기 → 메시지 이름(FRAME_STATUS 0x300 · DET_BOX 0x310 · PERF 0x320)과 값이 보이는지 확인.
5. Logging 블록 → 형식 `.asc` (또는 `.blf`), 저장 경로 기억.
6. **측정 시작(Start) 을 먼저** 누른다. 그다음 Ubuntu 쪽에서 송신을 시작한다.

## 4. 시험 (Ubuntu 쪽은 Ubuntu 의 Claude/사용자가 진행)
Ubuntu 카메라 PC: `cd camera_ai/can_canoe && ~/venvs/camera_ai/bin/python can_demo.py --fake --interface kvaser --channel 0 --duration 20 --out-dir /tmp/t`
→ 이 노트북 Trace 에 메시지가 이름·값으로 보이면 성공. 안 보이면 아래 체크.

| 증상 | 확인 |
|---|---|
| Trace 에 아무것도 없음 | 측정 시작했는지, 채널 할당(Hardware Config ↔ CANoe CAN 1), 500 kbps, 배선 H/L, 종단 120 Ω |
| Ubuntu 에서 `can_tx_errors` 증가 | 버스에 ACK 해줄 수신 노드가 없음 (CANoe 측정 시작 전, 속도 불일치, 배선) |
| 메시지는 오는데 이름이 안 나옴 | DBC 가 채널에 연결됐는지, 클래식 DBC 인지 |

## 5. 본 측정 후 분석
CANoe 측정 중지 → `.asc` 를 Ubuntu PC 로 옮기거나 이 노트북에서:
```
python analyze.py --log canoe.asc --runs-root <Ubuntu 의 runs/날짜_시각 를 가져온 폴더>
```
**미확인:** 실제 CANoe 가 만든 `.asc` 를 `analyze.py` 가 읽는지. 안 읽히면 `analyze.py` 의 `read_log` 를 실제 로그 형식에 맞춰 고칠 것.

## 5-1. CANoe 없이 측정할 때: `canoe_logger.py` (2026-10-06, 이 노트북에서 사용)
```
pip install python-can cantools numpy
cd can_canoe
python canoe_logger.py --idle-exit 120        # 먼저 켜 둔다. 프레임이 120초 끊기면 끝나고 표를 만든다
```
| 결과 (**바탕화면** `can_logs\<날짜_시각>\`, `--out-dir` 로 바꿀 수 있음) | 내용 |
|---|---|
| `canoe.asc` | 받은 프레임 원본 (시간축 = VN1630A 가 받은 시각, 첫 프레임 0) |
| `FRAME_STATUS.csv` · `DET_BOX.csv` · `PERF.csv` | 메시지별 값 + 실행 번호 + `t_axis_ms`(정수) |
| `runs_summary.csv` / `.md` | 실행(모델 × Raw)별: 수신 프레임·결번(`seq_missing`)·FPS·간격 표준편차·엣지 지연·PC/박스 시간·이더넷·CAN 부하·박스 수 수신/기대·검출 비율·평균 신뢰도 |
| `meta.json` | 로거·python-can 버전·채널·비트레이트, **타임스탬프 출처**(VN1630A 하드웨어 수신 시각, 절대 시각 기준점만 PC 시계), 첫 프레임 절대 시각(ISO ms)·`rx_duration_s`·로거 시작→첫 프레임 초, 항목 정의(`definitions`) |

요약표(`runs_summary`)의 통계 규칙 (2026-10-06 Ubuntu 피드백 반영): `edge_ms` 는 `EdgeMs=0`(값 없음) 제외, `pc_ms`·`post_ms`·`eth_KBps` 는 첫 PERF(워밍업) 제외, `interval_ms_*_skip2` 는 첫 2프레임 이후, `fps_10s` 는 꽉 찬 10초 구간별, 클래스는 이름(`class_counts`), ID 별 개수 `n_0x300/310/320`, `gap_before_s`·`t_start_wall_iso` 로 실행 간 시간 잇기. 드리프트(ppm)는 **5분(300초) 이상** 실행이 필요하고 30초 시험은 연결 확인용.

- 수동 종료: 창에서 Ctrl+C, 또는 `<로그 폴더>\STOP` 파일 만들기. 표만 다시: `python canoe_logger.py --summarize <로그 폴더>`
- 노트북 단독으로 나오는 것: 수신·결번·속도·박스 수. **카메라·PC 시계 드리프트(ppm), 송신 수 대비 손실**은 Ubuntu 의 `runs/` (frames.csv) 와 합쳐야 한다 → `python analyze.py --log <로그 폴더>\canoe.asc --runs-root <runs/날짜_시각>`
- 시험: 가상 버스 3실행 + 일부러 뺀 프레임 2개 → 실행 3개로 분리·결번 2 검출. 실제 6회 측정은 아직.

## 6. CANoe 가 막힐 때 대안 (미검증)
```
python canoe_sim.py --interface vector --channel 0 --out canoe.asc
```
(`--app-name` 은 Vector Hardware Config 에 등록한 응용 이름. 채널 번호는 응용 채널 할당을 따름)

## Windows 의 Claude 에게 줄 첫 말 (복사해서 사용)
> camera_ai 저장소의 CLAUDE.md 와 can_canoe/WINDOWS_SETUP.md 를 읽고, 이 노트북의 CANoe/VN1630A 설정을 이어서 도와줘.
> 클래식 CAN 500 kbps, oakd_canoe.dbc 기준. 먼저 python-can 이 VN1630A 를 인식하는지 확인해줘.
