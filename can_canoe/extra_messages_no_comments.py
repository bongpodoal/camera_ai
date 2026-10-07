import argparse
import csv
from pathlib import Path

import can

from can_msgs import DB, ID_FRAME

BASE = {"FRAME_STATUS", "DET_BOX", "PERF"}
STR_NAMES = {0: "device_id", 1: "product_name", 2: "platform", 3: "bootloader", 4: "depthai_version", 5: "model"}

def extract(log, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    by_name, t0, info = {}, None, {}
    for m in can.LogReader(str(log)):
        if m.is_error_frame:
            continue
        try:
            msg = DB.get_message_by_frame_id(m.arbitration_id)
        except KeyError:
            continue
        if m.arbitration_id == ID_FRAME and t0 is None:
            t0 = m.timestamp
        if msg.name in BASE or t0 is None:
            continue
        vals = msg.decode(m.data, decode_choices=False)
        t_ms = round((m.timestamp - t0) * 1000)
        if msg.name == "DEV_INFO":
            sid, k, total = int(vals["StrId"]), int(vals["Chunk"]), int(vals["TotalLen"])
            chars = "".join(chr(int(vals[f"C{i}"])) for i in range(5) if int(vals[f"C{i}"]))
            info.setdefault(sid, {"total": total, "chunks": {}, "t_ms": t_ms})["chunks"][k] = chars
            continue
        by_name.setdefault(msg.name, []).append(dict(t_axis_ms=t_ms, **vals))
    for name, rows in by_name.items():
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    texts = {}
    for sid, v in info.items():
        text = "".join(v["chunks"][k] for k in sorted(v["chunks"]))[:v["total"]]
        texts[STR_NAMES.get(sid, str(sid))] = text
    if texts:
        with open(out / "DEV_INFO.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["name", "value"])
            w.writerows(texts.items())
    return {n: len(r) for n, r in by_name.items()}, texts

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    counts, texts = extract(a.log, a.out)
    print("메시지별 개수:", counts)
    print("문자열:", texts)
