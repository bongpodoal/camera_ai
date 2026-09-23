# MATLAB 쪽 학습·변환

신호등 검출 모델을 MATLAB에서 학습하고 OAK-D에 올려 측정하기까지의 경로.
엣지 기준선(`../benchmark/BASELINE.md`)과 **같은 조건**으로 재야 비교가 성립한다.

## 필요한 것

- MATLAB + **Deep Learning Toolbox** + **Computer Vision Toolbox**
- **Deep Learning Toolbox Converter for ONNX Model Format** (무료 애드온)
- 학습 데이터셋 (YOLO 형식)

## 순서

### 1. 툴체인 검증 (학습 전에)

```matlab
>> run('training/matlab/step1_check_toolchain.m')
```

학습을 하지 않고 몇 분 안에 끝난다. 확인하는 것은 하나다 —
**MATLAB에서 만든 검출기를 ONNX로 내보낼 수 있는가.**

`detector.Network` 속성 접근은 MathWorks 문서에 **YOLOv2 기준으로만** 나와 있고
YOLOX 문서의 공개 속성 목록(ClassNames / InputSize / ModelName)에는 없다. 여기서 막히면
뒤의 학습이 전부 헛수고가 되므로 먼저 확인한다.

막힐 경우 대안은 **YOLOv4 / YOLOv2** — ONNX 내보내기가 문서화돼 있다.
정확도는 낮지만 경로가 확실하다.

여유가 있으면 이 단계에서 나온 ONNX를 3단계 변환까지 돌려보는 것이 좋다.
경로 전체가 뚫리는지 확인한 뒤에 학습에 시간을 쓰는 순서다.

### 2. 데이터 변환 + 학습

```bash
python3 training/check_dataset.py  <데이터셋_루트>   # 라벨 무결성 검증
python3 training/yolo_to_matlab.py <데이터셋_루트>   # MATLAB용 CSV 생성
```
```matlab
>> run('training/matlab/step2_train.m')
```

### 3. 변환 + 측정

```bash
./training/matlab/step3_convert_and_benchmark.sh traffic_yolox.onnx
```

## 데이터셋 형식

Ultralytics YOLO 표준을 기대한다. Roboflow/CVAT에서 "YOLOv8" 형식으로 내보내면 그대로 나온다.

```
dataset/
  data.yaml              # names, nc, train/val 경로
  images/train/*.jpg     labels/train/*.txt
  images/val/*.jpg       labels/val/*.txt
```

라벨 한 줄 = `<class_id> <cx> <cy> <w> <h>`, 좌표는 모두 0~1 정규화.

`yolo_to_matlab.py`가 메우는 차이:

| | YOLO | MATLAB |
|---|---|---|
| 좌표 | 정규화된 **중심** `cx cy w h` | **픽셀** 좌상단 `[x y w h]` |
| 인덱싱 | 0-기반 | 1-기반 |
| 라벨 저장 | 이미지당 `.txt` | `boxLabelDatastore` 테이블 |

이미지 경계를 넘는 라벨 클리핑(흔하다)도 함께 처리한다.

## 비교 조건에서 중요한 것

**MATLAB의 `exportONNXNetwork`는 검출기의 후처리(디코딩·NMS)를 ONNX에 담지 않는다.**
원시 head 텐서만 나온다.

이건 오히려 비교에 유리하다 — 엣지 기준선의 **"호스트 디코딩" 경로(33.38 FPS)와 조건이
정확히 같아지기** 때문이다. 칩 위 디코딩(31.79)이 아니라 33.38과 맞대면 된다.

그 외 맞춰야 할 조건은 `../benchmark/README.md` 참고 (해상도 512×288, SHAVE 6,
10초 × 3회, 워밍업 3초).

## 알아둘 제약

- **RVC2는 FP16 전용이라 INT8 양자화가 불가능하다.** MATLAB Model Compression Library의
  두 축 중 양자화가 빠지고 구조적 프루닝만 남는다.
- MathWorks는 OAK-D / Myriad X용 지원 패키지를 제공하지 않는다. 경로는
  `MATLAB → exportONNXNetwork → ONNX → .blob` 하나뿐이다.
- 가장 막히기 쉬운 지점은 ONNX → blob 변환이다. Myriad X의 OpenVINO 플러그인은
  지원 연산자가 제한적이다.

## 주의

`matlab/*.m` 두 파일은 **아직 실행 검증되지 않았다.** API 시그니처는 MathWorks 문서
(R2026a 기준 `yoloxObjectDetector`, `trainYOLOXObjectDetector`, `mAPObjectDetectionMetric`)에서
확인했지만 실제로 돌려본 적은 없다. 오류가 나면 수정이 필요하다.
