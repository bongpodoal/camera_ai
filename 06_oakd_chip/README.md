# ⑥ OAK-D 칩 — 추론 · 디코딩 · NMS

예제 코드(`detection_network_original.py`)가 ⑤ NNArchive를 장치로 보내면, 칩이 카메라 영상을
입력 크기로 줄이고 → 신경망 추론 → YOLO 출력 해석 → 겹친 박스 제거(NMS)까지 끝낸다.
호스트로는 박스(`out`)와 그 프레임(`passthrough`)만 온다.

| 파일 | 역할 |
|---|---|
| `detection_network_original.py` | depthai v3.10.0 공식 예제 원본 (수정 없음). 분석 대상 |
| `run_example.py` | 원본 실행용 사본. **차이는 IP로 장치를 지정하는 3줄뿐** (자동 탐색이 불안정해서) |
| `decompose.py` | 예제 FPS를 분해: 전체 / 화면 표시 제외 / 영상 전송 제외 |
| `benchmark/edge_benchmark.py` | 칩 처리 용량(`throughput`)과 카메라 실경로(`camera`) FPS·지연 측정 |
| `benchmark/aggregate.py` | 반복 측정 평균·편차 표 |
| `benchmark/summarize.py` | 측정별 표 |
| `benchmark/results/*.json` | YOLOv6n 측정 원본 13건 |
| `step01_record/` | Step 01 기록 (NOTES.md, 실행 로그 5개, 검출 화면, PDF) |

```bash
nmcli connection up oak-poe                       # 재부팅 후 1회
python3 06_oakd_chip/run_example.py 169.254.1.222     # 예제 실행 (q로 종료) — 2026-09-23 실측 21.32 FPS
python3 06_oakd_chip/decompose.py --mode full      # full | nodisplay | detonly
python3 06_oakd_chip/benchmark/edge_benchmark.py --model yolov6-nano --ip 169.254.1.222 \
    --label yolov6n-default --mode throughput --duration 10 --warmup 3
python3 06_oakd_chip/benchmark/aggregate.py
```

## 측정 결과 (YOLOv6n, 10초 · 워밍업 제외)

| 모델 | 입력 | 경로 | FPS | 지연 |
|---|---|---|---|---|
| yolov6-nano (기본값) | 512×384 | 칩 처리 용량 | 22.56 | — |
| yolov6-nano (기본값) | 512×384 | 예제 전체 | 21.44 | — |
| r2-coco-512x288 | 512×288 | 칩 처리 용량 (칩 위 디코딩) | 38.30 ±0.04 | — |
| r2-coco-512x288 | 512×288 | 칩 처리 용량 (호스트 디코딩) | 40.21 ±0.02 | — |
| r2-coco-512x288 | 512×288 | 카메라 실경로 | 30.01 (카메라 30fps 상한) | 51.0 ms |

## 장치 주의사항 (실측)

| 현상 | 대응 |
|---|---|
| `passthrough` 큐를 만들지 않으면 장치가 연결을 끊음 | 항상 만들고 계속 읽는다 |
| 종료 시 크래시 덤프가 자주 남음 | 종료 전 큐를 비운다. 연속 실행 사이 15~20초 대기 |
| 자동 탐색이 부팅 중 실패 | `--ip 169.254.1.222` 직접 지정 |
| 장치 재부팅 때 링크가 끊기면 NM 프로필 `LIDAR`가 `enp7s0`을 가져감 (2026-09-23 두 번 재현) | 실행 전 `nmcli -t connection show --active` 확인 → `nmcli connection up oak-poe` |
| 카메라 FPS > 칩 처리 용량이면 지연 폭증 | 카메라 FPS를 처리 용량 이하로 |
| `throughput` 모드의 지연값은 무의미 (같은 프레임 복제) | 지연은 `camera` 모드로만 |

| 분석할 것 | 상태 |
|---|---|
| 칩 위 디코딩 비용 (38.30 vs 40.21 FPS, 약 5%) | 측정됨, 원인 분석 미완 |
| 실행 시 SHAVE·스레드 배분 (④ superblob 선택) | 미확인 |
