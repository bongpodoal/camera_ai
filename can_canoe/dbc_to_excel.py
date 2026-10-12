"""oakd_canoe.dbc → 엣지 카메라 송출 데이터 정리 엑셀 (교수님 요청).

시트 ① 영상 미송출: 영상 없이 CAN 으로 보내는 모든 변수 (DBC 에서 자동 생성 → DBC 와 어긋나지 않는다)
시트 ② 영상 송출 : ① 에 더해 영상 스트림(RGB·깊이)을 PC 로 받을 때 추가되는 항목. 영상은 CAN 불가 → 이더넷
열: 변수명, 의미, 변수형, 길이, 업데이트 주기, + CANdb(50 ms, ID, 시작 byte, 끝 byte)

실행: python dbc_to_excel.py [출력.xlsx] [--fps 5] [--dbc oakd_canoe.dbc]
"""
import argparse
from pathlib import Path

import cantools
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
CANDB_CYCLE_MS = 50          # 교수님 요청: CANdb 송신 주기 열

# 메시지별 실제 데이터 갱신 주기 (can_demo.py 의 송신 구조와 같다). {fps} = 카메라 fps
PERIOD = {
    "FRAME_STATUS": ("프레임마다", "{frame_ms} ms (={fps:g} fps)"),
    "DET_BOX": ("검출마다", "프레임마다, 검출 개수만큼 (최대 N개)"),
    "PERF": ("1초", "1000 ms"),
    "DET_POS": ("검출마다", "프레임마다, 검출 개수만큼 (Raw 켬)"),
    "DET_ROI": ("검출마다", "프레임마다, 검출 개수만큼 (Raw 켬)"),
    "FRAME_META_A": ("프레임마다", "{frame_ms} ms (Raw 켬)"),
    "FRAME_META_B": ("프레임마다", "{frame_ms} ms (Raw 켬)"),
    "FRAME_META_C": ("프레임마다", "{frame_ms} ms (Raw 켬)"),
    "FRAME_TIME_DEV": ("프레임마다", "{frame_ms} ms (Raw 켬)"),
    "FRAME_TIME_HOST": ("프레임마다", "{frame_ms} ms (Raw 켬)"),
    "DEV_TEMP": ("1초", "1000 ms (Raw 켬)"),
    "DEV_MEM_A": ("1초", "1000 ms (Raw 켬)"),
    "DEV_MEM_B": ("1초", "1000 ms (Raw 켬)"),
    "DEV_MEM_C": ("1초", "1000 ms (Raw 켬)"),
    "CALIB_A": ("10초", "10000 ms (Raw 켬)"),
    "CALIB_B": ("10초", "10000 ms (Raw 켬)"),
    "CALIB_C": ("10초", "10000 ms (Raw 켬)"),
    "DEV_INFO": ("10초", "10000 ms (Raw 켬, 문자열 5글자씩 나눠 전송)"),
}
RAW_OFF_MSGS = {"FRAME_STATUS", "DET_BOX", "PERF"}

# 변수 의미(한글). (메시지, 변수) 가 없으면 변수명만으로 찾고, 그래도 없으면 DBC 영어 주석을 쓴다
KO = {
    "Seq": "카메라 프레임 번호(65536 에서 돌아옴)", "DetCount": "이 프레임의 검출 개수", "Fps": "칩 처리 속도(최근 1초)",
    "EdgeMs": "칩 안 지연(촬영→검출 결과, 같은 칩 시계라 드리프트 없음). 0=값 없음", "SeqGap": "직전 메시지 이후 건너뛴 프레임 수(최대 15)",
    "ModelId": "모델 번호(0 yolov6n,1 yolov8n,2 traffic_light,3 traffic_light_11n,4 traffic_light_v8n)", "RawOn": "Raw 켬 여부(0 검출만, 1 영상 등 전부)",
    "SeqLo": "프레임 번호의 아래 4비트(FRAME_STATUS.Seq 와 연결)", "Index": "검출 순번(0=신뢰도 최고)", "Label": "클래스 번호",
    "Conf": "신뢰도 0~1(카메라 출력값, 정확도 아님)", "Cx": "박스 중심 X(0~1 정규화)", "Cy": "박스 중심 Y(0~1 정규화)", "W": "박스 너비(0~1)", "H": "박스 높이(0~1)",
    "PcMs": "PC 쪽 지연 중앙값(이더넷·큐·처리)", "PostMs": "영상에 박스 그리는 시간(Raw 끔이면 0)", "EthKBps": "카메라→PC 이더넷 수신량(KB/s)",
    "CanLoadPct": "CAN 버스 부하 추정(최악 비트 스터핑)", "DroppedTotal": "입력 큐에서 버려진 프레임 누적",
    "X": "객체 X 위치(카메라 기준 오른쪽 +, 깊이 지도 기반)", "Y": "객체 Y 위치(아래 +)", "Z": "객체 Z 거리(앞 +)",
    "RoiX": "깊이 ROI 시작 X", "RoiY": "깊이 ROI 시작 Y", "RoiW": "깊이 ROI 너비", "RoiH": "깊이 ROI 높이",
    "ExposureUs": "노출 시간", "Iso": "ISO 감도", "ColorTempK": "색온도", "LensPos": "렌즈 위치(-1=고정 초점)", "SourceW": "센서 영상 너비",
    "SourceH": "센서 영상 높이", "CamInstance": "카메라 소켓 번호", "FrameType": "영상 픽셀 형식 코드(ImgFrame type)",
    "FrameW": "신경망이 처리한 영상 너비", "FrameH": "신경망이 처리한 영상 높이", "HfovDeg": "수평 화각", "VfovDeg": "수직 화각",
    "TsDeviceUs": "촬영 시각(카메라 시계, μs, 71.6분마다 돌아옴)", "DetLatencyMs": "촬영→검출까지 지연",
    "TsHostUs": "촬영 시각(호스트 시계로 동기, μs)", "FrameLatencyMs": "촬영→프레임 수신까지 지연",
    "TempCss": "칩 온도 CSS", "TempMss": "칩 온도 MSS", "TempUpa": "칩 온도 UPA", "TempDss": "칩 온도 DSS", "TempAvg": "칩 평균 온도",
    "CpuCssPct": "LEON CSS CPU 사용률", "CpuMssPct": "LEON MSS CPU 사용률",
    "DdrUsedMB": "DDR 메모리 사용량", "DdrTotalMB": "DDR 메모리 전체", "CmxUsedKB": "CMX 메모리 사용량", "CmxTotalKB": "CMX 메모리 전체",
    "CssHeapUsedKB": "LEON CSS 힙 사용량", "CssHeapTotalKB": "LEON CSS 힙 전체", "MssHeapUsedKB": "LEON MSS 힙 사용량", "MssHeapTotalKB": "LEON MSS 힙 전체",
    "Fx": "초점거리 fx(픽셀)", "Fy": "초점거리 fy(픽셀)", "BaselineCm": "스테레오 기선 길이", "DepthLoMm": "유효 깊이 최소", "DepthHiMm": "유효 깊이 최대",
    "NClasses": "클래스 수", "ConfThresholdPct": "신뢰도 문턱값", "NnInputW": "신경망 입력 너비", "NnInputH": "신경망 입력 높이",
    "SpatialOn": "깊이 위치 계산 켬 여부", "CameraMask": "연결된 카메라 소켓 비트마스크(bit0=CAM_A)",
    "StrId": "문자열 종류(0 장치ID,1 제품명,2 플랫폼,3 부트로더,4 depthai 버전,5 모델)", "Chunk": "문자열 조각 번호(k번째=글자 5k~5k+4)", "TotalLen": "문자열 전체 길이",
}
for _i in range(5):
    KO[f"C{_i}"] = f"문자열 조각의 {_i + 1}번째 글자(ASCII)"
KO_MSG = {("CALIB_A", "Cx"): "주점 cx(픽셀, 신경망 입력 크기 기준)", ("CALIB_A", "Cy"): "주점 cy(픽셀, 신경망 입력 크기 기준)"}


def ctype(sig):
    """변수형: 정수형이면 uint/int + 비트 수, 배율이 있으면 '정수 raw × 배율 = 실수 물리값'."""
    base = ("int" if sig.is_signed else "uint") + str(sig.length)
    if sig.length == 1:
        base = "bool(1bit)"
    if sig.scale != 1 or sig.offset != 0:
        return f"{base} → 실수 (×{sig.scale:g}{'%+g' % sig.offset if sig.offset else ''})"
    return base


def rows_can(db, fps):
    frame_ms = round(1000 / fps)
    out = []
    for m in sorted(db.messages, key=lambda x: x.frame_id):
        cat, per = PERIOD[m.name]
        per = per.format(frame_ms=frame_ms, fps=fps)
        for s in m.signals:
            sb, eb = s.start // 8, (s.start + s.length - 1) // 8          # Intel(리틀엔디언) 기준, 0 부터 시작
            rng = f"{s.minimum:g} ~ {s.maximum:g}" if s.minimum is not None else ""
            out.append([m.name, f"0x{m.frame_id:03X}", m.frame_id, s.name, KO_MSG.get((m.name, s.name)) or KO.get(s.name) or (s.comment or "").strip() or (m.comment or ""),
                        ctype(s), s.length, s.length / 8, s.unit or "", rng, cat, per, "Raw 끔+켬" if m.name in RAW_OFF_MSGS else "Raw 켬",
                        CANDB_CYCLE_MS, m.length, sb, eb, s.start])
    return out


def rows_video(fps):
    """② 영상 송출 시 추가되는 영상 항목. 크기는 설정값 기준 계산(실측 아님) → 실측 후 보완."""
    items = [
        ("RGB 프레임(신경망이 처리한 영상)", "신경망 입력과 같은 크기의 컬러 영상. 모델마다 다름", "uint8 × (W×H×3, BGR 평면)",
         "traffic_light 416×416", 416 * 416 * 3),
        ("RGB 프레임(yolov6n 입력)", "yolov6n 입력 크기", "uint8 × (W×H×3)", "512×288", 512 * 288 * 3),
        ("깊이 프레임(depth)", "스테레오 깊이 지도(밀리미터). 640×400 가정 — 실측으로 확인", "uint16 × (W×H)", "640×400 (가정)", 640 * 400 * 2),
    ]
    out = []
    for name, meaning, ctype_, size_txt, nbytes in items:
        can_frames = -(-nbytes // 8)
        can_sec = can_frames * 135 / 500_000                    # 클래식 CAN 500 kbps, 프레임당 135 비트(최악)
        fd_frames = -(-nbytes // 64)
        out.append([name, meaning, ctype_, size_txt, nbytes, f"{fps:g} fps ({round(1000 / fps)} ms)", nbytes * fps * 8 / 1e6,
                    can_frames, round(can_sec, 1), fd_frames, "이더넷(UDP/TCP)으로만 수신. CAN 불가 — 아래 계산 참고"])
    return out


def build(db, fps, path):
    wb = Workbook()
    head = ["메시지", "CAN ID(hex)", "CAN ID(10진)", "변수명", "변수 의미", "변수형", "길이(bit)", "길이(byte)", "단위", "범위(물리값)",
            "갱신 종류", "업데이트 주기", "필요한 모드", "CANdb 송신 주기(ms)", "메시지 길이(byte)", "시작 byte", "끝 byte", "시작 bit"]
    ws = wb.active
    ws.title = "① 영상 미송출"
    ws.append(head)
    can_rows = rows_can(db, fps)
    for r in can_rows:
        ws.append(r)
    ws2 = wb.create_sheet("② 영상 송출 (추가 항목)")
    ws2.append(["※ ① 의 모든 항목(CAN) + 아래 영상 항목(이더넷). 영상은 CAN 으로 못 보낸다(아래 열의 CAN 프레임 수 참고)."])
    ws2.append([])
    ws2.append(["항목", "의미", "변수형", "크기(설정값)", "1장 크기(byte)", "업데이트 주기", "필요 대역폭(Mbps)",
                "CAN 8byte 프레임 수/장", "클래식 CAN 500k 로 1장 전송 시간(초)", "CAN FD 64byte 프레임 수/장", "송출 경로·비고"])
    for r in rows_video(fps):
        ws2.append(r)
    ws2.append([])
    ws2.append(["영상과 같이 오는 프레임 정보(노출·ISO·색온도·렌즈·크기·시각)는 ① 의 FRAME_META_A/B/C, FRAME_TIME_DEV/HOST 로 CAN 에 실린다."])
    ws3 = wb.create_sheet("읽는 법·가정")
    for line in [
        "분류: ① 영상 미송출 = 영상 스트림을 받지 않고 CAN 으로 보내는 값 / ② 영상 송출 = ① + 영상(RGB·깊이) 이더넷 수신",
        "시작/끝 byte: Intel(리틀엔디언) 기준, 메시지의 0번째 byte 부터 센 값. 한 변수가 여러 byte 에 걸치면 시작~끝",
        f"CANdb 송신 주기 {CANDB_CYCLE_MS} ms: 교수님 요청 열. 카메라 값은 {fps:g} fps(={round(1000/fps)} ms)마다 갱신되므로 50 ms 로 보내면 4번 중 1번만 새 값이다.",
        "업데이트 주기가 '미설정'인 항목은 없음(모두 코드의 송신 주기를 적었다). 정해지지 않으면 '미설정'으로 쓴다.",
        "영상 크기·대역폭은 설정값 기준 계산이다. 카메라 연결 후 실측(EthKBps)으로 보완한다.",
        "카메라는 USB 가 아니라 PoE 이더넷으로 연결돼 있어 '송신 경로'는 이더넷 기준으로 정리했다.",
        f"변수 {len(can_rows)}개 / 메시지 {len(db.messages)}개 (DBC 에서 자동 생성)",
    ]:
        ws3.append([line])
    fill, bold = PatternFill("solid", fgColor="DDEBF7"), Font(bold=True)
    for sheet, hrow in ((ws, 1), (ws2, 3)):
        for c in sheet[hrow]:
            c.fill, c.font = fill, bold
            c.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.freeze_panes = sheet.cell(row=hrow + 1, column=1)
        for i in range(1, sheet.max_column + 1):
            sheet.column_dimensions[get_column_letter(i)].width = 16
    ws.column_dimensions["E"].width = 60
    ws2.column_dimensions["B"].width = 40
    ws2.column_dimensions["K"].width = 45
    ws3.column_dimensions["A"].width = 140
    wb.save(path)
    return len(can_rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="oakd_송출데이터_정리.xlsx")
    ap.add_argument("--fps", type=float, default=5)
    ap.add_argument("--dbc", default=str(HERE / "oakd_canoe.dbc"))
    a = ap.parse_args()
    n = build(cantools.database.load_file(a.dbc), a.fps, a.out)
    print(f"{a.out}: 변수 {n}개")
