# can_aurix — OAK-D 결과를 CAN 으로 AURIX 에 보내고, 시간축을 AURIX 시계로 통일

과제: 카메라 출력(CAN 수신) · 원본 화면 기준 인식 수준(후처리) · Raw 수신 여부별 연산/통신 속도 비교 · 3모델.
지난 과제 지적: 카메라(엣지) 시계를 시간축으로 쓰면 시간이 갈수록 오차가 커진다 → **AURIX 타이머 하나로 통일**.

```
OAK-D --이더넷--> PC(can_demo.py) --CAN(USB 어댑터)--> AURIX TC275 (받는 순간 STM 읽음)
                        ^---------- ECHO(Seq, AURIX 수신 시각 µs) ----------+
                        <---------- SYNC(1초마다 AURIX 시각) ---------------+
```

| 파일 | 역할 |
|---|---|
| `oakd_aurix.dbc` | 메시지 정의 SYNC 0x100 · ECHO 0x101 · FRAME_STATUS 0x300 · DET_BOX 0x310 (클래식 CAN 8바이트) |
| `aurix_can.py` | 인코딩/디코딩 공통 코드, 32비트 µs 이어 붙이기 |
| `can_demo.py` (+`_no_comments`) | 카메라 → CAN 송신, 시간축 기록, 드리프트·속도 요약. `--raw on/off`, `--model`, `--fake` |
| `aurix_sim.py` | AURIX 흉내 (보드 없이 검증, 또는 vcan0 으로 PC 쪽만 시험) |
| `selftest.py` | 카메라·보드 없이 전체 흐름 검증 (가상 CAN) |
| `aurix_tc275/` | AURIX 펌웨어 (iLLD). **맥에서 작성, 아직 컴파일 안 해 봄** |

## 결과 파일 (`--out-dir`)
| 파일 | 내용 |
|---|---|
| `frames.csv` | 프레임마다: `t_axis_ms`(정수, AURIX 기준) · `interval_ms` · `cam_minus_aurix_ms`(카메라 시계가 벌어진 양) · `edge_ms` · `pc_ms` · `post_ms`(박스 그리기) · `echo_rtt_ms` · `raw_bytes` |
| `summary.csv` | 실행마다 한 줄: FPS · 지연 · `eth_MBps` · `can_load_pct` · `camera_drift_ppm` · `pc_drift_ppm` |
| `images/` | `--raw on` 일 때 박스 그린 원본 화면 (1초에 1장) |

## 실행
```bash
python3 selftest.py                                   # 맥에서 (pip install python-can cantools numpy)
# 카메라 PC: CAN 어댑터를 can0 으로 올린 뒤 (PCAN 등은 socketcan)
sudo ip link set can0 up type can bitrate 500000
python3 can_demo.py --model yolov6n --raw off --channel can0 --nic <이더넷이름> --out-dir runs/v6n_off
python3 can_demo.py --model yolov6n --raw on  --channel can0 --nic <이더넷이름> --out-dir runs/v6n_on
```

## 아직 검증 안 된 것
| 항목 | 이유 |
|---|---|
| `OakSource` (실제 카메라 경로) | 카메라 없는 맥에서 작성. `--raw off` 의 칩 위 버림 Script, passthrough 연결은 카메라 PC 에서 확인 필요 |
| AURIX 펌웨어 | 컴파일·실행 안 해 봄. CAN 핀(P20.7/P20.8), LED 핀, iLLD 이름은 보드 문서·버전과 대조 필요 |
| `eth_MBps` | 리눅스 `/proc/net/dev` (`--nic`). 없으면 원본 영상 바이트만 센 하한값 |
