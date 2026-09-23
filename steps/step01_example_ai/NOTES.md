# Step 01 — OAK-D 공식 예제 AI 실행

**목적:** depthai 공식 예제를 그대로 돌려 (a) 장치에서 AI가 실제로 동작하는지,
(b) 어떤 성능이 나오는지, (c) **그 숫자가 무엇을 측정한 값인지**를 확인한다.

**일자:** 2026-09-16 · **장치:** OAK-D PoE `19443010C19B387E00` (Myriad X / RVC2)

---

## 1. 예제 확보

depthai-core 저장소에서 설치된 라이브러리와 **같은 버전(v3.10.0)** 의 예제를 받았다.
버전이 어긋나면 API가 달라 예제가 안 돈다.

```bash
git clone --depth 1 --branch v3.10.0 https://github.com/luxonis/depthai-core.git
```

`examples/python/DetectionNetwork/detection_network.py`를 골랐다. 가장 기본형이다.
원본을 `detection_network_original.py`로 **수정 없이** 보관했다.

예제의 구조는 단순하다:

```python
cameraNode = pipeline.create(dai.node.Camera).build()
detectionNetwork = pipeline.create(dai.node.DetectionNetwork).build(
    cameraNode, dai.NNModelDescription("yolov6-nano"))
qRgb = detectionNetwork.passthrough.createOutputQueue()   # 영상
qDet = detectionNetwork.out.createOutputQueue()           # 검출 결과
```

`DetectionNetwork`는 모델 주에서 모델을 받아 **칩 위에서 디코딩·NMS까지** 수행한다.
호스트로는 검출 박스만 온다. `passthrough`는 그 프레임의 영상이다.

## 2. 수정 없이 실행

```bash
python3 detection_network_original.py
```

**그대로 동작했다.** 장치 IP를 지정하지 않았는데도 자동 탐색이 성공했다
(이전에 자동 탐색이 실패한 적이 있어 실패를 예상했으나 이번엔 붙었다 — 항상 실패하는 게
아니라 **장치가 부팅 중일 때만** 실패한다는 뜻이다).

검출 창에 `person 83%` 박스가 그려지고 `NN fps: 21.27` 오버레이가 나왔다.
→ `output/detection_window.png`

FPS는 시간이 지나며 수렴했다:

```
FPS: 2.79   <- 시작 직후
FPS: 19.62
FPS: 20.39
...
FPS: 21.35  <- 66초 후 완전 수렴
```

**주의:** 예제의 FPS는 `counter / (now - startTime)` 즉 **누적 평균**이다. startTime이
파이프라인 시작 직후라서 모델 다운로드·부팅 시간이 분모에 섞인다. 그래서 처음에 2.79로
시작해 서서히 올라간다. 수렴값 **21.35**가 실제 값에 가깝다.

## 3. 이 숫자가 무엇을 측정한 값인가

21.35 FPS에는 NN 추론 말고도 두 가지가 섞여 있다.

- **영상 전송** — `passthrough`로 프레임을 호스트까지 보낸다 (PoE 네트워크)
- **렌더링** — `cv2.imshow`로 화면에 그린다

어디까지가 모델 성능인지 보려고 `decompose.py`를 만들어 하나씩 떼어냈다.
워밍업 5초를 버리고 30초씩 쟀으며, 누적 평균과 **최근 구간 순간 FPS**를 함께 냈다.

| 모드 | 내용 | 누적 FPS | 순간 FPS |
|---|---|---|---|
| `full` | 예제 그대로 (영상 수신 + 렌더링) | 21.44 | 21.45 |
| `nodisplay` | 영상은 받되 화면에 안 그림 | 21.42 | 21.38 |
| `detonly` | passthrough 큐 자체를 안 만듦 | **실패 — 아래 참고** |

**렌더링 비용은 사실상 0이다** (21.44 → 21.42).

`detonly`가 실패해서 NN 단독 용량은 별도 계측기로 쟀다
(`benchmark/edge_benchmark.py`, BenchmarkIn/BenchmarkOut으로 NN을 포화시키는 방식):

```
FPS 22.56   (512×384, 칩 위 디코딩, 워밍업 3초 제외 10초 측정)
```

### 결론

| 구간 | FPS | 비고 |
|---|---|---|
| NN 단독 용량 | **22.56** | 칩이 낼 수 있는 최대 |
| 예제 전체 | **21.44** | 영상 전송 + 렌더링 포함 |
| 차이 | −5% | 대부분 영상 전송 비용 |

**예제가 보여주는 21.35 FPS는 거의 그대로 모델의 성능이다.** 파이프라인 오버헤드가 5%뿐이라
병목은 NN 자체다. 영상을 호스트로 안 보내도 22.56이 상한이다.

---

## 발견한 것

### 파일명과 실제 입력 크기가 다르다

`dai.NNModelDescription("yolov6-nano")`가 받아오는 파일은
`YOLOv6_Nano-R2_COCO_512x288.rvc2.tar.xz`인데 **실제 입력은 512×384**다.

```
[예제 기본값: yolov6-nano]
  파일  : YOLOv6_Nano-R2_COCO_512x288.rvc2.tar.xz
  입력  : 512 x 384 = 196,608 px

[명시 지정: luxonis/yolov6-nano:r2-coco-512x288]
  파일  : yolov6n-r2-288x512.rvc2.tar.xz
  입력  : 512 x 288 = 147,456 px
```

**두 개는 서로 다른 아티팩트이고, 앞의 것은 파일명이 내용과 맞지 않는다.**
파일명을 믿고 "512×288에서 21.35 FPS"라고 기록하면 틀린 조건을 문서에 남기게 된다.
성능 수치를 적을 때는 **반드시 `getInputWidth()/getInputHeight()`로 확인**할 것.

픽셀 수가 1.33배 차이라 성능도 그만큼 차이 난다 — 같은 YOLOv6n인데
512×288에서 31.79 FPS, 512×384에서 22.56 FPS다 (비율 1.41).

### passthrough를 소비하지 않으면 장치가 죽는다

`detonly` 모드(= `passthrough.createOutputQueue()`를 호출하지 않음)는 **재현성 있게**
장치 연결을 끊었다.

```
Monitor thread - ping was missed, closing the device connection
terminate called after throwing an instance of 'std::invalid_argument'
  what():  Cannot create XLinkStream using unconnected XLinkConnection
```

큐를 안 만들면 데이터가 안 흐를 것으로 기대했으나, 실제로는 장치 내부에 쌓여 keepalive
ping을 놓치는 것으로 보인다. **출력을 안 쓸 거면 큐를 만들지 않는 것만으로는 부족하다.**

### 장치가 종료 시점에 자주 크래시한다

측정 자체는 완료되는데 파이프라인을 닫을 때 crash dump가 남는 경우가 잦다.
`~/.cache/depthai/crashdumps/`에 쌓인다. 데이터에는 영향이 없었지만 연속 실행 시
장치 복구를 기다려야 한다(ping으로 확인, 보통 15~20초).

---

## 남긴 파일

| 파일 | 내용 |
|---|---|
| `detection_network_original.py` | 공식 예제 원본 (수정 없음) |
| `decompose.py` | FPS 분해 측정 스크립트 |
| `output/01_original_run.log` | 예제 원본 실행 로그 (FPS 수렴 과정) |
| `output/02_screenshot_run.log` | 스크린샷 촬영 시 실행 로그 |
| `output/03_decompose.log` | full/nodisplay 분해 결과 |
| `output/04_detonly.log` | detonly 실패 로그 |
| `output/detection_window.png` | 검출 창 캡처 (person 83%) |

## 다음 단계로 넘길 것

- 이 예제는 **COCO 80클래스 YOLOv6n**이다. 신호등은 클래스 9번으로 포함돼 있으나
  전용 모델은 아니다.
- 입력 해상도가 성능을 크게 좌우한다는 것이 확인됐다(512×288 ↔ 512×384에서 1.41배).
  이후 모델을 비교할 때 **해상도를 맞추는 것이 최우선 조건**이다.
- 예제의 FPS 계산 방식(누적 평균)은 비교용으로 부적절하다. 워밍업을 버리고 정상 구간만
  재는 방식이 필요하다.
