# camera_ai — 작업 메모리 (다른 컴퓨터에서 이어서 작업하기 위한 파일)

Claude Code는 이 파일을 자동으로 읽는다. 사람도 이 파일 하나로 맥락을 잡을 수 있게 쓴다.
마지막 갱신: 2026-10-01.

## 1. 프로젝트가 무엇인가

OAK-D(Myriad X / RVC2) **공식 예제 모델(YOLOv6n)을 7단계로 나눠 분석**한다.

```
① .pt → ② ONNX → ③ OpenVINO IR → ④ .blob → ⑤ NNArchive → ⑥ OAK-D 칩 → ⑦ 호스트 검출 박스
```

최종 목표 (⑦):
1. 엣지 YOLO가 실제로 **어떤 데이터를 토출**하는지 확인
2. 그 데이터를 **시간축으로 최대 5분** 기록하고 **처리한 이미지로 확인**
3. 토출 데이터를 **CAN으로 받을 수 있는지** 확인
4. **파라미터 50개 이상** 추출 (현재 89개 정의)

**하지 않는 것 (2026-09-23 사용자 결정):** MATLAB, 신호등 모델, 다른 YOLO 비교. 관련 파일은 삭제했고
커밋 `72a1a01`(스냅샷)에 남아 있다. 차량 프로젝트 EV_racing과는 **별개**다.

## 2. 폴더 구조와 상태

최상단은 `example/`(공식 예제 분석) · `traffic_light/`(신호등 모델 직접 변환) · `tools/` 세 갈래 (2026-09-28 재편).
각 폴더 안에서 실행한다. 아래 표의 경로는 `example/` 기준.

| 단계 | 폴더 | 파일 | 상태 |
|---|---|---|---|
| ① .pt | `01_pytorch_pt/` | README만 | 원본 가중치 없음. 이름만 확인. 출처("R2") 미확인 |
| ② ONNX | `02_onnx/` | README만 | 파일 없음. buildinfo에서 이름·입출력 확인 |
| ③ IR | `03_openvino_ir/` | README만 | 파일 없음. 변환 명령 확인 |
| ④ .blob | `04_blob/` | README만 | 실물은 ⑤ `example/`의 superblob. 헤더 구조 해석 완료 |
| ⑤ NNArchive | `05_nnarchive/` | `fetch_example.py`, `example/` | 두 예제 추출·해석 완료 |
| ⑥ 칩 | `06_oakd_chip/` | 예제 원본, `run_example.py`, `decompose.py`, `benchmark/`, `step01_record/` | 실행·측정 완료 |
| ⑦ 호스트 | `07_host_output/` | `params.py`, `edge_logger.py`, `review.py`, `can_bridge.py`, `oakd_edge.dbc`, `common.py`, `selftest.sh` | 실카메라 20초 검증 완료. 5분 본 기록·실제 CAN 미완 |
| 최소 실행 | `minimal_example/` | `run_yolov6n.py`, `data_logger.py`, `image_saver.py` (+ `_no_comments`) | 5분 실측 완료 (21.4 FPS, 이미지 1500장) |
| — | `../tools/` | `oakd_preview.py` | 카메라 연결 확인용 (AI 없음) |
| — | `../tools/` | `latency_test.py` (+ `_no_comments`), `latency_runs/` | 지연 분해 측정 (엣지/PC/총). 3모델 10초 측정 완료 (2026-09-29) |
| — | `../tools/` | `latency_latest.py` (+ `_no_comments`), `run_latest_3models.sh` | 카메라 5 fps · AI 입력 큐 크기 1 비차단 · 화면 창 끔 · 5분. **준비만 됨, 미측정** (2026-10-01) |
| — | `../results/` | `README.md` + 모델별 CSV·JSON | 지금까지 실측 기록 모음 (이미지·영상은 git 제외, T7·카메라 PC 에 있음) |

①~④가 비어 있는 이유: Luxonis는 최종 NNArchive만 배포한다. 중간 파일은 `buildinfo.json`의 기록으로만 분석한다.

**`traffic_light/`** — `~/camera`(RealSense 신호등 프로젝트)의 `traffic_light.pt`(YOLO11s, red/yellow/green/off)를
YOLOv8n 예제(T7 외장하드 `camera_ai/*/yolov8n/`, 실카메라 검증 19 FPS)와 같은 절차로 ①~⑦ 구성. 상세: `traffic_light/README.md`.
①~⑤ 실행·검증 완료(카메라 없이). ⑦ 실카메라 5분 실측 완료(2026-09-29, **9.75 FPS**, 지연 중앙 821 ms). 실제 신호등 인식률 미확인.

**2026-10-01 추가:** ②~⑤ 스크립트가 `[크기 [이름]]` 인자를 받는다 (없으면 `512x288 traffic_light`).
`416x416` 으로 11s 변환 완료 (원본 .pt 와 출력 일치 확인, NNArchive 는 T7 에만 — 공개 허락은 512x288 만).
`00_train/train_yolo.py` = 학습 스크립트 (`~/camera/train_yolo.py` 를 옮겨 모델·크기·이름 인자화, 데이터셋 자동 다운로드).

**T7 에만 있는 것:** YOLOv8n ①~⑤ 파이프라인 (`T7/camera_ai/0?_*/yolov8n/`, git 미추적). `latency_latest.py --model yolov8n` 은 T7 에서 실행해야 한다.

## 3. 다음 할 일 (우선순위)

**A. 신호등 YOLO11n 재학습 (RTX 4080 PC, 2026-10-01 결정)** — 11s(21.4 GFLOPs, 칩 9.75 FPS)가 과도해서 n(6.5 GFLOPs)으로 비교.
   공개된 YOLO11n 신호등 모델은 없음 (HuggingFace 검색: 빈 저장소·보행자용 v8n 뿐) → 같은 데이터로 재학습.
```bash
cd traffic_light
pip install huggingface_hub                                  # 데이터셋 다운로드용 (최초 1회)
python3 00_train/train_yolo.py                               # = train yolo11n.pt 960 traffic_light_11n (11s 와 같은 조건)
python3 00_train/train_yolo.py val yolo11n.pt 960 traffic_light   # 기존 11s 같은 방식 평가 (01_pytorch_pt/traffic_light.pt 필요)
python3 02_onnx/export_onnx.py 416x416 traffic_light_11n     # ③ convert_ir · ④ compile_blob · ⑤ make_nnarchive 도 같은 인자
```
   - 학습 끝나면 `01_pytorch_pt/traffic_light_11n.pt` 로 복사됨 (git 제외). 960·416 두 크기로 평가 출력.
   - 비교할 것: 11s vs 11n mAP (특히 red·green), 칩 FPS·지연. **yellow 오검출 의심**: val yellow 20개뿐인데 5분 실측에서 yellow 1377개.
   - 11s 원본(`traffic_light.pt`)은 비공개 → 4080 PC 에 없으면 맥 `~/camera/deploy/` 에서 복사 (`01_pytorch_pt/get_pt.py <경로>`).

**B. 5 fps + 최신화 큐 지연 측정 (카메라 PC, 준비 완료)** — `T7/camera_ai/tools` 에서
   `PYTHON=~/venvs/camera_ai/bin/python bash run_latest_3models.sh` (5분 × 3~4모델 ≈ 16~22분).
   입력: YOLOv6n 512×384 그대로, YOLOv8n·신호등 416×416. 11n NNArchive 가 있으면 자동으로 함께 잰다.
   예상 총 지연: v6n 70~110 · v8n 80~120 · 신호등 11s 130~200 ms (이전 378 / 426 / 826).

0. **`traffic_light/` 인식 확인** — 5분 실측(FPS·안정성)은 끝남 (6절 표). 남은 순서:
   ② 모니터에 신호등 영상 띄워 칩 검출 확인 → ③ 실제 교차로(거리·가로형 신호등).
   5분 실측에서 849/2916 프레임에 검출이 나옴(yellow 1377·green 332·red 73개) → 장면 기록이 없어 오검출인지 이미지로 확인 필요
   (이미지 1500장은 git 제외, 카메라 PC의 `traffic_light/07_host_output/runs/20260929_160337/`).
   지연 821 ms 는 **칩 안(엣지)에서 생김** (2026-09-29 분해 측정, 6절). 카메라 FPS를 AI 속도(≈10)에 맞춰 줄어드는지 확인.
1. ④ superblob에서 기본 블롭(SHAVE 8) 떼어 `04_blob/`에 저장 — 바로 가능
2. ⑦ 실제 카메라 **5분** 본 기록 → `review.py summary`로 파라미터 50개 이상 확인
3. ⑦ CAN: `vcan0`(sudo 필요) → USB-CAN 어댑터 (이 PC에는 어댑터 없음)
4. ① YOLOv6 "R2" 원본 출처 확인 → ② 로컬 ONNX 변환(luxonis/tools) 후 예제와 비교
5. ③ IR은 OpenVINO 2022.3 필요 → Python 3.10 환경 별도 필요 (3.12용은 MYRIAD 미지원)
6. ⑥ 실행 시 실제 SHAVE 배분 확인

## 4. 환경 설치 (새 컴퓨터)

```bash
git clone https://github.com/bongpodoal/camera_ai.git && cd camera_ai
python3 -m pip install --user -r requirements.txt     # Ubuntu 24+: --break-system-packages 필요할 수 있음
cd example/07_host_output && ./selftest.sh 20         # 카메라 없이 전체 흐름 검증 (통과해야 정상)
cd .. && python3 05_nnarchive/fetch_example.py        # 예제 모델 받기 + superblob 복원 (git에 없음)
```

git에 없는 것: `*.superblob`(용량), `**/runs/`(5분 기록 ≈ 1.2 GB), `traffic_light/` 의 `.onnx`·`.bin`·`.blob`(②~④로 재생성),
`*.pt`(신호등 비공개), 512x288 외 신호등 `.tar.xz`, 학습 데이터셋, `results/` 의 이미지·영상.

## 5. 장치 연결 (가장 많이 막히는 곳)

| 항목 | 값 |
|---|---|
| 장치 | **OAK-D-PRO-POE-FF** (고정초점), DeviceId `19443010C19B387E00`, 부트로더 0.0.28 |
| 연결 | PoE 인젝터 → PC 이더넷 직결. DHCP 없음 → 카메라는 **`169.254.1.222`** (링크로컬) |
| PC 설정 | 이더넷에 `169.254.1.10/16` 수동 지정. 원래 PC에서는 NM 프로필 `oak-poe` (autoconnect 꺼짐) |

새 PC에서 NM 프로필 만들기:
```bash
nmcli connection add type ethernet ifname <이더넷이름> con-name oak-poe \
    ipv4.method manual ipv4.addresses 169.254.1.10/16 ipv6.method disabled connection.autoconnect no
nmcli connection up oak-poe && ping -c 2 169.254.1.222
```

**함정 (실측):**
- **자동 탐색은 불안정하다.** 항상 IP 직접 지정 (`--ip 169.254.1.222`). 예제 원본은 자동 탐색만 쓰므로 `run_example.py`(IP 지정 3줄만 다름)로 실행.
- 장치가 파이프라인 시작/종료 때 **재부팅하며 링크가 몇 초 끊긴다.** 연속 실행 사이 15~20초 대기.
- 원래 PC에서는 그 순간 **다른 자동 연결 프로필(`LIDAR`, 192.168.1.102/24)이 이더넷을 가로챘다.** 증상: `No available devices` / `X_LINK_DEVICE_NOT_FOUND`, ping 실패. `nmcli -t connection show --active`로 확인 → `nmcli connection up oak-poe`. 그 프로필은 EV_racing 라이다용이라 건드리지 않음.
- `passthrough` 큐를 만들지 않으면 장치가 연결을 끊는다. 항상 만들고 읽는다.
- 종료 시 크래시 덤프가 자주 남는다(`~/.cache/depthai/crashdumps/`). 종료 전 큐를 비운다. 연속 실행 때 다음 실행이 `Device already closed` 로 실패하면 30초 더 기다린다.
- **두 번째 PC (2026-09-29, 이더넷 `enp5s0`):** 자동 연결 프로필 `Wired connection 4` 가 링크 끊김 때 가로챈다. 연속 측정 동안만
  `nmcli connection modify oak-poe connection.autoconnect yes connection.autoconnect-priority 100` → 끝나면 `no` / `0` 으로 되돌린다.
  시스템 depthai 는 2.30(다른 프로젝트용) → 이 저장소는 venv `~/venvs/camera_ai` (depthai 3.10, Python 3.10) 로 실행.
- **칩 Script 노드 함정:** Script 안에서 `msg.getTimestamp()` 를 부르면 펌웨어 크래시. 칩 시계끼리(`Clock.now()`, `getTimestampDevice()`) 뺀다.
  `Buffer.setData()` 는 list 가 아니라 bytes 를 받는다 (list 면 TypeError 로 Script 가 멈춤).

## 6. 핵심 사실 (실측)

**예제 모델 두 개:**

| 항목 | `yolov6-nano` (예제 기본값) | `luxonis/yolov6-nano:r2-coco-512x288` |
|---|---|---|
| 실제 입력 | **512×384** (파일명은 512x288 — 틀림) | 512×288 |
| 변환 일자 / 도구 | 2025-10-01 / modelconverter 0.4.4 | 2024-07-24 / 0.1.2 |
| ③ 옵션 | ÷255·BGR→RGB를 모델 안에, `--compress_to_fp16` | ÷255·BGR→RGB를 모델 안에 |
| config 전처리 scale | 1.0 (블롭이 처리) | 1.0 |
| 칩 처리 용량 | 22.56 FPS | 38.30 FPS (칩 위 디코딩) |
| 예제 전체 / 카메라 경로 | 21.32~21.44 FPS | 30.01 FPS (카메라 상한), 지연 51 ms |

**superblob 구조:** 앞 136 B = 빅엔디언 u64 × 17 = [기본 블롭 크기, SHAVE 1..16 패치 크기]. 기본 블롭은 SHAVE 8로 컴파일(패치 0).

**⑦ 실카메라 20초:**

| 설정 | FPS | 누락 | 지연 중앙 | 파라미터 |
|---|---|---|---|---|
| 거리 계산 켬 · 30fps | 22.4 | 25% | 358 ms | 89/89 |
| 거리 계산 끔 · 30fps | 30.2 | 0 | 57 ms | 77/89 |
| 거리 계산 켬 · 20fps (**기본값**) | 20.3 | 0 | 90 ms | 89/89 |

**5분 실측 비교 (실카메라, 이미지 1초 5장 저장):**

| 모델 | 칩 FPS | PC 수신 지연 중앙 | 칩 온도 시작→끝 | 기록 |
|---|---|---|---|---|
| YOLOv6n 예제 (`minimal_example`) | 21.41 | 372 ms | 40.6 → 52.3°C | `example/minimal_example/runs/20260928_153518` |
| YOLOv8n 예제 (T7 외장하드) | 19 | — | — | — |
| 신호등 YOLO11s (`traffic_light`) | **9.75** (1초 구간 9.65~9.81) | 821 ms | 42.1 → 53.4°C | `traffic_light/07_host_output/runs/20260929_160337` |

**지연 원인 (2026-10-01 정리):** 세 모델 모두 엣지 지연 ≈ 추론 간격 × 8 (7.7 / 7.8 / 7.9장) → 크기 고정 큐가 가득 찬 상태로 추정.
같은 모델에서 AI > 카메라 FPS 면 57 ms, AI < 카메라면 358 ms. 문서: 8절 "OAK-D 지연 원인 정리".

**맥북 M5 학습 속도 (2026-10-01 실측, PyTorch MPS):** YOLO11n 960 batch 8 = 16.5장/s (11s 7.4장/s) → 60 epoch ≈ 4~5.5시간.
640 ≈ 2시간, 416 ≈ 1시간. 실제 학습은 순수 GPU 의 약 1.3배. → 학습은 CUDA PC 에서.

**지연 분해 (2026-09-29, 두 번째 PC, 10초씩, 중앙값):** `tools/latency_test.py` → `tools/latency_runs/20260929/`

| 모델 | FPS | 엣지 지연 | PC 지연 | 총 지연 | 엣지 비중 |
|---|---|---|---|---|---|
| YOLOv6n | 20.85 | 371 ms | 6.9 ms | 378 ms | 98% |
| YOLOv8n | 18.61 | 419 ms | 5.8 ms | 426 ms | 98% |
| 신호등 YOLO11s | 9.66 | 819 ms | 6.6 ms | 826 ms | 99% |

- 엣지 = 칩에서 AI 결과가 나온 시각 − 촬영 시각 (칩 Script 노드가 칩 시계로 잼). PC = 총 − 엣지 (이더넷 + PC 큐).
- 총 지연은 원래 PC 5분 기록과 같다 (372→378, 821→826 ms) → **PC를 바꿔도 지연은 그대로, 거의 전부 칩 안.**
- 추정 원인 (미확인): 카메라 30 FPS > AI 처리 속도 → 프레임이 칩 안 AI 입력에서 대기. 순번이 3씩 건너뛰는데 지연은 추론 1회(≈100 ms)의 약 8배.

- **OAK-D PoE에는 CAN 포트가 없다.** 호스트가 USB-CAN으로 중계 (`can_bridge.py`, `oakd_edge.dbc`).
- `roi_*`는 깊이 프레임 **픽셀** 값. `lens_pos`는 고정초점이라 -1.
- 전처리(÷255)는 블롭 또는 config 중 **한 곳에서만**. 둘 다 하면 검출 0개인데 FPS는 정상으로 나온다.
- 이 PC의 시스템 matplotlib은 numpy 2와 충돌 → 그래프는 OpenCV로 그린다.

## 7. 작업 방식 (사용자 선호)

- **과정이 중요하다.** 단계마다 기록(`NOTES.md`, `PROGRESS.md`)을 남긴다. 결과만 남기지 말 것.
- 문서는 **표 위주, 설명 문장 최소.** 약어는 처음에 풀어 쓴다. 군더더기 삭제를 여러 번 요청받았다.
- 실제 장치 명령 전에 준비·검증부터. 한국어로 답한다.
- 코드·개념 설명은 **초보자 눈높이로 한 줄씩** (비유 + 표 + 전체 흐름 요약). 이 방식에 만족했다.
- 스크립트는 **설명 주석판(`*.py`) + 주석 없는 판(`*_no_comments.py`)** 두 벌을 같은 폴더에 둔다. 결과 파일은 두 판이 같아야 한다.
- 모델 가중치 공개 여부는 사용자가 정한다. 현재 `traffic_light-512x288.tar.xz` 만 공개 커밋 허락, `traffic_light.pt` 는 비공개(이 맥 `~/camera/deploy/`).
- 이 저장소는 **공개**다. 토큰·비밀번호를 커밋하지 말 것.

## 8. 발행 문서 (claude.ai, 비공개 링크)

| 문서 | 링크 |
|---|---|
| ⑤~⑦단계 파일 역할과 기능 (현재 구조 기준) | https://claude.ai/code/artifact/b3c03f75-7695-4779-8a0a-56ac1599d71c |
| 엣지에 모델 올리기 과정과 원리 (6절은 삭제된 `edge_deploy.py` 기준이라 낡음) | https://claude.ai/code/artifact/df7e517a-23fa-474a-98a4-8df27fb247f7 |
| Step 01 · 공식 예제 실험 기록 | https://claude.ai/code/artifact/423ed4dd-372a-4117-a5c5-747c2f02693d |
| Step 02 · 신호등 모델 (현재 범위 밖) | https://claude.ai/code/artifact/fd012efe-cae1-4e01-92a8-c12cb81b2498 |
| OAK-D 지연 원인 정리 (2026-10-01, Claude Docs) | https://claude.ai/code/artifact/068590d1-a285-4464-a2d8-89fc1c53dcfd |

## 9. 자주 쓰는 명령

```bash
cd example
python3 05_nnarchive/fetch_example.py
python3 06_oakd_chip/run_example.py 169.254.1.222                       # q로 종료
python3 06_oakd_chip/benchmark/edge_benchmark.py --model yolov6-nano --ip 169.254.1.222 \
    --label x --mode throughput --duration 10 --warmup 3
cd 07_host_output
python3 edge_logger.py --ip 169.254.1.222 --duration 300                # 5분
python3 review.py summary|frame|sheet|timeline runs/<폴더> [...]
python3 can_bridge.py dbc|selftest|replay|listen [...]

cd traffic_light                                                         # 신호등 모델
python3 01_pytorch_pt/get_pt.py && python3 02_onnx/export_onnx.py       # ①② (로컬)
python3 03_openvino_ir/convert_ir.py && python3 04_blob/compile_blob.py # ③④ (인터넷)
python3 05_nnarchive/make_nnarchive.py                                  # ⑤
python3 07_host_output/run_with_logging.py --duration 60                # ⑥+기록 (카메라)
python3 00_train/train_yolo.py [train|val|resume] [기본모델] [크기] [이름]  # ⓪ 학습 (CUDA GPU)
python3 02_onnx/export_onnx.py 416x416 traffic_light_11n                # ②~⑤ 는 [크기 [이름]] 인자

cd tools                                                                 # 지연 측정
python3 latency_latest.py --model yolov6n|yolov8n|traffic_light|traffic_light_11n --out-dir latency_runs/x
bash run_latest_3models.sh [fps=5] [초=300]
```
