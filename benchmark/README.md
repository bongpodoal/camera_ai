# OAK-D 엣지 추론 성능 벤치마크

스톡 YOLO 모델을 OAK-D(RVC2) 엣지에 올린 성능과, MATLAB/Simulink로 최적화한 모델의 성능을
같은 조건에서 재어 비교하기 위한 환경.

## 대상 하드웨어

| 항목 | 값 |
|---|---|
| 장치 | OAK-D PoE, `DeviceId 19443010C19B387E00` |
| 칩 | Intel Movidius Myriad X (RVC2), 1.4 TOPS |
| 연결 | PoE 인젝터 직결, `169.254.1.222` (링크로컬 폴백) |
| 호스트 | `enp7s0` = `169.254.1.10/16`, 1Gbps/Full, NM 프로필 `oak-poe` |

DHCP 서버가 없는 직결 구성이라 카메라는 `169.254.1.222`로 폴백한다. 자동 탐색(UDP
브로드캐스트)은 장치가 부트로더에서 펌웨어로 부팅될 때 링크가 끊겨 실패하는 경우가 있으므로
**`--ip`로 직접 지정하는 것을 기본으로 한다.**

## 측정 모드 두 가지

둘은 서로 다른 질문에 답한다. 하나만 재면 결론이 틀어지므로 **둘 다 잰다.**

### `--mode throughput` — 모델 처리 용량

`BenchmarkOut`이 NN에 프레임을 최대 속도로 밀어넣어 칩을 포화시킨다. 카메라 프레임레이트에
막히지 않는 순수 모델 성능이며, **모델 A/B 비교는 이 값으로 한다.**

> **지연은 이 모드에서 재지 않는다.** `BenchmarkOut`이 같은 프레임을 원래 타임스탬프 그대로
> 복제하기 때문에, 측정된 "지연"이 프레임의 나이가 되어 시간에 따라 무한히 증가한다
> (실측 확인: 9.5s → 10.8s → 12.1s). 물리적 의미가 없어 아예 측정을 끈다.

### `--mode camera` — 실제 경로

카메라 → NN 실제 파이프라인. 차량에서 체감하는 FPS와 **지연**을 잰다. 카메라 FPS가 상한이므로
모델이 그보다 빠르면 카메라에 막힌 값이 나온다(예: 30fps 카메라에 40fps 모델 → 30으로 측정).
제어 루프 설계에는 이쪽 지연값이 필요하다.

## 실측으로 확인된 함정: 카메라 FPS를 모델 용량보다 높이지 말 것

`camera` 모드에서 카메라 FPS가 모델 처리 용량보다 높으면 프레임이 쌓여 **지연이 폭증한다.**
FPS는 거의 안 오르는데 지연만 6배가 된다.

| 모델 | 카메라 FPS | 측정 FPS | 지연 평균 |
|---|---|---|---|
| YOLOv10n | 30 | 16.13 | **492.15 ms** |
| YOLOv10n | 15 | 15.00 | **83.11 ms** |

FPS는 16.13 → 15.00으로 7% 줄었을 뿐인데 지연은 492ms → 83ms로 **409ms 줄었다.**

실시간 제어에 쓸 경우 이 지연이 그대로 반응 지연이 된다.
**카메라 FPS는 throughput 모드로 잰 모델 용량 이하로 설정한다.**

## 비교가 성립하기 위한 조건

A/B를 주장하려면 아래가 **같아야** 한다. 다르면 결과에 명시한다.

1. **입력 해상도** — 연산량이 픽셀 수에 비례한다. 512×288과 640×640을 비교하면 모델이 아니라
   해상도를 비교한 것이 된다.
2. **SHAVE/스레드 배분** — `--shaves`, `--threads`로 고정한다. 생략하면 depthai가 자동
   배분하는데, 모델마다 다르게 잡힐 수 있다.
3. **워밍업 제외** — 첫 수 초는 버린다(기본 5초). 초기 할당/캐시 효과가 섞인다.
4. **측정 길이** — 기본 30초. 짧으면 분산이 크다.
5. **장치 온도** — 연속 측정 시 스로틀링이 있을 수 있어 실행 사이에 간격을 둔다
   (`run_baseline.sh`는 3초).

## 사용법

```bash
# 스톡 베이스라인 일괄 측정 (3개 모델 × 2개 모드)
./benchmark/run_baseline.sh 169.254.1.222

# 개별 측정
python3 benchmark/edge_benchmark.py \
    --model luxonis/yolov6-nano:r2-coco-512x288 \
    --ip 169.254.1.222 --label yolov6n-stock --mode throughput

# MATLAB 산출물 측정 (로컬 NNArchive 경로를 그대로 넘긴다)
python3 benchmark/edge_benchmark.py \
    --model /path/to/matlab_model.tar.xz \
    --ip 169.254.1.222 --label matlab-opt --mode throughput

# 결과를 마크다운 표로
python3 benchmark/summarize.py --out benchmark/RESULTS.md
```

결과는 `results/<label>_<mode>_<timestamp>.json`에 장치·모델·설정·환경 정보와 함께 저장된다.
집계 스크립트가 이 파일들을 읽어 표를 만든다.

## 사용 가능한 스톡 모델 (RVC2, 모델 주)

API 키 없이 받아진다. `dai.getModelFromZoo()`가 `~/.cache/depthai/models/`에 캐시한다.

| 슬러그 | 입력 |
|---|---|
| `luxonis/yolov6-nano:r2-coco-512x288` | 512×288 |
| `luxonis/yolov10-nano:coco-512x288` | 512×288 |
| `luxonis/yolo26-nano:coco-512x288` | 512×288 |

**YOLO11은 모델 주에 RVC2용으로 존재하지만(`yolo11:nano-1.0.0`) 소유 팀이 TRI라 공개
다운로드가 404로 막혀 있다.** YOLO11 계열을 베이스라인에 넣으려면 가중치를 직접 변환해야 한다.

## 대상 모델: 신호등 증분학습 YOLOv8n

`~/Desktop/yolov8n.pt` (2026-09-13 학습, Ultralytics 8.4.61, fp16 `best.pt`).

| 항목 | 값 |
|---|---|
| 아키텍처 | YOLOv8n, 72 layers, 3,151,904 params |
| 클래스 | **nc=80 (COCO 표준)** — 신호 관련은 `traffic light`(9), `stop sign`(11) |
| 학습 | epochs 20, batch 16, **imgsz 640** |
| 베이스 | `traffic_incremental_80/runs/yolov8n_80class_incremental/weights/best.pt` |
| 데이터 | `traffic_incremental_500_20260913/dataset/data.yaml` |
| 실행 이름 | `location_detector` |
| 출처 | `/home/sangmin/.../HL-Global-Mobility-Team2` (타 팀 자산) |

> **이 모델은 신호등의 "위치"만 찾고 "상태"는 모른다.** 클래스가 COCO 80종 그대로라
> 빨강/초록/화살표 구분이 없다. 실행 이름이 `location_detector`인 것과 일치한다.
> 자율주행 판단에 쓰려면 검출된 박스 안에서 신호 상태를 따로 판별하는 단계가 필요하다.

로컬 ONNX 내보내기는 완료했다(업로드 없음):

| 파일 | 입력 | GFLOPs |
|---|---|---|
| `models/yolov8n_traffic_640.onnx` | 640×640 | 8.7 |
| `models/yolov8n_traffic_288x512.onnx` | 512×288 | 3.1 |

512×288 쪽은 스톡 베이스라인과 해상도를 맞추기 위한 것이다.

## 블롭 변환 (완료)

`blobconverter`로 온라인 변환했다(**모델 가중치가 Luxonis 서버로 업로드됨 — 사용자 동의 하에 진행**).

```python
blobconverter.from_onnx(
    model='benchmark/models/yolov8n_traffic_288x512.onnx',
    data_type='FP16', shaves=6, use_cache=False,
    optimizer_params=['--scale_values=[255,255,255]', '--reverse_input_channels'])
```

산출물: `models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob` (6.4 MB)

| | |
|---|---|
| 입력 | `images` [512, 288, 3, 1] U8 |
| 출력 | `output0` [3024, 84, 1] FP16 (4 box + 80 class) |
| SHAVE | 6 | 
| OpenVINO | 2022.1 |

출력이 YOLOv8 **원시 head 텐서**다. depthai가 칩 위에서 디코딩하지 못하므로
`NeuralNetwork` 노드로 원시 텐서만 뽑는다. FPS/지연 계측에는 충분하지만, 검출 결과를 실제로
쓰려면 호스트에서 디코딩(NMS 포함)해야 하고 그 비용은 아래 수치에 **포함되어 있지 않다.**

### 이 블롭은 30초 연속 포화에서 멈춘다

재현성 있게 확인했다. 10초는 정상, 30초는 장치가 응답을 멈추고 종료 시 세그폴트가 난다.
스톡 주 모델들은 같은 조건에서 30초를 견뎠으므로 **이 블롭 고유의 문제**다.
그래서 이 모델만 10초 × 3회 반복으로 측정했다(편차 0.4%로 매우 안정적).

## 참고: 로컬 변환은 이 장비에서 불가능하다

ONNX → RVC2 `.blob` 단계에서 막혔다. 이 장비에서 **로컬 변환이 불가능하다**:

- `luxonis/modelconverter` — **Docker 필요**. 이 장비에 Docker 없음(설치엔 sudo 필요)
- OpenVINO `compile_tool`의 MYRIAD 플러그인 — Myriad X를 지원하는 마지막 세대는
  OpenVINO 2022.x인데, **PyPI에 Python 3.12용으로 2024.1.0 이상만 남아 있고** 그 버전들은
  MYRIAD 지원을 제거했다. 설치 시도 실패 확인.

남은 경로는 **온라인 변환(tools.luxonis.com / blobconverter)** 뿐이며, 이는 **가중치를 외부
서버에 업로드**한다. 대상 모델이 타 팀(HL-Global-Mobility-Team2) 자산이므로 진행 전 확인 필요.

## MATLAB/Simulink 산출물을 올리는 경로

MathWorks는 OAK-D/Myriad X용 지원 패키지를 제공하지 않으므로 직접 배포 경로가 없다.
실제로 가능한 경로는 다음 한 가지다.

```
MATLAB 학습 → exportONNXNetwork → ONNX → OpenVINO IR → .blob(RVC2) → NNArchive → depthai
```

막히는 지점이 셋이다. 벤치마크 결과를 해석할 때 이 제약을 함께 기록해야 한다.

1. **디코딩** — depthai의 `DetectionNetwork`는 Ultralytics 계열 head 형식과 앵커/마스크 JSON을
   전제로 칩 위에서 디코딩까지 해준다. MATLAB이 뱉은 head는 이 형식이 아니라서, raw 텐서를
   호스트로 보내 직접 디코딩해야 할 가능성이 높다. 그러면 엣지 이점이 줄고 지연이 는다.
   → 이 경우 `edge_benchmark.py`는 `NeuralNetwork` 노드를 쓰므로 계측 자체는 그대로 된다
   (디코딩 비용은 빠진 값이라는 점을 결과에 명시할 것).
2. **연산자 지원** — Myriad X의 OpenVINO VPU 플러그인은 지원 op가 제한적이다. MATLAB의 ONNX
   내보내기가 커스텀 레이어를 끼워넣으면 변환 단계에서 실패한다.
3. **아키텍처 세대** — MathWorks 공식 ONNX 내보내기 예제는 YOLO v2 기준이다. 같은 연산량에서
   최신 nano 계열보다 정확도가 낮을 수 있다.

### 주의: 모델을 외부에 업로드하게 된다

Luxonis 변환 도구(`tools.luxonis.com`)는 가중치 파일을 업로드받아 서버에서 변환한다.
자체 학습한 콘 검출 모델을 올리는 것이 문제가 되는지 먼저 확인할 것.

## 호스트 CPU가 RVC2보다 빠르다

측정된 사실이다. 엣지로 옮기는 근거를 "속도"로 잡으면 안 된다.

| | FPS | 지연 |
|---|---|---|
| 호스트 CPU (i7-9750H, 512×288) | **49.19** | 20.33 ms |
| RVC2 최고 스톡 (YOLOv6n, 512×288) | 40.20 | 49.07 ms |

엣지의 실제 이점은 처리량이 아니라 (a) 호스트 CPU를 다른 일에 쓸 수 있다는 점,
(b) 차량 탑재 컴퓨트가 이 노트북보다 약할 경우의 대비다.

> 비교 시 주의: 호스트 수치는 onnxruntime 순수 추론만 잰 값으로 전처리(letterbox)와 NMS가
> 빠져 있다. 엣지 수치도 호스트측 디코딩이 빠져 있어 대략 같은 층위지만, 엄밀한 비교를 하려면
> 양쪽 모두 전처리·후처리를 포함해 다시 재야 한다.

## 알려진 사실

- **FPS를 결정하는 것은 아키텍처와 입력 해상도이지 툴체인이 아니다.** 칩이 1.4 TOPS로
  고정이므로, MATLAB으로 바꾼다고 같은 아키텍처가 빨라지지는 않는다. 최적화로 얻을 수 있는
  것은 (a) 더 가벼운 아키텍처 선택, (b) 양자화/프루닝, (c) 불필요한 레이어 제거다.
- **모델 2개를 동시에 올리면 시분할이다.** RVC2는 NCE 1개와 SHAVE 16코어를 공유하므로
  처리 시간이 대략 더해진다. 2개가 필요해 보이면 클래스를 늘린 단일 모델을 먼저 검토할 것.
- 부트로더 업데이트 권고(0.0.28 → 0.0.29, "improve device discoverability")가 떠 있다.
  탐색 실패와 관련 있으나 플래싱은 실패 시 장치를 못 쓰게 만들 수 있어 보류 중.

## 참고

- [RVC2 Performance 표](https://docs.luxonis.com/software/ai-inference/performance/) — Luxonis 공식 수치
- [RVC2 하드웨어 문서](https://docs.luxonis.com/hardware/platform/rvc/rvc2/)
- [luxonis/tools](https://github.com/luxonis/tools) — YOLO → blob 변환
- [exportONNXNetwork](https://www.mathworks.com/help/deeplearning/ref/exportonnxnetwork.html)
