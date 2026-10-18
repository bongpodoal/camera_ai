# 자동 launch 시험 결과 (2026-10-12, Ubuntu 카메라 PC) — **중단: 플래시 실패 후 카메라 무응답**

환경: DepthAI v2.33.0.0 (`~/venvs/depthai_v2`), 카메라 OAK-D-PRO-POE-FF, 부트로더 0.0.28, 블롭 `traffic_light_v8n-416x416.blob`(8 SHAVE, 4클래스), 수신 PC 169.254.1.10:5005.

## 경과
| 순서 | 한 일 | 결과 |
|---|---|---|
| 전제 | 이더넷 링크·카메라 부팅 확인 | 100 Mbps(이후 1000 Mbps), ping 응답, v3 연결로 부팅 OK |
| 사전 시험 | 같은 파이프라인을 **호스트 연결 모드**(플래시 없이)로 실행 | 칩 Script 에서 `ModuleNotFoundError: No module named 'socket'` 로 죽음, UDP 0개 → host 모드에서는 `socket` 사용 불가(스탠드얼론에서만 열리는지는 플래시로 확인 필요) |
| 플래시 | `flash_v2.py` | **62.7% 에서 실패**: `Monitor thread … ping was missed` → `XLinkReadError: Couldn't read data from stream '__bootloader'`. 같은 시각 커널 로그에 `enp6s0` 링크 Down/Up 반복(15:11:51~15:12:28) |
| 원복 | `clear_v2.py` | `Specified device not found` (카메라가 응답하지 않아 실행 못 함) |
| 현재 상태 | 링크 1000 Mbps Up, 그러나 `169.254.1.222` 로 ARP FAILED(`No route to host`), `getAllAvailableDevices`·`DeviceBootloader.getAllAvailableDevices` 모두 빈 목록, 포트 5005 에 UDP 도 오지 않음 | **카메라 무응답.** 플래시가 중간까지만 써진 상태일 수 있음 |

## 판정 (시험 목표 항목)
| 항목 | 결과 |
|---|---|
| 전원→첫 UDP 패킷 시간 | 측정 못 함 |
| 패킷 주기 / 칩 지연 | 측정 못 함 |
| IR LED | 확인 못 함 |
| ① PC 연결 없이 시작하는가 | 판정 불가 |
| ④ 깊이·여러 모델 | 시험 못 함 |
| CAN 게이트웨이(`udp_to_can_gateway.py`) | 시험 못 함 (UDP 가 없음) |

## "아직 모르는 것" 4가지에 대한 답
| 질문 | 답 |
|---|---|
| v2 `YoloDetectionNetwork` 가 YOLOv8 블롭을 `setAnchors([])` 로 해석하는가 | 파이프라인은 시작됨(`DetectionNetwork` 경고만, 오류 없음). 출력이 실제로 맞는지는 Script 가 죽어 **확인 못 함** |
| 부트로더 0.0.28 에서 v2 플래시가 되는가 | **62.7% 까지 진행 후 링크가 끊겨 실패.** 완료·부팅은 못 봄. 링크 불안정(이번 시험 전에도 10 Mbps/NO-CARRIER 이력)이 원인인지 플래시 자체 문제인지 **구분 못 함** |
| standalone 에서 `socket` UDP 송신이 되는가 | **호스트 모드에서는 `socket` 모듈이 없다**(위). 스탠드얼론은 확인 못 함 |
| 다중작업 모델 해석 | 시험 못 함 |

## 다음에 필요한 것
1. 카메라 PoE 케이블을 뽑았다 다시 꽂아(전원 재인가) 부트로더가 응답하는지 확인 → 응답하면 `clear_v2.py` 로 플래시를 지워 원복하고 v3 연결이 되는지 확인.
2. 케이블·PoE 전원 점검(링크가 플래시 중 끊김). 점검 전에는 플래시 재시도 금지.
3. 안정된 뒤 `socket` 문제(호스트 모드에서 불가)를 포함해 플래시 재시도.

## 추가 (15:17~15:23, 사용자가 전원을 다시 꽂은 뒤)
링크는 15:17:47 에 1000 Mbps 로 올라왔지만 카메라는 5분 넘게 ARP(`FAILED`)·ping·장치 검색(`getAllAvailableDevices`·`DeviceBootloader`, 직접 연결 3회)에 응답하지 않았고 UDP 도 오지 않았다. 15:22:40 에 링크가 다시 Down 이 되었다. 즉 **PoE 전원·케이블 접촉이 불안정**하거나 카메라가 부팅 루프에 있는 것으로 보이며, 이 PC 에서는 원복(`clear_v2.py`)을 실행할 수 없는 상태다.

## 복구 (15:24~, 사용자가 케이블을 다시 꽂은 뒤)
링크 1000 Mbps 로 올라오고 카메라가 ping·부트로더 검색(`X_LINK_BOOTLOADER`)에 응답했다. `clear_v2.py` → `지움: True`. 카메라 재부팅 후 ping 40/40, v3 연결 OK(OAK-D-PRO-POE-FF, 부트로더 0.0.28). **원복 완료.**
정리: 플래시 중 62.7% 에서 끊긴 원인은 링크(PoE 전원·케이블 접촉) 불안정으로 보인다. 케이블을 다시 꽂자 복구되었고, 플래시 자체가 카메라를 망가뜨린 것은 아니다. 자동 launch 시험(전원→첫 패킷, IR LED, 스탠드얼론 UDP, CAN 게이트웨이)은 **미완**이며, 링크가 안정된 상태에서 플래시를 다시 시도해야 판정할 수 있다.

## 2차 시도 (15:27~15:40, 링크 안정 후) — **플래시는 완료됐으나 PC 없이 시작하지 않음**
| 항목 | 결과 |
|---|---|
| 플래시 | `flash_v2.py` **100% 완료** (부트로더 0.0.28 에서 v2 플래시 가능). 링크 1000 Mbps, 중간 끊김 없음 |
| 부트로더 설정 | `network.timeoutMs = 30000` (전원 후 30초 안에 호스트가 연결하지 않으면 플래시된 앱을 시작해야 함) |
| 전원 재인가 후 UDP | 두 번 시도(1차: 호스트 쪽 장치 검색이 섞임, 2차: **전원 후 아무것도 건드리지 않고 4분 대기**). 링크 Up 15:35:16 기준 4분 넘게 **UDP 패킷 0개** (수신기 `0.0.0.0:5005`, 목적지 `169.254.1.10:5005`) |
| 카메라 상태 | 전원 후 계속 `X_LINK_BOOTLOADER`, ping 응답. 플래시된 앱이 실제로 돌았다는 증거 없음 |
| 원복 | `clear_v2.py` → `지움: True`, 재부팅 후 v3 연결 OK (OAK-D-PRO-POE-FF, 부트로더 0.0.28) |

### 판정 (최종)
| 항목 | 결과 |
|---|---|
| 전원→첫 UDP 패킷 시간 | 측정 못 함 (패킷이 오지 않음) |
| 패킷 주기 / 칩 지연 / IR LED | 측정 못 함 |
| ① PC 연결 없이 시작하는가 | **이 시험에서는 아니오** (30초 대기 후에도 UDP 없음, 부트로더 상태 유지). 원인은 구분 못 함 |
| ④ 깊이·여러 모델 | 시험 못 함 |
| CAN 게이트웨이 | UDP 가 없어 시험 못 함 |

### "아직 모르는 것" 4가지 (최종 답)
| 질문 | 답 |
|---|---|
| v2 `YoloDetectionNetwork` 가 YOLOv8 블롭을 `setAnchors([])` 로 해석하는가 | 파이프라인은 시작(오류 없음). 출력이 맞는지는 Script 가 호스트 모드에서 `socket` 때문에 죽어 **확인 못 함** |
| 부트로더 0.0.28 에서 v2 플래시가 되는가 | **됨** (2차에서 100% 완료, 6.1 MB 블롭). 1차 62.7% 실패는 링크 끊김 때문 |
| standalone 에서 `socket` UDP 송신이 되는가 | 호스트 모드에서는 `socket` 모듈이 없다. 스탠드얼론에서는 **패킷이 오지 않아 송신되는 것을 확인하지 못함** (앱이 안 돌았거나, 돌았어도 `socket`/네트워크 설정 문제) |
| 다중작업 모델 해석 | 시험 못 함 |

### 다음에 해 볼 것 (미시도)
- 플래시된 앱이 정말 시작하는지 구분: Script 에서 `socket` 없이 동작이 보이는 최소 파이프라인(예: LED/UART 대신 UDP 이전 단계)으로 확인, 또는 카메라 LED 상태 관찰.
- 부트로더 설정(`flashConfig`)의 앱 시작 조건/`appMem`, 또는 `dai.DeviceBootloader.flashBootloader` 업데이트가 필요한지는 미확인(부트로더 업데이트는 하지 않음).
- 사용 가능한 공식 방식은 OAK4(RVC4) 또는 호스트(작은 컴퓨터)에서 자동 실행하는 방식.

## 호스트 자동 실행 (systemd) — 진행 중 (2026-10-12, Ubuntu 카메라 PC)
`host_autostart/` 에 `run_oakd.sh`·`oakd-autostart.service`·`install.sh` 저장(맥 세션 제공). 이 PC 맞춤으로 두 가지만 수정: `run_oakd.sh` 에 `CAN_INTERFACE`(기본 socketcan, 이 PC 는 kvaser + `CAN_IF=0`, `can0` 없음), `install.sh` 가 `/etc/default/oakd-autostart` 에 `CAN_INTERFACE`·`CAN_IF` 를 환경변수로 기록.
| 항목 | 결과 |
|---|---|
| 문법 (`bash -n`) | 통과 |
| `can_demo.py` 인자 (`--mode vehicle --model --raw --ip --interface --channel --bitrate --duration --out-dir`) | 현재 파일과 일치 |
| 서비스 없이 직접 실행 (`run_oakd.sh`, traffic_light_v8n, Raw 끔, 60초) | 카메라 응답 대기 → can_demo 시작 → **frames 305, fps 5.02, dropped 0, edge_ms 80.3**, 시작 9.2초. `can_tx_errors` 365 는 Windows 로거(수신기)가 없어서 ACK 가 없었기 때문(수신기 있을 때는 이전 측정에서 0) |
| 직접 실행 1차 | 카메라가 직전 `clear_v2.py` 후 재부팅 중이라 `Device already closed or disconnected`(크래시 덤프). 링크 안정 후 재시도로 통과 → 부팅 직후엔 카메라 복귀를 충분히 기다려야 함 |
| 서비스 설치·재부팅·카메라 재인가 시험 | **미실시** — `sudo` 비밀번호가 필요해 이 세션에서 설치 불가, 재부팅은 사용자 확인 필요 |

### 카메라 PoE 뽑기 시험 (2026-10-12 16:19, 서비스 실행 중)
| 항목 | 결과 |
|---|---|
| 마지막 정상 프레임 | 16:19:26.10 (Seq 525), 5 fps 로 마지막까지 오다 갑자기 끊김. 링크 Down 16:19:26 과 1초 안에 일치 |
| 중간 | depthai 자동 재연결 성공(16:19:53) → 6프레임(16:19:54.35~55.19) → 링크 재단절(16:20:05) → 통신 예외 → 16:20:31 `Segmentation fault` 로 종료 |
| 서비스 복귀 | `Restart=always` 로 16:20:36 자동 재시작 → 안정 재개 16:20:49.91 |
| 끊김 | 마지막 정상 → 안정 재개 **83.8초** (공백 28.2 + 54.7초) |
| 데이터 | 재개 때마다 Seq 0 으로 리셋(새 파이프라인), SeqGap 0, 결번 0, can_lost_frames 0 |
| 판정 | 사람 손 없이 복귀함. 단 정상 종료가 아니라 SEGV 를 거쳐 복귀. 케이블 접촉이 불안정하면 링크가 여러 번 끊겼다 붙어 복귀가 늦어짐 |
| 시작 시간 | 서비스 시작 16:17:31 → 첫 CAN 프레임 16:17:41.3 (약 10초, 두 PC 시계가 1초 안쪽이라는 가정) |

### 재부팅 시험 (2026-10-12 16:23 부팅, 서비스 enabled 상태)
| 항목 | 결과 |
|---|---|
| 부팅 시각 (`uptime -s`) | 16:23:51 |
| 서비스 시작 (`boot.log`) | 16:24:06.663 (부팅 후 약 15초, 로그인 없이 systemd 가 시작) |
| 카메라 응답 | 16:24:09.675 (시작 후 약 3초) |
| `oakd-autostart` | enabled · active, `can_demo.py` 프로세스 실행 중 (traffic_light_v8n, Raw 끔, kvaser:0, 500 kbps) |
| 링크 | carrier 1, 1000 Mbps |
| 저널 경고 | `canSetAcceptanceFilter … Not implemented [-32]`(Leaf v3 에서 이전부터 나던 것), 부트로더 0.0.28→0.0.29 업데이트 권장(미적용) |
| **부팅→첫 CAN 프레임** | **미측정.** 이 PC 는 `--duration` 이 1년이라 종료 전까지 요약 파일이 안 써지고 `boot.log` 에도 첫 프레임 줄이 없음 |
| **Windows 수신 확인** | **미확인.** 실행 중인 다른 Claude 세션이 없어(`ListAgents` 빈 목록) Windows 세션에 확인 요청을 보내지 못함 |
| 판정 | 재부팅 후 사람 손 없이 서비스와 카메라 연결 단계까지 올라옴(확인됨). CAN 송신·수신 정상 여부는 위 두 항목이 채워져야 확정 |

남은 확인: Windows 로거 로그에서 16:24:09 이후 첫 수신 시각과 Seq 0 리셋, 결번 0 여부 → 부팅→첫 프레임 시간 = (첫 수신 시각 − 16:23:51), 두 PC 시계 차이 1초 가정.

### Raw 켬 시험 (2026-10-12 16:30~16:47, 서비스 정지 후 직접 실행, traffic_light_v8n 6 SHAVE)
| 시험 | 결과 |
|---|---|
| 1차 15초 (수정 전) | 7프레임 후 정지(0.24 fps). 칩 Script(`EDGE_SCRIPT`)가 `TypeError: timedelta - lpb.Timestamp` 로 죽고 전 스트림 `X_LINK_ERROR` → 재연결. **링크 문제가 아니라 코드 문제** |
| 원인 | Raw 켬(`SpatialDetectionNetwork`)에서는 칩 Script 의 `getTimestampDevice()` 가 timedelta 가 아니라 `lpb.Timestamp`(sec·nsec) |
| 수정 | `EDGE_SCRIPT` 가 `total_seconds()` 를 먼저 시도, 안 되면 `sec + nsec*1e-9`. 둘 다 안 되면 죽지 않고 필드 목록을 경고로 1회 출력. `can_demo.py`·`can_demo_no_comments.py` (푸시됨 `55c9737`) |
| 2차 15초 (수정 후) | 78프레임, 5.08 fps, dropped 0, 칩 지연 122.7 ms, pc 6.0 ms, can_tx_errors 0 |

#### 30초 2회 (Windows 로거 수신 대조, 클래식 500 kbps)
| 항목 | `_b` (`--edge-wait` 0) | `_c` (`--edge-wait` 0.25) |
|---|---|---|
| 데이터 프레임 | 153 (seq 0~152) | 153 (seq 0~152) |
| 송신 = 수신 | 1154 = 1154 | 1132 = 1132 |
| 결번 · `can_lost_frames` · 에러 프레임 | 0 · 0 · 0 | 0 · 0 · 0 |
| `seconds` / `fps_avg` | 52.7 / 2.9 (종료 때 장치 닫기 약 12초 섞임) | 30.3 / 5.05 |
| 칩 지연(0 아닌 값 중앙값) · pc_ms | 122 · 6.0 ms | 122 · 5.5 ms |
| **EdgeMs=0 (값 없음)** | **58/153 = 37.9%** | **0/153 = 0%** |
| 간격 중앙값 | 199.94 ms | 199.96 ms |
| 간격 표준편차(시작 직후 3개 제외) | 1.12 ms (범위 197.4~202.7) | 8.94 ms (범위 178.8~221.5) |
| 0x320 PERF 개수 | 52 (프레임 끝난 뒤 22개 더) | 30 (깨끗한 종료) |
| 그 밖 ID | 0x340~344 각 153, 0x350~353 각 31, 0x360~362 각 3, 0x370 51 (두 run 동일), 0x310·0x330·0x331 = 0(검출 0개) | 동일 |
| 두 PC 시계 | +0.067 초 | +0.04 초 (NTP 동기 여부 미확인) |

- `can_tx_frames` 22개 차이는 PERF(0x320) 개수 차이뿐(`_b` 는 프레임 끝난 뒤 PERF 타이머가 22초 더 송신).
- **트레이드오프:** `--edge-wait 0.25` 는 EdgeMs 값 없음을 없애지만 송신 간격이 ±20 ms 흔들린다. 기본값은 사용자 결정 대기(제안: 기본 0, 지연값이 필요한 Raw 켬에서만 0.25).
- Raw 켬 칩 지연은 Raw 끔(80 ms)보다 약 42 ms 큼(깊이 계산). 목표 100 ms 이하는 넘음. CAN 부하 약 1.0%(MEASURE.md 기대 3~4% 보다 낮음). 이더넷 약 4.3 MB/s(Raw 끔 약 9 KB/s).
- `_b` 종료 중 `ping was missed … Device crashed` 경고 1회(프레임 송신 구간 밖). `_c` 에서는 없음. 원인 미확인.
- 한계: 30초 2회 표본. 60초×3모델·5분 측정은 미실시. YOLO11s 6 SHAVE 변환본은 아직 이 PC 에 없음.
- 로그: Windows `can_logs\20261012_raw_on_30s_b·_c\canoe.asc`, 송신 기록 `can_canoe/runs/20261012_raw_on_30s_b·_c/`(git 제외).

## 1번 재시도 — 카메라 단독(v2 플래시 standalone) 원인 분석 (2026-10-12 17:00~22:08, Ubuntu 카메라 PC)
**최종 판정: 된다.** 원인 2개를 고치자 전원만으로 PC 없이 앱이 시작해 UDP 가 5.03/s 로 온다. 시험 전 서비스(`oakd-autostart`)는 켜져 있었고(이전 v2 플래시 시험 때는 서비스가 설치되기 전), 사용자 sudo 로 정지한 뒤 진행했다(disable 안 함).

### 관측 수단
`retry/observe.py` — 1초마다 ping · `DeviceBootloader/Device.getAllAvailableDevices()` 상태 · UDP 5005 수신 개수를 시각과 함께 기록. 앱이 뜨면 상태가 `X_LINK_BOOTLOADER` → `X_LINK_FLASH_BOOTED`. (`tcpdump` 는 sudo 가 필요해 쓰지 않음.) 링크 변화는 `/sys/class/net/enp6s0/carrier` 를 0.2초 간격으로 기록.
플래시 전 상태: 앱 없음(`hasApplication=False`), 부트로더 0.0.28 NETWORK, 설정 `appMem=0`, DHCP(링크로컬 fallback), `network.timeoutMs=30000`.

### 가설별 시험
| 가설 | 시도 | 바꾼 것 | 관측 | 결론 |
|---|---|---|---|---|
| D 플래시 포맷 | step 1: `ColorCamera → XLinkOut`(Script 없음) 플래시 | 최소 파이프라인 | 플래시 100%. 부트로더 상태에서 약 60초 뒤 재부팅 → **`X_LINK_FLASH_BOOTED` 유지** | **기각.** v2.33 플래시 포맷을 부트로더 0.0.28 이 읽고 앱을 시작함 (B·D 해소) |
| A Script 가 죽음 | step 2: Script 만(UDP "hello"), 기본 프로세서 | 기본(LEON_MSS) | `FLASH_BOOTED` 에 잠깐 들어갔다 약 4초 뒤 `X_LINK_BOOTLOADER` 로 복귀, 이후 약 64초 주기로 반복, UDP 0 | 앱은 시작하지만 Script 가 죽어 부트로더로 돌아옴 |
| A 원인 | step 2b: Script 에서 socket 을 빼고 `node.warn` 만 | socket 제거 | `FLASH_BOOTED` 유지 | **socket 이 원인** |
| A 원인 | `retry/probe_modules.py`(호스트 모드)로 import 가능 모듈 조사 | `setProcessor` 기본 | `socket`·`_socket`·`select`·`http`·`urllib` 모두 `No module named` (json·time·struct·os·errno 만 있음) | 기본 프로세서(LEON_MSS)에는 socket 이 없음 |
| A 수정 ① | 같은 조사, `setProcessor(LEON_CSS)` | LEON_CSS | `socket`·`_socket`·`select`·`http`·`urllib` OK (`ssl`·`ipaddress` 없음) | **socket 은 LEON_CSS 에서만 import 된다** (Luxonis 문서: [Script node](https://docs.luxonis.com/software/depthai-components/nodes/script/)) |
| A 수정 ① 확인 | `retry/probe_hello.py`(호스트 모드) | LEON_CSS | UDP "hello" 5개 중 4개 수신(첫 패킷은 이쪽 수신 준비 전 손실로 보임) | 호스트 모드에서 UDP 송신 확인 |
| A 수정 ① 만 적용 | step 2 를 LEON_CSS 로 플래시 | LEON_CSS | 여전히 `BOOTLOADER` 로 약 64초 주기 반복, UDP 0 | **이것만으로는 부족.** 앱이 시작 직후 죽음 |
| A 수정 ② | step 2 Script 에 `try/except` + 소켓 재생성 추가 | 예외 처리 | **UDP 수신 시작(최종 62개/130초 관측, FLASH_BOOTED 유지)** | **전원 직후 네트워크가 아직 안 올라와 첫 `sendto` 가 예외를 내고, 예외가 나면 Script·앱이 같이 죽어 부트로더로 돌아간 것.** 재시도로 해결 |
| 전체 | 카메라 + `YoloDetectionNetwork` + Script(LEON_CSS, try/except) 플래시 | `build_pipeline_v2.py` 수정 | 부트로더 up 17:37:49 → 앱 시작 → **첫 UDP 17:38:50(약 61초)**, 이후 313패킷 | 6 SHAVE 가 아닌 **8 SHAVE 블롭(`traffic_light_v8n-416x416.blob`, 2클래스)** 으로 동작 |
| 칩 지연 | `Clock.now() - det.getTimestampDevice()` | 호스트 모드 조사(`probe_clock.py`) | `AttributeError: 'lpb.ImgDetections' object has no attribute 'getTimestampDevice'` → lat_ms=-1 로 나옴 | v2 Script 의 검출 메시지에는 `getTimestamp()` 만 있다. `Clock.now() - det.getTimestamp()` 로 수정 |

### 수정한 코드 (`build_pipeline_v2.py`, 변경 이유는 파일 주석에도 있음)
1. `script.setProcessor(dai.ProcessorType.LEON_CSS)` — socket 은 LEON_CSS 에서만 있음.
2. `SCRIPT`: `sendto` 를 `try/except` 로 감싸고 실패하면 소켓을 다시 만들어 재시도(예외가 앱을 죽이지 않게).
3. 칩 지연: `Clock.now() - det.getTimestamp()`, 실패하면 -1.
새 보조 파일 `retry/`: `observe.py`(관측기), `min_flash.py`(단계별 최소 파이프라인 step 1/2/2b), `probe_modules.py`·`probe_hello.py`·`probe_clock.py`(호스트 모드 조사). `flash_v2.py`·`clear_v2.py`·`listen_udp.py` 는 수정 없음. 사용한 플래시 명령: `flash_v2.py --blob traffic_light/04_blob/traffic_light_v8n-416x416.blob --dest-ip 169.254.1.10 --classes 2` (기본 `--classes 4` 는 이 모델에 맞지 않음).

### 판정 항목 측정 (traffic_light_v8n 8 SHAVE, 5 fps, 목적지 169.254.1.10:5005)
| 항목 | 결과 |
|---|---|
| ① PC 연결 없이 시작 | **예.** 카메라는 PoE 전원만으로 앱을 시작했다(호스트가 연결하지 않음) |
| ② 전원 인가 → 첫 UDP | PoE 를 뽑았다 꽂은 시험(22:04): 링크 Up 22:04:39.8 → 부트로더 22:04:40 → 30초 뒤(22:05:11) 앱으로 재부팅 → **첫 UDP 22:05:19. 전원 인가(링크 Up)에서 약 39초.** 플래시 직후 첫 시험들은 부트로더 up 에서 약 61초 |
| 패킷 주기 | **5.03/s** (151개/30초, 5 fps 와 일치) |
| 칩 지연 | 중앙 **79.7 ms** (`Clock.now() - det.getTimestamp()`) |
| 검출 | 0개 (장면에 신호등이 없었음). **v2 `YoloDetectionNetwork` 가 YOLOv8 블롭을 `setAnchors([])` 로 해석하는지는 검출이 없어 확정 못 함** (파이프라인은 오류 없이 동작) |
| IR LED | 확인 못 함(카메라를 보지 않음, 사용자 육안 확인 필요) |
| ④ 깊이·여러 모델 | 시험 안 함 |
| CAN 게이트웨이(`udp_to_can_gateway.py`, Kvaser, 500 kbps) | 20초 동안 UDP 101패킷 → CAN 101프레임 송신(FRAME_STATUS, 검출 0개라 DET_BOX 없음). **Windows 수신은 미확인** — Windows 세션이 오프라인이어서 로거 연결을 못 함 |
| 부팅 시간 주의 | 부트로더가 `timeoutMs=30000` 인데 앱 시작은 부트로더 up 후 약 30~60초. 두 시험(39초/61초)이 다른 것은 첫 시험이 플래시 직후라 부트로더를 먼저 거친 시간이 섞였을 수 있음(미확정, 표본 각 1회) |

### "아직 모르는 것" 4가지 답
| 질문 | 답 |
|---|---|
| v2 `YoloDetectionNetwork` 가 YOLOv8 블롭을 `setAnchors([])` 로 해석하는가 | 파이프라인은 시작·동작함. **출력이 맞는지는 검출이 0개여서 확정 못 함** (신호등이 보이는 장면에서 `listen_udp.py` 로 확인 필요) |
| 부트로더 0.0.28 에서 v2 플래시가 되는가 | **됨.** 최소 파이프라인(step 1)부터 전체까지 모두 100% 완료·앱 시작 |
| standalone 에서 `socket` UDP 송신이 되는가 | **된다.** 단 `LEON_CSS` 프로세서와 `try/except` 재시도가 필수 |
| 다중작업 모델 해석 | 시험 안 함 |

### 원복
`clear_v2.py` → `지움: True`. 재부팅 후 v3 연결 OK (OAK-D-PRO-POE, 부트로더 0.0.28). 서비스는 사용자가 다시 켜기로 함. 부트로더 업데이트·플래시는 하지 않았다.

### 남은 것
Windows 에서 게이트웨이 CAN 수신 대조(30초, 세션 연결 후) · 신호등이 보이는 장면에서 검출 확인 · IR LED 육안 확인 · 깊이·다중 모델(8 SHAVE 블롭 + 깊이 시 SHAVE 부족 주의) · 부팅→첫 UDP 시간 반복 측정.

### 단독 앱 → 게이트웨이 → CAN → Windows 수신 대조 (2026-10-12 23:19, 30초)
카메라 단독 앱(UDP 5 fps) → `udp_to_can_gateway.py --interface kvaser --channel 0 --bitrate 500000 --model traffic_light_v8n --seconds 30` → Windows 로거(VN1630A, 클래식 500 kbps).
| 항목 | 결과 |
|---|---|
| 송신 = 수신 | CAN **151 = 151** (전부 0x300 FRAME_STATUS, 0x310·0x320·추가 메시지 0, 에러 프레임 0) |
| 결번 | Seq 540~690 연속 151개, seq_missing 0, can_lost_frames 0. Seq 는 게이트웨이가 카메라 앱의 프레임 번호를 그대로 쓴 값(0 이 아니라 540 에서 시작) |
| 모델·Raw | ModelId 4(traffic_light_v8n) 정상, RawOn 0 |
| 시각 | 첫 프레임 23:19:44.199(Windows) vs 송신 23:19:44.14 → +0.06 초(앞선 시험의 +0.067 초와 일관, NTP 동기 여부 미확인) |
| 간격 | 중앙 199.97 ms, 최소 197.8, 최대 202.3, 표준편차 0.59 ms (시작 직후 3개 제외 0.60). `can_demo` 에서 보이던 시작 직후 프레임 몰림(12·52·93 ms)이 없음 → 카메라 앱의 5 fps 가 거의 그대로 CAN 에 반영 |
| CAN 부하 | 0.13% |
| EdgeMs | 151프레임 전부 80. **고정값이 아님:** UDP 의 `lat_ms` 를 40패킷 샘플링하면 79.5~79.8(중앙 79.7)로 매우 안정적이고, DBC 의 EdgeMs 분해능이 1 ms 라 반올림되어 80 이 된 것 |
| Fps 필드 | 0.0 — 게이트웨이가 `frame_status(…, fps=0, …)` 로 채우지 않음(미구현) |
| 검출 | 0개(장면에 신호등 없음) → DET_BOX 는 시험 못 함 |
