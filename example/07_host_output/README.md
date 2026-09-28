# ⑦ 호스트 검출 박스 — 받고, 기록하고, 확인하고, 전달한다

⑥이 보낸 결과를 호스트가 받아 시간축으로 기록(최대 5분)하고, 처리한 이미지로 확인하고, CAN으로 내보낸다.
기본 모델은 예제 `luxonis/yolov6-nano:r2-coco-512x288`. 상세 기록은 `NOTES.md`.

| 파일 | 역할 |
|---|---|
| `params.py` | 받을 파라미터 89개 정의 (세션 18 · 프레임 31 · 검출 27 · 장치 상태 17) |
| `edge_logger.py` | 카메라(또는 가짜 데이터) → `runs/<시각>/` 에 CSV 3개 + 세션 + 처리 이미지 + 영상 |
| `review.py` | `summary` · `frame` · `sheet` · `timeline` |
| `can_bridge.py` | CAN 변환·송출·수신. `dbc` · `selftest` · `replay` · `listen` |
| `oakd_edge.dbc` | CAN 메시지 4종 정의 (0x300 프레임, 0x310 박스, 0x320 거리, 0x330 장치 상태) |
| `common.py` | 박스 그리기, CSV 읽기 |
| `selftest.sh` | 카메라 없이 기록 → 검토 → CAN 왕복 검증 |
| `NOTES.md` | Step 03 기록 |

```bash
cd 07_host_output
./selftest.sh 300                                             # 카메라 없이 검증
python3 edge_logger.py --ip 169.254.1.222 --duration 20 --display   # 짧게 확인
python3 edge_logger.py --ip 169.254.1.222 --duration 300            # 5분 (기본: 거리 계산 켬 + 20fps)
python3 review.py summary runs/<폴더>
python3 can_bridge.py selftest --run runs/<폴더>
```

**OAK-D PoE에는 CAN 포트가 없다.** CAN은 호스트가 USB-CAN 어댑터로 중계한다.
