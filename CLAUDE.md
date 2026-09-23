# camera_ai — 작업 메모리 (다른 컴퓨터에서 이어서 작업하기 위한 파일)

Claude Code는 이 파일을 자동으로 읽는다. 사람도 이 파일 하나로 맥락을 잡을 수 있게 쓴다.
마지막 갱신: 2026-09-23.

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

| 단계 | 폴더 | 파일 | 상태 |
|---|---|---|---|
| ① .pt | `01_pytorch_pt/` | README만 | 원본 가중치 없음. 이름만 확인. 출처("R2") 미확인 |
| ② ONNX | `02_onnx/` | README만 | 파일 없음. buildinfo에서 이름·입출력 확인 |
| ③ IR | `03_openvino_ir/` | README만 | 파일 없음. 변환 명령 확인 |
| ④ .blob | `04_blob/` | README만 | 실물은 ⑤ `example/`의 superblob. 헤더 구조 해석 완료 |
| ⑤ NNArchive | `05_nnarchive/` | `fetch_example.py`, `example/` | 두 예제 추출·해석 완료 |
| ⑥ 칩 | `06_oakd_chip/` | 예제 원본, `run_example.py`, `decompose.py`, `benchmark/`, `step01_record/` | 실행·측정 완료 |
| ⑦ 호스트 | `07_host_output/` | `params.py`, `edge_logger.py`, `review.py`, `can_bridge.py`, `oakd_edge.dbc`, `common.py`, `selftest.sh` | 실카메라 20초 검증 완료. 5분 본 기록·실제 CAN 미완 |
| — | `tools/` | `oakd_preview.py` | 카메라 연결 확인용 (AI 없음) |

①~④가 비어 있는 이유: Luxonis는 최종 NNArchive만 배포한다. 중간 파일은 `buildinfo.json`의 기록으로만 분석한다.

## 3. 다음 할 일 (우선순위)

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
cd 07_host_output && ./selftest.sh 20                 # 카메라 없이 전체 흐름 검증 (통과해야 정상)
cd .. && python3 05_nnarchive/fetch_example.py        # 예제 모델 받기 + superblob 복원 (git에 없음)
```

git에 없는 것: `*.superblob`(용량), `07_host_output/runs/`(5분 기록 ≈ 1.2 GB).

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
- 종료 시 크래시 덤프가 자주 남는다(`~/.cache/depthai/crashdumps/`). 종료 전 큐를 비운다.

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

- **OAK-D PoE에는 CAN 포트가 없다.** 호스트가 USB-CAN으로 중계 (`can_bridge.py`, `oakd_edge.dbc`).
- `roi_*`는 깊이 프레임 **픽셀** 값. `lens_pos`는 고정초점이라 -1.
- 전처리(÷255)는 블롭 또는 config 중 **한 곳에서만**. 둘 다 하면 검출 0개인데 FPS는 정상으로 나온다.
- 이 PC의 시스템 matplotlib은 numpy 2와 충돌 → 그래프는 OpenCV로 그린다.

## 7. 작업 방식 (사용자 선호)

- **과정이 중요하다.** 단계마다 기록(`NOTES.md`, `PROGRESS.md`)을 남긴다. 결과만 남기지 말 것.
- 문서는 **표 위주, 설명 문장 최소.** 약어는 처음에 풀어 쓴다. 군더더기 삭제를 여러 번 요청받았다.
- 실제 장치 명령 전에 준비·검증부터. 한국어로 답한다.
- 이 저장소는 **공개**다. 토큰·비밀번호를 커밋하지 말 것.

## 8. 발행 문서 (claude.ai, 비공개 링크)

| 문서 | 링크 |
|---|---|
| ⑤~⑦단계 파일 역할과 기능 (현재 구조 기준) | https://claude.ai/code/artifact/b3c03f75-7695-4779-8a0a-56ac1599d71c |
| 엣지에 모델 올리기 과정과 원리 (6절은 삭제된 `edge_deploy.py` 기준이라 낡음) | https://claude.ai/code/artifact/df7e517a-23fa-474a-98a4-8df27fb247f7 |
| Step 01 · 공식 예제 실험 기록 | https://claude.ai/code/artifact/423ed4dd-372a-4117-a5c5-747c2f02693d |
| Step 02 · 신호등 모델 (현재 범위 밖) | https://claude.ai/code/artifact/fd012efe-cae1-4e01-92a8-c12cb81b2498 |

## 9. 자주 쓰는 명령

```bash
python3 05_nnarchive/fetch_example.py
python3 06_oakd_chip/run_example.py 169.254.1.222                       # q로 종료
python3 06_oakd_chip/benchmark/edge_benchmark.py --model yolov6-nano --ip 169.254.1.222 \
    --label x --mode throughput --duration 10 --warmup 3
cd 07_host_output
python3 edge_logger.py --ip 169.254.1.222 --duration 300                # 5분
python3 review.py summary|frame|sheet|timeline runs/<폴더> [...]
python3 can_bridge.py dbc|selftest|replay|listen [...]
```
