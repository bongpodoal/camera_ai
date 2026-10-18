# a_yolom — A-YOLOM(n) (검출 + 차선 + 주행영역) 를 can_demo.py 에 연결

`can_demo.py --model a_yolom_n` (ModelId 5). 4080 PC 가 학습·변환한 6 SHAVE 블롭을 NNArchive 로 받아 쓴다.

| 파일 | 역할 |
|---|---|
| `a_yolom_source.py` | 카메라 → NeuralNetwork(원시 출력) → 호스트 디코딩. 실제(`AYolomSource`)·가짜(`AYolomFake`)·공통 후처리(`Processor`) |
| `postprocess.py` · `postprocess_variants.py` | 4080 PC 제공(next-task) 후처리. **출력 이름·모양 가정은 여기 한 곳**: `det_p3/p4/p5 (1,69,H/s,W/s)` + `drivable`·`lane`. 변형(v1~v3)은 `postprocess_variants.postprocess(variant, …)` 가 처리 |
| `raw_ai.py` | `--raw on` 전용 AI 결과 기록 (NMS 전 후보·분할 점수·원시 텐서) |
| `a_yolom_debug_view.py` | 측정 전 확인용 디버그 창 (영상 + 박스 + 차선·주행영역 오버레이, Q/ESC 종료) |
| `<저장소 루트>/a_yolom/05_nnarchive/*.tar.xz` | 모델 파일 (이 폴더가 아니라 저장소 루트의 `a_yolom/` 에 둔다, git 제외 = `.gitignore`) |

## 실행
```bash
# 측정 전 확인(카메라 점유 → 측정 전에 닫을 것)
./can_canoe/a_yolom/a_yolom_debug_view.py [--fps 4] [--depth] [--no-seg]
# 짧은 시험(가상 CAN)
python3 can_canoe/can_demo.py --model a_yolom_n --raw off --interface virtual --channel t --duration 20 --mode vehicle --nic enp6s0 --out-dir /tmp/x
# 측정 (run_matrix.sh)
MODELS=a_yolom_n RAWS="off on" FPS=4 NIC=enp6s0 INTERFACE=kvaser CHANNEL=0 ./can_canoe/run_matrix.sh
```
변형 모델: `--archive <경로>.tar.xz` 또는 `.blob`(최소 NNArchive 로 감쌈). 변형 이름은 파일명(`_v1_`, `_v2b_` …)에서 읽고 `--variant` 로 지정할 수도 있다.
옵션: `--conf`(기본 0.25) · `--seg-min-pixels`(기본 50) · `--raw-log on|off`(Raw 켬의 AI 결과 기록, 기본 on) · `--raw-tensors-every S`(원시 텐서 .npz 저장 간격, 기본 0 = 안 함).

## CAN 으로 나가는 것
FRAME_STATUS(ModelId 5)·DET_BOX(Label 0 person 1 car 2 tl_red 3 tl_green 4 tl_yellow)·PERF + **SEG_SUMMARY(0x380)**: Seq · LanePresent · DaPresent · LaneConf · LaneAreaPct · DaConf · DaAreaPct.
- present = 신경망 입력 크기(512×288) 마스크의 양성 픽셀 ≥ 50 (평가에서 1280×720 정답 마스크로 N=50 을 쓴 것과 기준 해상도가 다름 → 같은 장면이면 이쪽이 더 엄격). conf = (패딩 제외 영역) sigmoid(logit1−logit0) 최댓값 %, area = 양성 픽셀/전체 %. 마스크 자체는 CAN 에 싣지 않는다.
- Raw 켬일 때만 깊이(X/Y/Z·ROI)·프레임 메타·칩 상태 등 기존 추가 메시지도 나간다. X/Y/Z 는 **호스트가** 깊이 프레임에서 계산한다(검출 박스 가운데 50% 영역의 유효 깊이 중앙값, 100 mm~20 m). 깊이는 카메라의 별도 출력(신경망 입력과 같은 크기)에 정렬한다 — 신경망 `passthrough` 에 정렬하면 칩 지연이 0.5 → 1.7 s 로 쌓여 쓰면 안 된다(2026-10-13 실측).

## Raw 켬 AI 결과 기록 (실행 폴더 안)
- `raw_ai_candidates.csv`: 프레임마다 det_p3/p4/p5 모든 앵커 후보 중 최대 클래스 점수 ≥ 0.01, 프레임당 상위 200개. 열: frame_seq, ts_device_ms, scale(p3/p4/p5), gx, gy, 박스 x1,y1,x2,y2(모델 입력 기준 0~1, 자르지 않음), 클래스 5개 점수(sigmoid, 임계값 전), max_cls, max_score, kept_after_nms, sent_to_can.
- `raw_ai_seg.csv`: 프레임·작업(lane/drivable)마다 max_score_pct, max_logit_diff, pos_pixels, area_pct, present, sent_to_can.
- `raw_tensors/*.npz`: `--raw-tensors-every S` 일 때만. 프레임당 약 3 MB(float32, 압축)이라 1초 1프레임이면 5분에 약 1 GB. 변형(분할 출력 축소)은 작다.
- Raw 끔에서는 기록하지 않는다. 기록 때문에 호스트 후처리 시간이 늘어난다(가짜 입력 비교: 후처리 1.5 → 3.7 ms/프레임, 실카메라 값은 측정 때 `--raw-log off` 와 비교).

## 알아둘 것 (2026-10-13 실측)
- 칩 지연(`edge_ms`)은 원본 ft1 이 약 270~283 ms (목표 ≤100 ms 초과). 검출만 남긴 변형 v1 은 약 73 ms (`model_candidates/chip_bench.py`).
- 깊이 켬은 5 fps 를 못 지킨다(처리량 약 4 fps, 5 fps 요청 시 약 25% 프레임 누락·지연 증가). 4 fps 로 같이 맞추면 안정(약 3.96 fps, 누락 1).
- Raw 끔이어도 신경망 원시 출력(프레임당 약 3 MB)은 이더넷으로 호스트에 온다. 이더넷 통신량 비교는 `--nic` 로 잴 것.
