#!/usr/bin/env python3
"""발표용 PERF CSV: 실수값을 소수 둘째 자리에서 내림하고, 열 제목을 한글로 바꿔 따로 저장한다.

원본(logs/*/PERF.csv)은 건드리지 않는다 (analyze.py 가 영어 열 이름을 쓰기 때문).
결과는 <날짜 폴더>/발표용/PERF_<실행이름>.csv 이고, 엑셀에서 한글이 깨지지 않게 UTF-8(BOM)으로 저장한다.

예) python3 slide_perf_csv.py ../results/can_canoe/20261007
"""
import argparse
import csv
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path

HEADERS = {
    "run": "실행 번호",
    "t_axis_s": "시간축(초)",
    "canoe_ts_s": "수신 시각(초)",
    "PcMs": "PC 쪽 지연(ms)",
    "PostMs": "박스 그리기 시간(ms)",
    "EthKBps": "이더넷 수신량(KB/s)",
    "CanLoadPct": "CAN 부하(%)",
    "DroppedTotal": "누적 버려진 프레임 수",
    "frame_seq": "프레임 번호",
    "frame_ts_s": "프레임 수신 시각(초)",
    "edge_ms": "칩 안 지연(ms)",
    "det_count": "검출 개수",
    "box_class": "박스 클래스",
    "box_label": "박스 클래스 번호",
    "box_conf": "박스 신뢰도(0~1)",
    "box_cx": "박스 중심 x(0~1)",
    "box_cy": "박스 중심 y(0~1)",
    "box_w": "박스 폭(0~1)",
    "box_h": "박스 높이(0~1)",
}
REAL = {"canoe_ts_s", "PcMs", "PostMs", "CanLoadPct", "frame_ts_s", "box_conf", "box_cx", "box_cy", "box_w", "box_h"}


def floor2(text):
    """소수 둘째 자리 내림. 2.9000000000000004 같은 계산 오차는 먼저 6자리로 정리해서 없앤다."""
    if text == "":
        return ""
    try:
        return str(Decimal(f"{float(text):.6f}").quantize(Decimal("0.01"), rounding=ROUND_FLOOR))
    except (InvalidOperation, ValueError):
        return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date_dir", help="logs/ 가 들어 있는 날짜 폴더 (예: ../results/can_canoe/20261007)")
    a = ap.parse_args()
    root = Path(a.date_dir)
    out = root / "발표용"
    out.mkdir(exist_ok=True)
    for src in sorted((root / "logs").glob("*/PERF.csv")):
        rows = list(csv.DictReader(open(src, encoding="utf-8")))
        cols = list(rows[0])
        dst = out / f"PERF_{src.parent.name}.csv"
        with open(dst, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow([HEADERS.get(c, c) for c in cols])
            for r in rows:
                w.writerow([floor2(r[c]) if c in REAL else r[c] for c in cols])
        print(f"{dst.name}: {len(rows)}행")


if __name__ == "__main__":
    main()
