# Windows 노트북 설정 (Vector VN1630A + python-can 로거) — git pull 후 이 순서대로

역할: 카메라 PC(Ubuntu)가 보낸 CAN 프레임을 **받아서 시각을 기록**한다 (시간축 = 이 노트북의 VN1630A 가 받은 시각).
이 노트북에는 카메라·모델 파일이 필요 없다. 필요한 것: 이 폴더의 `canoe_logger.py`(수신), `oakd_canoe.dbc`(해석), `analyze.py`(분석).

> **2026-10-06 사용자 확정: CANoe 는 쓰지 않는다.** 수신·시간축은 python-can 기반 `canoe_logger.py` 로 한다.
> (이 노트북에 CANoe 설치 파일이 없고 상용 라이선스가 필요함.) 이전의 CANoe 설정 절차는 삭제했다 — 필요하면 저장소 이력(`b715ce8`)에서 볼 수 있다.

## 결정 사항
| 항목 | 값 |
|---|---|
| CAN 종류 | **클래식 CAN 500 kbps** (FD 아님). DBC = `oakd_canoe.dbc` |
| 송신 (Ubuntu 카메라 PC) | Kvaser Leaf v3 → `python-can` `--interface kvaser --channel 0` |
| 수신 (이 노트북) | Vector VN1630A 채널 1 (python-can `--interface vector --channel 0`), **`canoe_logger.py`** |
| 시간축 | VN1630A **하드웨어 수신 시각** (Vector XL 드라이버 이벤트 `timeStamp`). 절대 시각 기준점만 버스를 연 순간의 PC 시계 |
| 배선 | Leaf v3 CAN_H/CAN_L ↔ VN1630A CAN_H/CAN_L, 버스 양 끝 120 Ω 종단 |

## 1. 저장소 받기·준비
```
git clone https://github.com/bongpodoal/camera_ai.git
cd camera_ai\can_canoe
pip install python-can cantools numpy
```
이미 받았으면 `git pull`.

## 2. 드라이버·장치 확인
Vector 드라이버(`vxlapi64.dll`)가 설치되어 있어야 한다. 아래가 VN1630A 를 보여 주면 된다 (채널 1·2, `hw_type` VN1630).
```
python -c "import can; print(can.detect_available_configs('vector'))"
```

## 3. 수신 시작 (Ubuntu 송신보다 먼저)
```
python canoe_logger.py --idle-exit 120        # 프레임이 120초 끊기면 자동 종료하고 표를 만든다
```
- 6회를 이어 받을 때는 `--idle-exit 180` 이상 (실행 사이 카메라 재시작 대기가 있음). 로거를 한 번만 켜 두면 모델·Raw 가 바뀌는 곳에서 실행이 자동으로 나뉜다.
- `--out-dir <폴더>` 로 저장 위치를 바꿀 수 있다 (기본: 바탕화면 `can_logs\<날짜_시각>\`).
- 종료: Ctrl+C, 또는 `<로그 폴더>\STOP` 파일 만들기.

| 결과 (`can_logs\<날짜_시각>\`) | 내용 |
|---|---|
| `canoe.asc` | 받은 프레임 원본 (시간축 = VN1630A 가 받은 시각, 첫 프레임 0) |
| `FRAME_STATUS.csv` · `DET_BOX.csv` · `PERF.csv` | 메시지별 값 + 실행 번호 + `t_axis_ms`(정수) |
| `runs_summary.csv` / `.md` | 실행(모델 × Raw)별 수신 프레임·결번(`seq_missing`)·FPS·간격 표준편차·엣지 지연·PC/박스 시간·이더넷·CAN 부하·박스 수 수신/기대·검출 비율·평균 신뢰도·클래스별 개수 |
| `meta.json` | 로거·python-can 버전·채널·비트레이트, **타임스탬프 출처**, 첫 프레임 절대 시각(ISO ms)·`rx_duration_s`·로거 시작→첫 프레임 초, 항목 정의(`definitions`) |

요약표 통계 규칙: `edge_ms` 는 `EdgeMs=0`(값 없음) 제외, `pc_ms`·`post_ms`·`eth_KBps` 는 첫 PERF(워밍업) 제외, `interval_ms_*_skip2` 는 첫 2프레임 이후, `fps_10s` 는 꽉 찬 10초 구간별, ID 별 개수 `n_0x300/310/320`, `gap_before_s`·`t_start_wall_iso` 로 실행 간 시간 잇기. 드리프트(ppm)는 **5분(300초) 이상** 실행이 필요하고 30초 시험은 연결 확인용.

## 4. 시험 (Ubuntu 쪽은 Ubuntu 의 Claude/사용자가 진행)
Ubuntu 카메라 PC: `cd camera_ai/can_canoe && ~/venvs/camera_ai/bin/python can_demo.py --fake --interface kvaser --channel 0 --duration 20 --out-dir /tmp/t`
→ 로거 출력에 `0x300 … · 0x310 … · 0x320 …` 개수가 올라가면 성공. 안 올라가면 아래 체크.

| 증상 | 확인 |
|---|---|
| 개수가 계속 0 | 로거를 먼저 켰는지, VN1630A 채널 1 에 배선했는지(H/L), 500 kbps, 종단 120 Ω |
| Ubuntu 에서 `can_tx_errors` 증가 | 버스에 ACK 해줄 수신 노드가 없음 (로거를 먼저 켜지 않음, 속도 불일치, 배선) |
| 로거가 바로 종료 | `--idle-exit` 가 너무 짧음 / Vector 드라이버·채널 번호 확인 |
| 한글 깨짐 | 파일은 UTF-8 이다. 콘솔 코드페이지만 다를 수 있음 (파일 내용은 정상) |

## 5. 본 측정 후 분석
로거 종료 → 같은 폴더의 `runs_summary.md` 로 노트북 단독 결과 확인.
**카메라·PC 시계 드리프트(ppm), 송신 수 대비 손실**은 Ubuntu 의 `runs/<run_id>/frames.csv` 와 합쳐야 나온다:
```
python analyze.py --log <로그 폴더>\canoe.asc --runs-root <runs 폴더>
```
(이전 시험은 `results/can_canoe/20261006/` 에 로그·송신 기록이 같이 올라가 있고 Ubuntu 에서 합치기에 성공했다. 드리프트 계산은 시작 후 3초를 제외한다.)

## 6. 두 PC Claude 세션 협업 (선택)
| 항목 | 값 |
|---|---|
| 수신 설정 | 양쪽 `~/.claude/settings.json` 에 `{"crossSessionInbound": "accept"}` (없으면 권한 모드가 다른 세션의 메시지가 보류됨) |
| 절차 | 사용자 요청 → Ubuntu `START <run_id> …` → Windows 로거 켜고 `READY <run_id>` → Ubuntu 카메라 실행 → `RESULT` → Windows `LOGGED` (수치 위주, 로그 줄은 옮기지 않고 파일 경로만) |
| 주의 | 카메라·CAN 송신은 사용자가 지시할 때만 |

## Windows 의 Claude 에게 줄 첫 말 (복사해서 사용)
> camera_ai 저장소의 CLAUDE.md 와 can_canoe/WINDOWS_SETUP.md 를 읽고, 이 노트북의 VN1630A 수신 로거 설정을 이어서 도와줘.
> 클래식 CAN 500 kbps, oakd_canoe.dbc, CANoe 는 쓰지 않고 canoe_logger.py 로 받는다. 먼저 python-can 이 VN1630A 를 인식하는지 확인해줘.
