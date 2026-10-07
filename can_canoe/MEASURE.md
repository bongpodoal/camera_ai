# Raw 켬 측정 바로 하기 (카메라 PC + Windows 노트북)

**Raw 켬 = 카메라로 받을 수 있는 모든 데이터 (깊이 포함).** 칩에서 스테레오 깊이와 깊이 포함 검출망이 돌고, 숫자·문자열은 전부 CAN 으로,
RGB·깊이 프레임은 이더넷으로 받는다 (README 의 Raw 정의 표). 이 문서는 그 측정을 처음부터 끝까지 하는 순서다.
시간: 점검 5분 + 확인 3분 + 본 측정 6회 × 5분 + 대기 ≈ 40분.

## 0. 준비 (양쪽 PC)
| PC | 할 일 |
|---|---|
| 둘 다 | `git pull origin main` (DBC 가 바뀌었다: 추가 메시지 14개) |
| 카메라 PC (Ubuntu) | depthai 가 있는 venv 에서 `pip install python-can cantools numpy opencv-python` → `cd can_canoe && python3 selftest.py` 가 "결과: 통과" |
| Windows 노트북 | `pip install python-can cantools numpy` (그 밖에는 `WINDOWS_SETUP.md` 의 2번까지) |

## 1. 점검 (카메라 PC)
```bash
cd can_canoe
python3 preflight.py --interface kvaser --channel 0 --nic enp6s0      # 이 PC 기준. 다른 PC 면 값 바꾸기
```
FAIL 이 나온 줄의 `→` 안내대로 고친다. 특히 **NNArchive 두 개**(`traffic_light_v8n-416x416.tar.xz`, `traffic_light-416x416.tar.xz`)는 git 에 없고 이 PC 에만 있다.

## 2. Windows 로거 켜기 (Ubuntu 송신보다 먼저, 측정 내내 켜 둠)
```
python canoe_logger.py --idle-exit 180
```
Raw 켬의 추가 메시지(0x330~0x370)는 로거가 그대로 `canoe.asc` 에 저장한다 (기존 표는 변하지 않음).

## 3. 먼저 위험한 것 하나만 60초 (카메라 PC) — 깊이 파이프라인이 열리는지
가장 무거운 신호등 YOLO11s 로 확인한다. 이게 되면 나머지 모델은 더 가볍다.
```bash
MODELS=traffic_light RAWS=on DURATION=60 INTERFACE=kvaser CHANNEL=0 NIC=enp6s0 ./run_matrix.sh
```
출력의 `설정:` 줄과 마지막 summary 줄을 본다.

| 확인 | 정상 | 아니면 |
|---|---|---|
| `설정:` 줄 | `… raw on (깊이·텔레메트리·영상 모두 받음)` | 에러로 끝나면 메시지를 그대로 기록해 알려 줄 것 (깊이 파이프라인 구성 문제) |
| `경고: 이 노드에는 input 큐 설정이 없어…` | 안 나오는 게 좋음. 나오면 최신화 큐가 깊이 모드에서 적용 안 된 것 → 지연이 커질 수 있음 (측정은 계속 가능, 결과에 기록) |
| `fps_avg` | 5.0 근처 (4.9 이상) | 이보다 낮으면 칩이 못 따라감 → 아래 대처 |
| `dropped` | 0 | 늘면 같은 대처 |
| `can_tx_errors` | 0 | CAN 배선·속도·Windows 로거가 켜져 있는지 |
| `eth_MBps` | 0.0 보다 훨씬 큼 (Raw 끔은 약 0.01) | 0 이면 `--nic` 이름 확인 |
| `edge_ms` | Raw 끔(11s 154 ms)과 비교해 크게 안 늘면 정상 | 크게 늘면 깊이 부하 → 결과로 기록 |
| 결과 폴더 | `images/…_depth.png`(깊이), `…jpg`(RGB), `telemetry.csv`, `session.json` 생김 | 없으면 해당 큐가 안 온 것 |

**fps 가 5 에 못 미칠 때 대처 (순서대로)**: ① `FPS=4` 로 낮춰 재측정 (비교표에 "4 fps" 명시) ② 그 모델만 입력을 줄인 변환본 사용 ③ YOLO11n 재학습본으로 교체.
어느 경우든 **Raw 끔과 켬은 같은 FPS 로 비교**해야 하므로, 바꾸면 끔도 다시 잰다.

## 4. 본 측정 (6회: 3모델 × Raw 끔/켬, 각 5분)
```bash
systemd-inhibit --what=sleep:idle --why="CAN 측정" \
  env INTERFACE=kvaser CHANNEL=0 NIC=enp6s0 ./run_matrix.sh
```
- 순서: yolov6n 끔→켬, traffic_light_v8n 끔→켬, traffic_light 끔→켬. 실행 사이 20초 대기 (카메라 재부팅).
- 한 실행이 `Couldn't open stream` 으로 시작 실패하면 30초 기다렸다가 그 모델·Raw 만 다시: `MODELS=<모델> RAWS=<off|on> ./run_matrix.sh`.
- 이미 Raw 끔 5분 결과가 있으면(`results/can_canoe/20261007/`) **Raw 켬 3회만** 새로 재도 된다: `RAWS=on ./run_matrix.sh`. 단 장치·위치·장면·FPS 가 그때와 같아야 비교가 된다 (다르면 6회 전부).
- 측정 중 두 PC 절전 금지 (Windows 로거는 절전 방지를 켬, Ubuntu 는 위 `systemd-inhibit`).

## 5. 끝난 뒤 정리
```bash
# Windows 로그(canoe.asc 또는 can_logs 폴더)를 카메라 PC 로 옮긴 뒤
python3 analyze.py --log <canoe.asc> --runs-root runs/<날짜_시각>          # 실행별 시간축·드리프트·compare.md
python3 extra_messages.py --log <canoe.asc> --out runs/<날짜_시각>/추가메시지   # 깊이 위치·프레임 메타·칩 상태·보정·장치 정보 CSV
python3 slide_perf_csv.py ../results/can_canoe/<날짜>                     # 발표용 PERF (내림, 한글 열)
```
결과는 `results/can_canoe/<날짜>/` 아래 `logs/`(Windows)·`runs/`(Ubuntu)에 정리하고, **커밋·푸시는 사용자가 지시할 때만** 한다.

## 6. 결과에서 볼 것 (Raw 끔 vs 켬, 같은 모델끼리)
| 항목 | 어디서 | 기대 (추정, 미측정) |
|---|---|---|
| 칩 FPS / 누락 | `summary.csv` `fps_avg`·`dropped` | 5.0 유지 / 0 |
| 칩 안 지연 | `edge_ms` | 깊이 때문에 늘 수 있음 |
| PC 쪽 지연 | `pc_ms` | 거의 같음 |
| 이더넷 수신량 | `eth_MBps` (NIC 기준) | 끔 약 0.01 → 켬 수 MB/s (RGB + 깊이 프레임) |
| CAN 부하 | `analyze.py` 의 `can_load_pct` | 끔 약 1% → 켬 약 3~4% |
| 칩 온도·CPU·메모리 | `telemetry.csv` / `DEV_TEMP.csv` | 켬에서만 얻을 수 있음 (끔은 안 받음) |
| 깊이 거리 | `detections.csv` `z_mm` / `DET_POS.csv` | 검출마다 X/Y/Z |

## 알려진 위험 (모두 실카메라 미검증)
- 깊이 파이프라인(`SpatialDetectionNetwork`)이 416×416 NNArchive 와 맞는지, 최신화 큐(`network.input`) 설정이 되는지.
- 5 fps 에서 YOLO11s + 깊이가 칩에 부담이 되는지 (지난 과제는 yolov6n + 깊이가 30 fps 에서 25% 누락, 20 fps 에서 정상).
- Windows 로거는 새 메시지를 CSV 로 풀지 않으므로 반드시 5번의 `extra_messages.py` 를 쓴다.
