# camera_ai

OAK-D(Myriad X / RVC2) 카메라의 **엣지 AI 추론 성능 테스트** 프로젝트.
신호등 검출 모델을 대상으로, 스톡 YOLO와 MATLAB/Simulink로 최적화한 모델의 성능 차이를
같은 조건에서 재어 문서화하는 것이 목적이다.

> 차량 프로젝트(EV_racing)와는 **별개다.** 여기서 재는 값은 카메라와 칩의 성능이지
> 특정 차량 파이프라인의 성능이 아니다.

## 진행 기록

단계별 작업 기록은 [`PROGRESS.md`](PROGRESS.md)와 `steps/<단계>/NOTES.md`에 있다.
각 단계가 끝날 때마다 과정을 문서에 반영한다.

## 구성

```
benchmark/      엣지 추론 계측
  edge_benchmark.py          OAK-D에 모델을 올려 FPS·지연 측정 (핵심)
  host_benchmark.py          호스트 CPU 대조군 (onnxruntime)
  run_averaged_baseline.sh   반복 측정 일괄 실행
  aggregate.py               결과 JSON -> 평균·편차 표
  summarize.py               결과 JSON -> 개별 실행 표
  README.md                  측정 방법론과 조건 (먼저 읽을 것)
  BASELINE.md                평균 기준선 (자동 생성)
  models/                    변환된 모델 (.onnx / .blob / NNArchive)
  results/                   원본 측정 JSON

training/       MATLAB 쪽 학습·변환
  check_dataset.py           YOLO 데이터셋 검증
  yolo_to_matlab.py          YOLO 데이터셋 -> MATLAB용 CSV (좌표계 변환)
  load_dataset.m             CSV -> imageDatastore + boxLabelDatastore
  matlab/step1_check_toolchain.m        학습 전 ONNX 내보내기 가능 여부 검증
  matlab/step2_train.m                  YOLOX 파인튜닝 + mAP 평가 + ONNX 내보내기
  matlab/step3_convert_and_benchmark.sh ONNX -> blob -> 측정

tools/
  oakd_preview.py            카메라 영상/깊이맵 프리뷰 (AI 없음)
  edge_deploy.py             .pt -> NNArchive -> 블롭 -> OAK-D 실행 (export/convert/inspect/run)

steps/          단계별 작업 기록 (과정 중심)
  step01_example_ai/         공식 예제 실행 + FPS 분해
```

## 빠른 시작

```bash
# 카메라 확인
python3 tools/oakd_preview.py --ip 169.254.1.222

# 엣지 측정
python3 benchmark/edge_benchmark.py \
    --model benchmark/models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob \
    --ip 169.254.1.222 --label test --mode throughput --duration 10 --warmup 3

# 집계
python3 benchmark/aggregate.py --out benchmark/BASELINE.md
```

측정 조건과 주의사항은 `benchmark/README.md`에 있다. 특히 **자동 탐색은 신뢰할 수 없으므로
항상 `--ip`로 장치를 직접 지정**해야 한다.

## 현재 상태

- **Step 01 완료** — 공식 예제 실행 및 성능 분해 (21.35 FPS, NN 단독 22.56 FPS)
- 이전 측정(신호등 YOLOv8n 기준선: 호스트 디코딩 33.38 / 칩 위 디코딩 31.79 FPS)은
  `benchmark/BASELINE.md`에 남아 있다. 단계별 재정리 대상.
- **비어 있음** — 정확도(mAP) 축. 학습 데이터셋이 확보돼야 채울 수 있다

## 환경

| 항목 | 값 |
|---|---|
| 장치 | OAK-D PoE · Myriad X(RVC2) · 1.4 TOPS · FP16 전용 |
| 연결 | PoE 인젝터 직결 · `169.254.1.222` (링크로컬 폴백) |
| 호스트 | `enp7s0` = `169.254.1.10/16` · NetworkManager 프로필 `oak-poe` |
| 라이브러리 | depthai 3.10.0 · blobconverter · ultralytics 8.4.152 |
