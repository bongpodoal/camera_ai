# camera_ai

OAK-D(Myriad X / RVC2)에 YOLO 모델을 올려 **모델이 칩에 올라가 박스가 나오기까지 7단계**로 나눠 분석한다.

```
① .pt → ② ONNX → ③ OpenVINO IR → ④ .blob → ⑤ NNArchive → ⑥ OAK-D 칩 → ⑦ 호스트 검출 박스
```

| 폴더 | 내용 |
|---|---|
| `example/` | 공식 예제 모델(YOLOv6n) 분석 ①~⑦ + `minimal_example/` (최소 실행·기록) |
| `traffic_light/` | 직접 학습한 신호등 모델(YOLO11s, 4클래스)을 ①~⑦로 직접 변환·실행 — `traffic_light/README.md` |
| `tools/` | 카메라 연결 확인 (AI 없음) `oakd_preview.py` |

각 폴더는 그 안에서 실행한다 (스크립트 안의 실행 예시는 그 폴더 기준 경로).

## example/ — 공식 예제 (YOLOv6n)

| 단계 | 폴더 | 예제에서 확보한 것 | 파일 |
|---|---|---|---|
| ① .pt | `01_pytorch_pt/` | 이름만 | README |
| ② ONNX | `02_onnx/` | 이름·입출력 (buildinfo) | README |
| ③ OpenVINO IR | `03_openvino_ir/` | 변환 명령 (buildinfo) | README |
| ④ .blob | `04_blob/` | superblob 실물 + 헤더 해석 | README |
| ⑤ NNArchive | `05_nnarchive/` | 아카이브 실물 + config | `fetch_example.py`, `example/` |
| ⑥ OAK-D 칩 | `06_oakd_chip/` | 예제 실행 + FPS 측정 | 예제 원본, `decompose.py`, `benchmark/` |
| ⑦ 호스트 | `07_host_output/` | 토출 데이터 기록·검토·CAN | `edge_logger.py`, `review.py`, `can_bridge.py` 외 |
| 최소 실행 | `minimal_example/` | 자동 연결 + 기록 + 이미지 저장, 5분 실측 | `run_yolov6n.py`, `data_logger.py`, `image_saver.py` |

예제는 ①~⑤를 Luxonis가 미리 끝낸 NNArchive를 받아 쓴다. 그래서 ①~③은 파일이 아니라
**아카이브 안의 변환 기록으로** 분석한다 (`05_nnarchive/fetch_example.py`).

## traffic_light/ — 신호등 모델 직접 변환

①~⑤를 **직접** 거친다 (YOLOv8n 예제와 같은 절차). 카메라 없이 ①~⑤ 완료·검증, ⑥⑦은 카메라 실행 대기.

## 빠른 시작

```bash
nmcli connection up oak-poe && ping -c 2 169.254.1.222     # 카메라 연결 (재부팅 후)

cd example
python3 05_nnarchive/fetch_example.py                       # ⑤→① 해석
python3 06_oakd_chip/run_example.py                         # ⑥ 예제 실행 (q로 종료)
cd 07_host_output && ./selftest.sh 20                       # ⑦ 카메라 없이 검증

cd traffic_light
python3 06_oakd_chip/run_on_chip.py                         # 신호등 모델 칩 실행 (q로 종료)
```

## 환경

| 항목 | 값 |
|---|---|
| 장치 | **OAK-D-PRO-POE-FF** (고정초점) · `19443010C19B387E00` · Myriad X(RVC2) · 부트로더 0.0.28 |
| 연결 | PoE 직결 · `169.254.1.222` · 호스트 `enp7s0` = `169.254.1.10/16` (NM 프로필 `oak-poe`) |
| 라이브러리 | depthai 3.10.0 · python-can 4.6.1 · cantools 44.1.0 · OpenCV 5.0 |

이전 구조(MATLAB 학습, 신호등 모델, 다른 모델 비교)는 git 커밋 `72a1a01`에 남아 있다.
