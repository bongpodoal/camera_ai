# CANdb 분석: 영상에서 뽑아낸 숫자의 CAN 송신 (A-YOLOM(n), 영상 송출 상태)

> 이 문서는 `can_canoe/make_candb_doc.py` 가 `oakd_canoe.dbc` 에서 변수 표를 자동 생성한다. 같은 내용의 엑셀은 `dbc_to_excel.py`(`oakd_송출데이터_정리.xlsx`).
> 표기: **[실측]** = 이 PC 의 로그·측정으로 확인, **[계산]** = DBC·설정값으로 계산, **[미검증]** = 아직 확인 못 함.
> **범위(사용자 지시)**: 깊이 관련 값(DET_POS·DET_ROI 전체, CALIB_B 의 BaselineCm·DepthLoMm·DepthHiMm, CALIB_C 의 SpatialOn)과 차선·주행영역 요약(SEG_SUMMARY 전체)·LANE_POLY 는 이 문서의 CANdb 구성에서 **제외**했다. DBC·송신 코드에는 남아 있으므로 실측 CAN 부하(`can_tx_load_pct`)에는 포함되어 있다. 이 문서의 구성은 변수 73개 / 메시지 16개.

## 1. 영상은 왜 이더넷이고, CAN 에는 무엇을 싣는가

- 영상 원본(RGB·마스크)은 CAN 에 실을 수 없다. 512×288 **1채널**(흑백 영상·마스크 한 장) = 147,456 byte ≈ 147 KB, 5 fps 면 **737 KB/s**. 클래식 CAN 500 kbps 의 실효 전송량은 프레임당 8바이트 데이터 / 135비트(최악 비트 스터핑) 기준 약 **30 KB/s** 이므로 영상이 **약 25배** 많다 **[계산]**. RGB(3채널) 한 장은 442,368 byte 로 클래식 CAN 8바이트 프레임 55,296개 → 한 장에 약 15 초(5 fps 불가) **[계산]**.
- 그래서 **영상(RGB·마스크)은 이더넷(PoE)** 으로 PC 가 받고, **CAN 에는 영상에서 뽑아낸 숫자만** 싣는다. 신경망 원시 출력(마스크 logit 포함, 프레임당 약 1.6 MB FP16)도 호스트 디코딩에 필요해 모든 조건에서 이더넷으로 온다 **[실측 근거: Raw 끔 5 fps 에서 NIC 수신 8.57 MB/s]**.

| 조건 | Raw 데이터 | 영상 송출 | CAN 으로 나가는 것(이 문서 범위) | 이더넷으로 오는 것 |
|---|---|---|---|---|
| A | 켬 | 켬 | 전부 (아래 4종) | RGB 프레임 + 신경망 원시 출력 |
| B | 끔 | 끔 | AI 검출 결과 + PERF(처리 성능)만 | 신경망 원시 출력 |
| C | 켬 | 끔 | A 와 같음 | 신경망 원시 출력 |
| D | 끔 | 켬 | B 와 같음 | RGB 프레임 + 신경망 원시 출력 |

- **Raw 데이터** = 숫자로 CAN 에 싣는 값 전부(아래 4종 중 AI 검출 결과 외 항목 + 카메라 PC 의 AI 결과 기록 `raw_ai_*.csv`). 영상 송출과 독립으로 켜고 끈다(`--video on|off`).

## 2. "영상에서 뽑아낸 숫자" 4종과 CAN 메시지

| 종류 | 의미 | CAN 메시지(ID) | 모드 |
|---|---|---|---|
| AI 검출 결과 | 신경망이 영상에서 찾은 객체: 프레임 요약(개수·Seq·지연·fps) + 검출마다 클래스·신뢰도·박스 | FRAME_STATUS(0x300) · DET_BOX(0x310) | Raw 끔+켬 |
| 프레임 촬영 메타 | 그 프레임을 찍을 때의 카메라 설정: 노출·ISO·색온도·렌즈·센서/처리 크기·화각 | FRAME_META_A/B/C(0x340~0x342) | Raw 켬 |
| 처리 성능·지연 | 카메라→칩→PC 의 처리 속도와 지연, 촬영 시각(카메라 시계·호스트 시계) | PERF(0x320) · FRAME_TIME_DEV/HOST(0x343·0x344) (+ FRAME_STATUS 의 Fps·EdgeMs) | PERF 는 Raw 끔+켬, 나머지 Raw 켬 |
| 장치 상태 | 칩 온도·CPU·메모리(1초), 카메라 보정·신경망 설정(10초), 장치 ID·제품명·펌웨어(10초, 문자열) | DEV_TEMP·DEV_MEM_A/B/C(0x350~0x353) · CALIB_A/B/C(0x360~0x362) · DEV_INFO(0x370) | Raw 켬 |

**CamInstance·FrameType·CameraMask 가 깊이를 가리키는 값인가?** 아니다(확인함, `oak_full.py`): `CamInstance` = 신경망이 처리한 **RGB 프레임**을 찍은 카메라 소켓(CAM_A = 0), `FrameType` = 그 프레임의 픽셀 형식 코드(ImgFrame type, 예 BGR888p). `CameraMask` = 연결된 카메라 소켓 비트마스크(bit0 = CAM_A, bit1 = CAM_B, bit2 = CAM_C)로 **장치 구성 정보**이며 깊이 값이 아니다 (CAM_B·CAM_C 비트가 켜져 있다는 것은 흑백 스테레오 카메라가 달려 있다는 뜻일 뿐). 그래서 문서 범위에 남겼다. 지우려면 사용자 지시가 필요하다.

## 3. 변수표 (3.1 Edge→PC 이더넷, 3.2 PC→CAN)

### 3.1 Edge→PC 데이터 변수표 (이더넷, 카메라 칩 → 카메라 PC)

카메라(OAK-D PoE)는 이더넷으로 PC 에 아래 데이터를 보낸다. 이 중 **CAN 으로 가는 것은 3.2 의 숫자뿐**이다.

**(a) 영상 프레임** (영상 송출 켬일 때만 이더넷으로 옴)

| 이름 | 형식 | 크기 | 1장 byte | 주기 | 정의 위치 |
|---|---|---|---|---|---|
| ImgFrame (신경망 passthrough, RGB) | uint8 BGR888p, 3×288×512 | 512×288 | 442,368 | 프레임마다 (200 ms) | a_yolom/a_yolom_source.py (frame_q), can_demo.py |

**(b) 신경망 출력** (모든 조건에서 이더넷으로 옴, 호스트 디코딩에 필요)

| 모델 | 출력 이름 | shape | dtype | 바이트/프레임 | 주기·대역폭 |
|---|---|---|---|---|---|
| 원본 ft1 | det_p3 | 1x69x36x64 | FP16(칩 출력) → 호스트 float32 | 317,952 | 프레임마다 |
| 원본 ft1 | det_p4 | 1x69x18x32 | FP16(칩 출력) → 호스트 float32 | 79,488 | 프레임마다 |
| 원본 ft1 | det_p5 | 1x69x9x16 | FP16(칩 출력) → 호스트 float32 | 19,872 | 프레임마다 |
| 원본 ft1 | drivable | 1x2x288x512 | FP16(칩 출력) → 호스트 float32 | 589,824 | 프레임마다 |
| 원본 ft1 | lane | 1x2x288x512 | FP16(칩 출력) → 호스트 float32 | 589,824 | 프레임마다 |
| 원본 ft1 | 합계/프레임 |  |  | 1,596,960 | 5 fps → 7.98 MB/s |
| L1_lane_nop5 (본 측정 모델) | det_p3 | 1x69x36x64 | FP16(칩 출력) → 호스트 float32 | 317,952 | 프레임마다 |
| L1_lane_nop5 (본 측정 모델) | det_p4 | 1x69x18x32 | FP16(칩 출력) → 호스트 float32 | 79,488 | 프레임마다 |
| L1_lane_nop5 (본 측정 모델) | lane | 1x2x288x512 | FP16(칩 출력) → 호스트 float32 | 589,824 | 프레임마다 |
| L1_lane_nop5 (본 측정 모델) | 합계/프레임 |  |  | 987,264 | 5 fps → 4.94 MB/s |

출력 이름은 `a_yolom/postprocess_variants*.py` 가 이름으로 꺼낸다(블롭 출력 순서는 바뀔 수 있음). det_p* 채널 = 64(박스 DFL logit 4변×16) + 5(클래스 logit). **[실측 근거]** Raw 끔 5 fps NIC 수신: 원본 8.57 MB/s(계산 8.0 MB/s), L1 5.39 MB/s(계산 4.9 MB/s, 이더넷 헤더·메타 포함).

**(c) 프레임 메타·텔레메트리·세션 정보** (Raw 켬. 영상 송출과 무관 — 프레임 메타는 칩 안 Script 가 JSON 으로 보내고 텔레메트리는 SystemLogger)

| 묶음 | 필드 | 출처(depthai API) | 주기 | 정의 위치 |
|---|---|---|---|---|
| frame_meta | exposure_us | ImgFrame.getExposureTime() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | iso | getSensitivity() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | color_temp_k | getColorTemperature() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | lens_pos | getLensPosition() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | source_w | getSourceWidth() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | source_h | getSourceHeight() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | cam_instance | getInstanceNum() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | frame_type | getType().value | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | frame_w | getWidth() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | frame_h | getHeight() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | hfov_deg | getSourceHFov() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | vfov_deg | getSourceVFov() | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | ts_device_us | getTimestampDevice() (μs) | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | ts_host_us | 신경망 결과 getTimestamp() (호스트 시계 동기, μs) | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | det_latency_ms | Clock.now() − 결과 촬영 시각 | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| frame_meta | frame_latency_ms | Clock.now() − 프레임 촬영 시각(영상 송출 끔이면 0) | 프레임마다 | oak_full.py frame_meta · a_yolom_source.py META_SCRIPT |
| telemetry_row | ts_device_s | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | temp_css | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | temp_mss | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | temp_upa | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | temp_dss | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | temp_avg | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | cpu_css_pct | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | cpu_mss_pct | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | ddr_used_mb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | ddr_total_mb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | cmx_used_kb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | cmx_total_kb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | css_heap_used_kb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | css_heap_total_kb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | mss_heap_used_kb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| telemetry_row | mss_heap_total_kb | SystemInformation (chipTemperature·leon CPU·DDR/CMX/LEON 힙) | 1초 | oak_full.py telemetry_row |
| session_info | nn_w | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | nn_h | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | model | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | depthai_version | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | fx | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | fy | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | cx | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | cy | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | device_id | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | product_name | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | platform | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | bootloader | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | cameras | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | camera_mask | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | n_classes | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |
| session_info | conf_threshold | 보정(CAM_A 내부 파라미터)·장치 정보·신경망 설정 | 시작 때 1번 읽음(CAN 으로는 10초 반복) | oak_full.py session_info |

깊이 관련 필드(깊이 하한·상한, 기선 길이, SpatialOn, 깊이 좌표)는 사용자 지시로 이 표에서 제외했다.

### 3.2 PC→CAN 변수표 (DBC 에서 자동 생성)

변수 73개 / 메시지 16개. **업데이트 주기**는 카메라 5 fps = **200 ms** 마다 새 값이 만들어지는 주기, **CAN 수신 주기(CANdb) 50 ms** 는 교수님이 지정한 수신 기준 열이다(두 값이 다른 이유는 5.3절). 시작/끝 byte 는 Intel(리틀엔디언) 기준 0 부터 센 값. **갱신 종류**: 프레임마다 / 검출마다(프레임당 최대 N=8개를 200 ms 마다 묶음) / 1초 / 10초 — can_demo.py 상단 설명의 실제 송신 시점. **GenMsgCycleTime 불일치**: DBC 에는 PERF=1000 ms 만 값이 있고 나머지는 기본값 0(주기 없음 = 이벤트 송신)이라 'CANdb 수신 주기 50 ms' 열(교수님 요청, 문서·엑셀 전용)과 **DBC 속성이 다르다** [DBC 확인].

| 메시지 | ID | 변수명 | 변수 의미 | 변수형 | 길이(bit) | 갱신 종류 | 업데이트 주기 | 필요한 모드 | 시작 byte | 끝 byte | CAN 수신 주기(CANdb) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FRAME_STATUS | 0x300 | Seq | 카메라 프레임 번호(65536 에서 돌아옴) | uint16 | 16 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 0 | 1 | 50 ms |
| FRAME_STATUS | 0x300 | DetCount | 이 프레임의 검출 개수 | uint8 | 8 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 2 | 2 | 50 ms |
| FRAME_STATUS | 0x300 | Fps | 칩 처리 속도(최근 1초) | uint16 → 실수 (×0.1) | 16 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 3 | 4 | 50 ms |
| FRAME_STATUS | 0x300 | EdgeMs | 칩 안 지연(촬영→검출 결과, 같은 칩 시계라 드리프트 없음). 0=값 없음 | uint12 | 12 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 5 | 6 | 50 ms |
| FRAME_STATUS | 0x300 | SeqGap | 직전 메시지 이후 건너뛴 프레임 수(최대 15) | uint4 | 4 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 6 | 6 | 50 ms |
| FRAME_STATUS | 0x300 | ModelId | 모델 번호(0 yolov6n,1 yolov8n,2 traffic_light,3 traffic_light_11n,4 traffic_light_v8n,5 a_yolom_n) | uint4 | 4 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 7 | 7 | 50 ms |
| FRAME_STATUS | 0x300 | RawOn | Raw 켬 여부(0 검출만, 1 영상 등 전부) | bool(1bit) | 1 | 프레임마다 | 200 ms (=5 fps) | Raw 끔+켬 | 7 | 7 | 50 ms |
| DET_BOX | 0x310 | SeqLo | 프레임 번호의 아래 4비트(FRAME_STATUS.Seq 와 연결) | uint4 | 4 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 0 | 0 | 50 ms |
| DET_BOX | 0x310 | Index | 검출 순번(0=신뢰도 최고) | uint4 | 4 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 0 | 0 | 50 ms |
| DET_BOX | 0x310 | Label | 클래스 번호 | uint7 | 7 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 1 | 1 | 50 ms |
| DET_BOX | 0x310 | Conf | 신뢰도 0~1(카메라 출력값, 정확도 아님) | uint7 → 실수 (×0.01) | 7 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 1 | 2 | 50 ms |
| DET_BOX | 0x310 | Cx | 박스 중심 X(0~1 정규화) | uint10 → 실수 (×0.001) | 10 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 2 | 3 | 50 ms |
| DET_BOX | 0x310 | Cy | 박스 중심 Y(0~1 정규화) | uint10 → 실수 (×0.001) | 10 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 4 | 5 | 50 ms |
| DET_BOX | 0x310 | W | 박스 너비(0~1) | uint10 → 실수 (×0.001) | 10 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 5 | 6 | 50 ms |
| DET_BOX | 0x310 | H | 박스 높이(0~1) | uint10 → 실수 (×0.001) | 10 | 검출마다 | 프레임마다 검출 개수만큼(프레임당 최대 N=8개), 200 ms 마다 한 프레임분을 묶어 송신 | Raw 끔+켬 | 6 | 7 | 50 ms |
| PERF | 0x320 | PcMs | PC 쪽 지연 중앙값(이더넷·큐·처리) | uint12 → 실수 (×0.1) | 12 | 1초 | 1000 ms | Raw 끔+켬 | 0 | 1 | 50 ms |
| PERF | 0x320 | PostMs | 영상에 박스 그리는 시간(Raw 끔이면 0) | uint12 → 실수 (×0.1) | 12 | 1초 | 1000 ms | Raw 끔+켬 | 1 | 2 | 50 ms |
| PERF | 0x320 | EthKBps | 카메라→PC 이더넷 수신량(KB/s) | uint16 | 16 | 1초 | 1000 ms | Raw 끔+켬 | 3 | 4 | 50 ms |
| PERF | 0x320 | CanLoadPct | CAN 버스 부하 추정(최악 비트 스터핑) | uint8 → 실수 (×0.5) | 8 | 1초 | 1000 ms | Raw 끔+켬 | 5 | 5 | 50 ms |
| PERF | 0x320 | DroppedTotal | 입력 큐에서 버려진 프레임 누적 | uint16 | 16 | 1초 | 1000 ms | Raw 끔+켬 | 6 | 7 | 50 ms |
| FRAME_META_A | 0x340 | Seq | 카메라 프레임 번호(65536 에서 돌아옴) | uint16 | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| FRAME_META_A | 0x340 | ExposureUs | 노출 시간 | uint20 | 20 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 2 | 4 | 50 ms |
| FRAME_META_A | 0x340 | Iso | ISO 감도 | uint12 | 12 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 4 | 5 | 50 ms |
| FRAME_META_A | 0x340 | ColorTempK | 색온도 | uint14 | 14 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 6 | 7 | 50 ms |
| FRAME_META_B | 0x341 | Seq | 카메라 프레임 번호(65536 에서 돌아옴) | uint16 | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| FRAME_META_B | 0x341 | LensPos | 렌즈 위치(-1=고정 초점) | int10 | 10 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 2 | 3 | 50 ms |
| FRAME_META_B | 0x341 | SourceW | 센서 영상 너비 | uint13 | 13 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 3 | 4 | 50 ms |
| FRAME_META_B | 0x341 | SourceH | 센서 영상 높이 | uint13 | 13 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 4 | 6 | 50 ms |
| FRAME_META_B | 0x341 | CamInstance | 카메라 소켓 번호 | uint4 | 4 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 6 | 6 | 50 ms |
| FRAME_META_B | 0x341 | FrameType | 영상 픽셀 형식 코드(ImgFrame type) | uint8 | 8 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 7 | 7 | 50 ms |
| FRAME_META_C | 0x342 | Seq | 카메라 프레임 번호(65536 에서 돌아옴) | uint16 | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| FRAME_META_C | 0x342 | FrameW | 신경망이 처리한 영상 너비 | uint13 | 13 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 2 | 3 | 50 ms |
| FRAME_META_C | 0x342 | FrameH | 신경망이 처리한 영상 높이 | uint13 | 13 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 3 | 5 | 50 ms |
| FRAME_META_C | 0x342 | HfovDeg | 수평 화각 | uint11 → 실수 (×0.1) | 11 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 5 | 6 | 50 ms |
| FRAME_META_C | 0x342 | VfovDeg | 수직 화각 | uint11 → 실수 (×0.1) | 11 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 6 | 7 | 50 ms |
| FRAME_TIME_DEV | 0x343 | Seq | 카메라 프레임 번호(65536 에서 돌아옴) | uint16 | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| FRAME_TIME_DEV | 0x343 | TsDeviceUs | 촬영 시각(카메라 시계, μs, 71.6분마다 돌아옴) | uint32 | 32 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 2 | 5 | 50 ms |
| FRAME_TIME_DEV | 0x343 | DetLatencyMs | 촬영→검출까지 지연 | uint16 → 실수 (×0.1) | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 6 | 7 | 50 ms |
| FRAME_TIME_HOST | 0x344 | Seq | 카메라 프레임 번호(65536 에서 돌아옴) | uint16 | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| FRAME_TIME_HOST | 0x344 | TsHostUs | 촬영 시각(호스트 시계로 동기, μs) | uint32 | 32 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 2 | 5 | 50 ms |
| FRAME_TIME_HOST | 0x344 | FrameLatencyMs | 촬영→프레임 수신까지 지연 | uint16 → 실수 (×0.1) | 16 | 프레임마다 | 200 ms (Raw 켬) | Raw 켬 | 6 | 7 | 50 ms |
| DEV_TEMP | 0x350 | TempCss | 칩 온도 CSS | uint8 → 실수 (×0.5-40) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 0 | 0 | 50 ms |
| DEV_TEMP | 0x350 | TempMss | 칩 온도 MSS | uint8 → 실수 (×0.5-40) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 1 | 1 | 50 ms |
| DEV_TEMP | 0x350 | TempUpa | 칩 온도 UPA | uint8 → 실수 (×0.5-40) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 2 | 2 | 50 ms |
| DEV_TEMP | 0x350 | TempDss | 칩 온도 DSS | uint8 → 실수 (×0.5-40) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 3 | 3 | 50 ms |
| DEV_TEMP | 0x350 | TempAvg | 칩 평균 온도 | uint8 → 실수 (×0.5-40) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 4 | 4 | 50 ms |
| DEV_TEMP | 0x350 | CpuCssPct | LEON CSS CPU 사용률 | uint8 → 실수 (×0.5) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 5 | 5 | 50 ms |
| DEV_TEMP | 0x350 | CpuMssPct | LEON MSS CPU 사용률 | uint8 → 실수 (×0.5) | 8 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 6 | 6 | 50 ms |
| DEV_MEM_A | 0x351 | DdrUsedMB | DDR 메모리 사용량 | uint16 → 실수 (×0.1) | 16 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| DEV_MEM_A | 0x351 | DdrTotalMB | DDR 메모리 전체 | uint16 → 실수 (×0.1) | 16 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 2 | 3 | 50 ms |
| DEV_MEM_A | 0x351 | CmxUsedKB | CMX 메모리 사용량 | uint16 → 실수 (×0.1) | 16 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 4 | 5 | 50 ms |
| DEV_MEM_A | 0x351 | CmxTotalKB | CMX 메모리 전체 | uint16 → 실수 (×0.1) | 16 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 6 | 7 | 50 ms |
| DEV_MEM_B | 0x352 | CssHeapUsedKB | LEON CSS 힙 사용량 | uint32 | 32 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 0 | 3 | 50 ms |
| DEV_MEM_B | 0x352 | CssHeapTotalKB | LEON CSS 힙 전체 | uint32 | 32 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 4 | 7 | 50 ms |
| DEV_MEM_C | 0x353 | MssHeapUsedKB | LEON MSS 힙 사용량 | uint32 | 32 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 0 | 3 | 50 ms |
| DEV_MEM_C | 0x353 | MssHeapTotalKB | LEON MSS 힙 전체 | uint32 | 32 | 1초 | 1000 ms (Raw 켬) | Raw 켬 | 4 | 7 | 50 ms |
| CALIB_A | 0x360 | Fx | 초점거리 fx(픽셀) | uint16 → 실수 (×0.1) | 16 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| CALIB_A | 0x360 | Fy | 초점거리 fy(픽셀) | uint16 → 실수 (×0.1) | 16 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 2 | 3 | 50 ms |
| CALIB_A | 0x360 | Cx | 주점 cx(픽셀, 신경망 입력 크기 기준) | uint16 → 실수 (×0.1) | 16 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 4 | 5 | 50 ms |
| CALIB_A | 0x360 | Cy | 주점 cy(픽셀, 신경망 입력 크기 기준) | uint16 → 실수 (×0.1) | 16 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 6 | 7 | 50 ms |
| CALIB_B | 0x361 | NClasses | 클래스 수 | uint8 | 8 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 6 | 6 | 50 ms |
| CALIB_B | 0x361 | ConfThresholdPct | 신뢰도 문턱값 | uint8 | 8 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 7 | 7 | 50 ms |
| CALIB_C | 0x362 | NnInputW | 신경망 입력 너비 | uint16 | 16 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 0 | 1 | 50 ms |
| CALIB_C | 0x362 | NnInputH | 신경망 입력 높이 | uint16 | 16 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 2 | 3 | 50 ms |
| CALIB_C | 0x362 | CameraMask | 연결된 카메라 소켓 비트마스크(bit0=CAM_A) | uint8 | 8 | 10초 | 10000 ms (Raw 켬) | Raw 켬 | 4 | 5 | 50 ms |
| DEV_INFO | 0x370 | StrId | 문자열 종류(0 장치ID,1 제품명,2 플랫폼,3 부트로더,4 depthai 버전,5 모델) | uint4 | 4 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 0 | 0 | 50 ms |
| DEV_INFO | 0x370 | Chunk | 문자열 조각 번호(k번째=글자 5k~5k+4) | uint4 | 4 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 0 | 0 | 50 ms |
| DEV_INFO | 0x370 | TotalLen | 문자열 전체 길이 | uint8 | 8 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 1 | 1 | 50 ms |
| DEV_INFO | 0x370 | C0 | 문자열 조각의 1번째 글자(ASCII) | uint8 | 8 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 2 | 2 | 50 ms |
| DEV_INFO | 0x370 | C1 | 문자열 조각의 2번째 글자(ASCII) | uint8 | 8 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 3 | 3 | 50 ms |
| DEV_INFO | 0x370 | C2 | 문자열 조각의 3번째 글자(ASCII) | uint8 | 8 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 4 | 4 | 50 ms |
| DEV_INFO | 0x370 | C3 | 문자열 조각의 4번째 글자(ASCII) | uint8 | 8 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 5 | 5 | 50 ms |
| DEV_INFO | 0x370 | C4 | 문자열 조각의 5번째 글자(ASCII) | uint8 | 8 | 10초 | 10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송) | Raw 켬 | 6 | 6 | 50 ms |

## 4. DET_BOX 값의 인코딩 예

예: **car**(클래스 번호 1), 신뢰도 0.87, 박스 중심 (0.52, 0.61), 크기 (0.12, 0.09) (모두 영상 크기 대비 0~1 정규화). Seq 의 아래 4비트는 5 라고 하자.

| 변수 | 물리값 | 배율 | CAN 원시 정수 | 비트 | 512×288 픽셀 환산 |
|---|---|---|---|---|---|
| SeqLo | 5 | 1 | 5 | 0~3 | — |
| Index | 0 (신뢰도 최고) | 1 | 0 | 4~7 | — |
| Label | car | 1 | 1 | 8~14 | 클래스: 0 person · 1 car · 2 tl_red · 3 tl_green · 4 tl_yellow |
| Conf | 0.87 | 0.01 | 87 | 15~21 | — |
| Cx | 0.52 | 0.001 | 520 | 22~31 | 266.2 px (가로 512) |
| Cy | 0.61 | 0.001 | 610 | 32~41 | 175.7 px (세로 288) |
| W | 0.12 | 0.001 | 120 | 42~51 | 61.4 px |
| H | 0.09 | 0.001 | 90 | 52~61 | 25.9 px |

8바이트 데이터(16진): `05 81 2B 82 62 E2 A1 05`. 디코딩하면 원래 값이 나온다(왕복 검증 **[검증]**). 박스 모서리는 (x1, y1) = (235.5, 162.7) px, (x2, y2) = (297.0, 188.6) px (512×288 기준).
정규화한 이유: 모델 입력 해상도가 바뀌어도(512×288 → 640×384) CAN 값의 의미가 같고, 수신 쪽이 자기 화면 크기로 곱하면 된다.

## 5. 왜 이렇게 CANdb 를 구성했는가 (설계 근거)

### 5.1 메시지를 나누는 기준: 값이 바뀌는 주기와 소속

| 묶음 | 메시지(ID) | 나눈 이유 |
|---|---|---|
| 프레임 단위(5 fps) | FRAME_STATUS(0x300) · FRAME_META_A/B/C·FRAME_TIME_DEV/HOST(0x340~0x344) | 프레임마다 1개씩 생기는 값. Seq 로 서로 연결. 한 프레임에 한 번 보내면 되는 값만 모은다 |
| 검출 단위(프레임당 N개) | DET_BOX(0x310) | 검출 개수가 매번 달라 프레임 메시지에 못 넣는다. SeqLo(4bit)+Index(4bit)로 프레임과 순번을 가리킨다 |
| 1초 단위 | PERF(0x320) · DEV_TEMP·DEV_MEM_A/B/C(0x350~0x353) | 자주 바뀌지 않아 프레임마다 보낼 필요 없음 → 버스 부하 절약 |
| 10초 단위 | CALIB_A/B/C(0x360~0x362) · DEV_INFO(0x370) | 보정·장치 정보는 거의 불변. 늦게 접속한 수신기도 10초 안에 받도록 반복 |

- **ID 대역(0x30·0x31·0x32·0x34·0x35·0x36·0x37)**: CAN 은 ID 가 낮을수록 우선순위가 높다. 프레임 상태(0x300)와 검출(0x310)이 가장 먼저 중재를 이기고 10초 단위 정보(0x36x·0x370)는 뒤로 밀려도 무방하다 **[설계 원칙, 버스 부하가 낮아 실제 중재 손실은 확인되지 않음]**.
- **한 메시지는 8바이트(클래식 CAN)**: Vector VN1630A·Kvaser Leaf v3 모두 클래식 CAN 500 kbps 로 시험했고(CAN FD 는 DBC·코드에 대비만 해 둠), 검출 한 개의 클래스·신뢰도·위치·크기가 64비트에 맞는다.
- **문자열(DEV_INFO)** 은 8바이트에 ASCII 5글자씩 나눠 보낸다(StrId·Chunk·TotalLen 3바이트 + 5글자). 최대 255자 복원 **[실측: Windows 로그에서 장치 ID·제품명 복원 확인]**.

### 5.2 신호의 비트 폭과 해상도를 정한 이유

| 신호 | 선택 | 근거 |
|---|---|---|
| Seq (16bit) | 프레임 번호 65536 에서 순환 | 5 fps 에서 약 3.6시간 순환 → 수신 쪽 결번 검사에 충분. 더 크면 8바이트 프레임에 다른 값이 못 들어감 |
| Conf (7bit, 0.01) | 신뢰도 0~1.27, 0.01 단위 | 신뢰도의 의미 있는 해상도는 1% 수준. 7비트로 줄여 박스 4개 값(10비트×4)과 라벨을 한 프레임에 담음 |
| Cx·Cy·W·H (10bit, 0.001) | 정규화 0~1.023 | 입력 512 px 기준 0.5 px 미만의 단위 → 모델 정밀도보다 촘촘해 손실 없음 |
| EdgeMs (12bit, 1 ms) | 0~4095 ms, 0 = 값 없음 | 칩 지연은 약 100~400 ms. 12비트면 충분하고 0 을 '값 없음'으로 약속해 늦게 온 값을 구분 |
| SeqGap (4bit) | 0~15 에서 포화 | 연속 누락 15프레임 이상이면 '장애'로 보면 충분 |
| DEV_TEMP·DEV_MEM | 온도·CPU %·메모리 MB/KB 를 1초에 1번 | 상태 감시용이라 1초면 충분(프레임마다 보내면 부하만 늘어남) |

### 5.3 CAN 수신 주기 50 ms 와 업데이트 주기 200 ms 가 다른 이유

- **업데이트 주기 200 ms**: 카메라가 5 fps 로 찍고 신경망이 한 장씩 처리하므로 새 값은 200 ms 마다 한 번만 생긴다 **[실측: 수신 간격 중앙 199.97 ms, 표준편차 0.59 ms (단독 앱 게이트웨이 30초 시험)]**.
- **CAN 수신 주기(CANdb) 50 ms**: 교수님이 지정한 수신 기준(수신 노드가 이 간격으로 값을 읽는다고 가정). 새 값은 200 ms 마다만 오므로 50 ms 로 읽으면 **4번 중 1번만 새 값**이다.
- **현재 구현은 새 값이 생길 때만 한 번 송신(이벤트 송신)** 한다. 50 ms 마다 같은 값을 반복 송신하지 않는다 → 버스 부하가 4배로 늘지 않는다. 수신 쪽은 `Seq` 가 바뀌었는지로 새 값 여부를 판단한다.
- 대안(50 ms 반복 송신)은 부하가 4배이고 수신 쪽이 Seq 로 중복을 걸러야 해서 이득이 없다고 판단했다 **[계산·판단]**. 수신 쪽이 50 ms 마다 폴링해야 하는 요구라면 DBC 의 GenMsgCycleTime 만 50 으로 두고 송신은 이벤트로 유지하는 현재 구성이 가장 부하가 낮다.
- DBC 의 `GenMsgCycleTime` 속성은 현재 PERF(1000 ms)만 값이 있고, 엑셀의 'CANdb 송신 주기 50 ms' 열은 교수님 요청 열로 따로 두었다 **[DBC 확인]**.

### 5.4 버스 부하 계산

클래식 CAN 500 kbps, 프레임당 135 비트(11비트 ID + 8바이트, 비트 스터핑 최악 근사)로 계산: 부하(%) = 메시지/초 × 135 / 500000 × 100. 카메라 5 fps, **이 문서 범위(깊이·차선 제외)** 기준.

| 프레임당 검출 수 | Raw 끔(B·D): 메시지/초 | 부하 | Raw 켬(A·C): 메시지/초 | 부하 |
|---|---|---|---|---|
| 0 | 6 | 0.16 % | 37 | 0.99 % |
| 2 | 16 | 0.43 % | 47 | 1.26 % |
| 4 | 26 | 0.70 % | 57 | 1.53 % |
| 8 | 46 | 1.24 % | 77 | 2.07 % |

**[실측] 5분 실행의 CAN 부하·이더넷 대역폭: 측정 대기** (4조건 5분 본 측정 후 `--runs` 로 채움)

부하는 모든 조건에서 버스 용량의 약 1~5 % 로 낮아(계산) 메시지를 더 쪼개거나 합칠 여유가 크다. 이 여유 덕분에 ID 우선순위·이벤트 송신만으로 충분하다고 판단했다.

## 6. 영상 X(Raw 끔) 와의 차이

| 항목 | 영상 X · Raw 끔 (B) | 영상 O (A: Raw 켬 / D: Raw 끔) |
|---|---|---|
| CAN 메시지 | FRAME_STATUS · DET_BOX · PERF | D 는 B 와 같음 / A 는 + 프레임 메타·시간·지연·칩 상태·보정·장치 정보 |
| 이더넷 | 신경망 원시 출력만 | + RGB 프레임 (512×288×3 = 442,368 byte, 5 fps = 2.2 MB/s, 계산) |
| CAN 부하(검출 4개 가정) | 0.70 % | D 같음 / A 1.53 % |
| AI 결과 기록(카메라 PC) | frames.csv·run_info.json 만 | A: + raw_ai_candidates/seg·텐서(선택) |

## 7. 검증 현황

| 항목 | 상태 | 근거 |
|---|---|---|
| DBC 의 변수·시작/끝 byte | [검증] cantools 로 인코딩/디코딩 왕복, selftest 통과 | make_candb_doc.py 가 DBC 에서 직접 생성 |
| DET_BOX 인코딩 예 | [검증] 왕복 일치 | 4절의 바이트·정수·픽셀 환산 |
| 수신 간격 200 ms·결번 0 | [실측, 이전 시험] Raw 켬 30초 2회 송신=수신 1154=1154, 1132=1132; 단독 앱 게이트웨이 151=151 | Windows 로거 LOGGED 보고 |
| 조건별 5분 부하·대역폭 | [측정 대기] | 4조건 본 측정(사용자 승인 후) |
| 영상 원본 CAN 불가 비율(약 25배) | [계산] | 1절의 식 |

## 부록. 변수가 정의된 파일 (경로는 저장소 `can_canoe/` 기준)

| 파일 | 무엇이 정의되는가 |
|---|---|
| `oakd_canoe.dbc` · `oakd_canoe_fd.dbc` | CAN 메시지·신호(ID, 시작 bit, 길이, 배율, 범위, 코멘트), GenMsgCycleTime(PERF=1000 만) |
| `can_msgs.py` | DBC 로드, `MODEL_IDS`(ModelId 번호), 메시지 만드는 함수(`frame_status`·`det_box`·`perf`·`seg_summary`·`make`), 신호 범위 자르기(`_msg`), `BITS_PER_FRAME` |
| `oak_full.py` | Raw 켬 값: `frame_meta`·`telemetry_row`·`session_info` 필드, CAN 메시지 변환(`meta_messages`·`telemetry_messages`·`session_messages`), 가짜 값 |
| `can_demo.py` (· `can_demo_no_comments.py`) | 칩 위 Script(`EDGE_SCRIPT`: 칩 지연 EdgeMs), 프레임마다·1초·10초 송신 구조, 인자(`--raw`·`--video` …), `summary.csv`·`run_info.json` 열 |
| `a_yolom/a_yolom_source.py` | A-YOLOM 파이프라인(카메라→신경망), 칩 위 `META_SCRIPT`(프레임 메타 JSON), 호스트 후처리 호출, Raw 기록 |
| `a_yolom/postprocess.py` · `postprocess_variants.py` · `postprocess_variants3.py` | 신경망 출력 이름·shape 가정, 박스 디코딩(DFL·NMS), 변형별 처리 |
| `a_yolom/raw_ai.py` | AI 연산 결과 기록(`raw_ai_candidates.csv`·`raw_ai_seg.csv`·텐서) 형식 |
| `dbc_to_excel.py` · `make_candb_doc.py` | 이 문서·엑셀 생성 (제외 목록 `EXCLUDE_MSGS`·`EXCLUDE_SIGS`) |
| `analyze.py` · `canoe_logger.py` · `extra_messages.py` | CAN 수신 로그 해석(클래스 이름 `LABELS`, 메시지별 CSV) |

