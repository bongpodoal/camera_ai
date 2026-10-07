# autolaunch — 카메라에 전원만 넣으면 PC 없이 AI 가 자동 실행되는지 (조사 + 시험 준비)

## 조사 결과 (2026-10-07, 웹 문서 근거)
| 방식 | 가능 여부 | 근거 |
|---|---|---|
| DepthAI **v3** 의 RVC2 standalone | **지원 안 함** | v3 문서 Bootloader 페이지: "Both the package format and RVC2 standalone mode are deprecated and no longer supported." RVC2 는 peripheral 모드(호스트 연결)만 권고 |
| DepthAI **v2** standalone (이 카메라 OAK-D Pro PoE FF, RVC2) | 가능하지만 **폐기된 기능** | PoE 모델은 카메라 플래시에 파이프라인을 써 두면(`DeviceBootloader.flash`) 전원이 들어올 때 호스트 없이 시작한다(구버전 문서). 맥에서 depthai 2.33 에 `flash`, `flashClear`, `flashDepthaiApplicationPackage` 가 있는 것까지 확인 |
| OAK4(RVC4) + OAK Apps | 공식 지원 | 이 카메라가 아닌 다른 하드웨어 |
| 작은 컴퓨터가 부팅 때 스크립트 자동 실행 (systemd 등) | 가능 | 카메라 단독이 아니라 호스트가 시작하는 방식 |

### 출력 경로 (두 조건 모두 조사)
| 출력 | 방법 | 비고 |
|---|---|---|
| **이더넷** | 칩 안 `Script` 노드가 UDP/TCP/HTTP 로 송신 | standalone 에서는 DNS 해석기가 없고, Script 만 있는 파이프라인은 안 돈다는 보고가 있음 |
| **CAN** | **카메라 단독 불가.** 카메라에 CAN 포트가 없고 Script 는 이더넷·UART/GPIO·SPI 로만 내보냄 → 변환 장치(UDP→CAN)가 필요 | `udp_to_can_gateway.py`(기준 구현, 맥에서 가상 CAN 으로 검증) |
| UART/GPIO | 가능성 있음(문서상 Script 가 지원) | 이 카메라 커넥터에서 쓸 수 있는지 **미확인** |

알려진 제약(검색): 같은 계열(OAK-D Pro W PoE)에서 standalone 일 때 **IR LED 가 안 켜진다**는 이슈(depthai-python #1080). 플래시한 파이프라인은 전원이 들어올 때마다 돌아서 발열이 생기고, `flashClear` 로 지운다.

## 이 폴더의 파일
| 파일 | 역할 | 검증 |
|---|---|---|
| `build_pipeline_v2.py` | v2 파이프라인(카메라 → YOLO 검출 → Script 가 UDP 송신) | 맥에서 파이프라인 구성 성공 (실행은 카메라 필요) |
| `flash_v2.py` | 파이프라인을 플래시에 써서 자동 실행 설정 | 미검증 |
| `clear_v2.py` | 플래시 지우기 (원복) | 미검증 |
| `listen_udp.py` | PC 에서 UDP 를 받아 첫 패킷 시간·주기·칩 지연을 셈 | 문법만 |
| `udp_to_can_gateway.py` | UDP → CAN(`oakd_canoe.dbc`) 변환 장치 | **맥 가상 CAN 시험 통과** (`selftest_gateway.py`) |

## 시험 순서 (카메라 앞에서, 링크 100 Mbps 이상일 때)
환경: DepthAI **v2** 가 설치된 별도 가상환경 (`pip install "depthai<3"`). v3 환경과 섞지 않는다.
1. PC 에서 `python3 listen_udp.py --port 5005 --seconds 300` 을 켜 둔다.
2. `python3 flash_v2.py --blob <블롭> --dest-ip <PC IP> --classes 4` (먼저 가벼운 블롭으로).
3. 카메라 전원을 껐다 켠다 → PC 에서 **전원부터 첫 패킷까지 시간**, 패킷 주기(5 fps 면 약 5/s), 칩 지연을 본다.
4. 판정: ① PC 연결 없이 시작하는가 ② 주기·지연이 PC 연결 모드와 비슷한가 ③ IR LED 문제 ④ 깊이·여러 모델을 올려도 되는가.
5. `python3 clear_v2.py` 로 원복하고 PC 연결 모드(v3 환경)가 다시 되는지 확인.
6. CAN: 다른 PC 에서 `udp_to_can_gateway.py --interface kvaser --channel 0` 을 켜고 Windows 로거가 FRAME_STATUS·DET_BOX 를 받는지 본다.

## 아직 모르는 것
- v2 `YoloDetectionNetwork` 가 우리 YOLOv8 형식(앵커 없는) 블롭을 `setAnchors([])` 로 해석하는지 (`build_pipeline_v2.py` 의 가정)
- 부트로더 0.0.28 에서 v2 플래시가 되는지, 플래시 용량(블롭 크기)과 한계
- standalone 에서 `socket` UDP 송신이 실제로 되는지
- 다중작업 모델(분할 출력)은 칩 위 Script 로 해석하기 어렵다 → standalone 에서는 원시 출력을 보내고 변환 장치가 해석해야 할 수 있음
