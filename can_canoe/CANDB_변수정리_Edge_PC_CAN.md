# 영상 송출 데이터 정리: Edge → PC → CAN (CANdb 구성용)

작성: 2026-10-13 (맥 세션). 대상: CAM01(전방 중앙), A-YOLOM(n) 변형 L1(검출 p3·p4 + 차선 출력), 영상 송출 상태(조건 A·D).
범위 규칙(사용자 지시): **깊이(depth) 관련과 차선은 CANdb 구성에서 제외.**

> 정식 CANdb 문서는 카메라 PC가 `CANDB_영상송출_분석.md`로 작성 중이다. 이 문서는 설계 논리와 변수 정리의 맥 쪽 사본이며, 카메라 PC 로컬 코드(미커밋)와 다를 수 있어 최종 확정 전에 대조가 필요하다.

## 1. 전체 흐름

```
[Edge: OAK-D 칩] --이더넷(영상·AI 원시 출력·상태)--> [카메라 PC] --CAN 500 kbps(숫자)--> [Windows PC / CANoe]
 촬영, 신경망 연산                                      후처리(DFL 해석, NMS), 변환                Vector 수신, 로깅
```

- 영상 원본(RGB 프레임, 마스크)은 CAN으로 보내지 않는다. 512×288 1채널만 프레임당 147 KB, 5 fps에서 737 KB/s인데 클래식 CAN 500 kbps의 실효 데이터량은 약 30 KB/s라서 약 25배 초과한다(계산).
- CAN에는 영상에서 뽑아낸 숫자만 보낸다.

### "영상에서 뽑아낸 숫자" 4종
| 종류 | 의미 | 메시지 |
|---|---|---|
| ① AI 검출 결과 | 영상 안에 무엇이 어디 있는가 | `FRAME_STATUS`(검출 수), `DET_BOX` |
| ② 촬영 정보 | 노출, ISO, 색온도, 렌즈, 해상도, 화각 | `FRAME_META_A/B/C`, `CALIB_A` |
| ③ 처리 성능 | 촬영~결과 지연, fps, 누락 | `FRAME_STATUS`, `PERF`, `FRAME_TIME_DEV/HOST` |
| ④ 장치 상태 | 칩 온도, CPU, 메모리 | `DEV_TEMP`, `DEV_MEM_*` |

`DET_BOX` 인코딩 예(예시, 실측 아님): car, Conf 0.87, 중심 0.52/0.61, 크기 0.12/0.09 → 512×288 화면에서 중심 (266, 176) px, 크기 61×26 px. 박스 하나가 CAN 프레임 하나(8바이트)이며, 박스가 3개면 3프레임과 `DetCount`=3이 나간다.

## 2. Edge → PC (이더넷)
| 변수 | 형식·크기 | 의미 | 주기 |
|---|---|---|---|
| 영상 프레임(ImgFrame) | 512×288 BGR, 442,368 B | 카메라 영상 | 프레임마다(5 fps → 200 ms) |
| `det_p3` | (1,69,36,64) FP16, 317,952 B | 큰 격자 검출 출력(박스 DFL 64 + 클래스 5) | 프레임마다 |
| `det_p4` | (1,69,18,32) FP16, 79,488 B | 중간 격자 검출 출력 | 프레임마다 |
| `lane` | (1,2,288,512) FP16, 589,824 B | 픽셀별 차선 2클래스 logit | 프레임마다 |
| 프레임 메타 | `exposure_us`, `iso`, `color_temp_k`, `lens_pos`, `source_w/h`, `cam_instance`, `frame_type`, `frame_w/h`, `hfov_deg`, `vfov_deg`, `ts_device_us` | 촬영 정보, 장치 시각 | 프레임마다 |
| 호스트 계산 | `ts_host_us`, `det_latency_ms`, `frame_latency_ms` | 호스트 수신 시각, 지연 | 프레임마다 |
| 칩 상태(`telemetry_row`) | `temp_css/mss/upa/dss/avg`, `cpu_css/mss_pct`, `ddr_used/total_mb`, `cmx_used/total_kb`, `css/mss_heap_used/total_kb` | 칩 온도, CPU, 메모리 | 1초 |
| 세션 정보(`session_info`) | `fx`, `fy`, `cx`, `cy`, `nn_w/h`, `camera_mask`, `n_classes`, `conf_threshold`, 장치 ID·제품명 등 | 보정, 설정, 장치 정보 | 시작 시 한 번 |

- 합계는 L1 기준 약 1.4 MB/프레임, 약 7 MB/s로 추정(계산). 원본 ft1은 `det_p5`와 `drivable`까지 있어 약 2.0 MB/프레임.
- 실측(원본 ft1): 영상을 안 받는 Raw 끔 이더넷 약 8.6 MB/s, Raw 켬(영상 포함) 약 10~11 MB/s. 차이 약 2~3 MB/s는 RGB 영상 약 2.2 MB/s와 맞는다. 따라서 영상이 없어도 신경망 원시 출력은 항상 이더넷으로 온다.
- 제외: 깊이 프레임, 깊이로 계산한 X/Y/Z, `baseline_cm`, `depth_lo/hi_mm`, `spatial`.
- 차선 원시 출력은 CAN으로 가지 않고, Raw 켬에서 PC 로그(`raw_ai_seg.csv`)에만 남는다.

## 3. PC 처리 (Edge → CAN 사이)
| 처리 | 입력 → 출력 |
|---|---|
| 검출 후처리 | `det_p3/p4` → DFL 디코딩, sigmoid, 문턱 0.25, NMS → 박스 |
| 단위 변환 | 박스 0~1 정규화, 신뢰도 % |
| 시간 계산 | `EdgeMs`(칩), `PostMs`(PC, 측정 약 3~4 ms), 프레임 지연, `SeqGap` |
| 부하 계산 | `EthKBps`, `CanLoadPct`, 누락 누적 |
| 후보 로깅 | Raw 켬일 때만 문턱 이전 후보 전체와 클래스별 점수를 `raw_ai_candidates.csv`에 저장 |

## 4. PC → CAN (16개 메시지, 변수 73개)
### 프레임 결과 (프레임마다, 200 ms)
| 메시지 (ID) | 변수 | 비트 | 시작~끝 byte | 의미 |
|---|---|---|---|---|
| `FRAME_STATUS` 0x300 | `Seq` | 16 | 0~1 | 프레임 순번 |
| | `DetCount` | 8 | 2 | 검출 수 |
| | `Fps` | 16 (×0.1) | 3~4 | 수신 fps |
| | `EdgeMs` | 12 | 5~6 | 칩 지연(ms) |
| | `SeqGap` | 4 | 6 | 건너뛴 순번(누락) |
| | `ModelId` | 4 | 7 | 모델 번호 |
| | `RawOn` | 1 | 7 | Raw 켬 여부 |
| `DET_BOX` 0x310 (검출마다) | `SeqLo` | 4 | 0 | 순번 하위 4비트 |
| | `Index` | 4 | 0 | 박스 번호 |
| | `Label` | 7 | 1 | 클래스 |
| | `Conf` | 7 (×0.01) | 1~2 | 신뢰도 |
| | `Cx`, `Cy`, `W`, `H` | 10×4 (×0.001) | 2~3, 4~5, 5~6, 6~7 | 박스 중심과 크기(정규화) |

### 프레임 메타·시간 (Raw 켬, 프레임마다 200 ms)
| 메시지 (ID) | 변수(비트) | 의미 |
|---|---|---|
| `FRAME_META_A` 0x340 | `Seq`(16), `ExposureUs`(20), `Iso`(12), `ColorTempK`(14) | 노출(µs), ISO, 색온도(K) |
| `FRAME_META_B` 0x341 | `Seq`(16), `LensPos`(10, 부호 있음), `SourceW`(13), `SourceH`(13), `CamInstance`(4), `FrameType`(8) | 렌즈 위치, 원본 크기, 카메라 번호, 프레임 형식 |
| `FRAME_META_C` 0x342 | `Seq`(16), `FrameW`(13), `FrameH`(13), `HfovDeg`(11, ×0.1), `VfovDeg`(11, ×0.1) | 출력 크기, 화각 |
| `FRAME_TIME_DEV` 0x343 | `Seq`(16), `TsDeviceUs`(32), `DetLatencyMs`(16, ×0.1) | 장치 시각, 검출 지연 |
| `FRAME_TIME_HOST` 0x344 | `Seq`(16), `TsHostUs`(32), `FrameLatencyMs`(16, ×0.1) | 호스트 시각, 프레임 지연 |

### 1초 주기
| 메시지 (ID) | 변수(비트) | 의미 |
|---|---|---|
| `PERF` 0x320 | `PcMs`(12, ×0.1), `PostMs`(12, ×0.1), `EthKBps`(16), `CanLoadPct`(8, ×0.5), `DroppedTotal`(16) | PC 처리 시간, 후처리 시간, 이더넷 사용량, CAN 부하, 누락 누적 |
| `DEV_TEMP` 0x350 (Raw 켬) | `TempCss/Mss/Upa/Dss/Avg`(8×5, ×0.5 −40), `CpuCssPct`, `CpuMssPct`(8, ×0.5) | 칩 온도, CPU |
| `DEV_MEM_A` 0x351 | `DdrUsedMB`, `DdrTotalMB`, `CmxUsedKB`, `CmxTotalKB`(16×4, ×0.1) | DDR·CMX 메모리 |
| `DEV_MEM_B` 0x352 | `CssHeapUsedKB`, `CssHeapTotalKB`(32×2) | CSS 힙 |
| `DEV_MEM_C` 0x353 | `MssHeapUsedKB`, `MssHeapTotalKB`(32×2) | MSS 힙 |

### 10초 주기 (Raw 켬, 정적)
| 메시지 (ID) | 변수(비트) | 의미 |
|---|---|---|
| `CALIB_A` 0x360 | `Fx`, `Fy`, `Cx`, `Cy`(16×4, ×0.1 px) | RGB 초점거리, 주점 |
| `CALIB_B` 0x361 | `NClasses`(8), `ConfThresholdPct`(8) | 클래스 수, 문턱(%) |
| `CALIB_C` 0x362 | `NnInputW`(16), `NnInputH`(16), `CameraMask`(8) | 신경망 입력 크기, 카메라 구성 |
| `DEV_INFO` 0x370 | `StrId`(4), `Chunk`(4), `TotalLen`(8), `C0`~`C4`(8×5) | 장치·모델 문자열(5글자씩 분할) |

(메시지 ID는 DBC의 10진수 값을 16진수로 바꾼 것. 시작·끝 byte는 Intel 정렬, byte 번호 0부터. `FRAME_STATUS`, `DET_BOX` 외 byte 열은 카메라 PC 문서에서 채운다.)

## 5. 구성 근거
1. **메시지는 8바이트 한 프레임 단위**: 클래식 CAN 한 프레임 한도. 의미가 같은 변수끼리 묶고 넘치면 `_A/_B/_C`로 나눠 필요한 것만 받을 수 있게 했다.
2. **박스 하나 = 메시지 하나**: 검출 수가 가변이라 `Index`로 구분하고 `DetCount`로 개수를 알린다.
3. **좌표 정규화(×0.001)**: 입력 해상도(512, 640)가 바뀌어도 변수 정의가 그대로. 512 px 입력에서 약 0.5 px 단위로 모델 정밀도보다 촘촘하다.
4. **물리 단위와 배율은 값의 의미 단위로**: 온도 0.5도 단위, 신뢰도 1%, 지연 0.1 ms.
5. **`Seq`로 메시지 연결과 누락 검출**: `SeqLo`(4비트)는 16프레임 넘게 유실되면 모호해진다. `SeqGap`, `DroppedTotal`로 누락을 숫자로 확인.
6. **ID는 기능별 묶음**: 0x30x 상태, 0x31x 검출, 0x34x 메타, 0x35x 진단, 0x36x 보정, 0x37x 정보. CANoe 필터링이 쉽다.

## 6. 업데이트 주기와 수신 주기
- 송신 코드(`can_demo.py`)는 이벤트(프레임) 단위, 1초, 10초로 보낸다. 50 ms마다 반복 송신하는 코드는 없다.
- 교수님 요청의 "수신 50 ms"를 CANoe 수신 샘플링·타임아웃 감시 기준으로 쓸지 정해야 한다. DBC의 `GenMsgCycleTime`과 어긋나는지 카메라 PC가 확인 중.
- 5 fps에서 새 값은 200 ms마다 오므로 50 ms 칸 4개 중 3개는 새 값이 없다. 수신 측은 `Seq`가 바뀌었는지로 새 값과 반복 값을 구분한다.
- `PERF`는 프레임이 아니라 첫 프레임 기준 k초 + 50 ms의 1초 간격이다.

## 7. 버스 부하 (계산, 실측 대기)
- 프레임당 최악 135비트 가정. 박스 10개 기준 Raw 끔 약 12프레임/주기, Raw 켬 약 24프레임/주기.
- 5 fps에서 약 8~16 kbps(500 kbps의 약 1.6~3.2%). 5분 본 측정의 Windows 로그와 `CanLoadPct`로 대조한다.

## 8. 검증 상태
| 항목 | 상태 |
|---|---|
| DBC 신호 정의와 인코딩 | 코드와 selftest로 확인 |
| 이더넷 크기 합계 | 출력 shape에서 계산, 조건별 `EthKBps` 실측 대기 |
| 버스 부하 | 계산만 함 |
| 송신 주기(이벤트, 1초, 10초) | 맥 저장소 `can_demo.py` 설명 기준, 카메라 PC 로컬 코드와 대조 필요 |
| `CamInstance`, `FrameType`, `CameraMask`가 깊이를 가리키는지 | 확인 중 |

## 9. 변수가 정의된 파일 (`can_canoe/`)
| 역할 | 파일 |
|---|---|
| CAN 변수 정의(이름, 비트, 배율, 단위) | `oakd_canoe.dbc`, `oakd_canoe_fd.dbc` |
| 메시지 만드는 함수, 모델 ID 표 | `can_msgs.py` |
| Edge 값 추출과 추가 메시지 생성 | `oak_full.py` (`frame_meta`, `telemetry_row`, `session_info`, `frame_messages`, `telemetry_messages`, `session_messages`) |
| 송신 시점과 주기, 메인 루프 | `can_demo.py` |
| 수신 로그를 CSV로 푸는 쪽 | `extra_messages.py`, `canoe_logger.py` |
| 변수표 엑셀 | `dbc_to_excel.py`, `oakd_송출데이터_정리.xlsx` |
| 카메라 PC 로컬(맥 저장소에 없음) | `a_yolom/`(`a_yolom_source.py`, `postprocess*.py`, `raw_ai.py`), `can_demo.py`의 `--video`, `--model a_yolom_n`, `CANDB_영상송출_분석.md` |
