import argparse
import csv
import json
import statistics
from pathlib import Path

import can
import numpy as np

from can_msgs import BITS_PER_FRAME, ID_FRAME, ID_PERF, MODEL_IDS, decode

GAP_S = 5.0
HERE = Path(__file__).resolve().parent
COCO_CFG = HERE.parent / "example/05_nnarchive/example/yolov6-nano/config.json"
LABELS = {"traffic_light": ["red", "yellow", "green", "off"], "traffic_light_11n": ["red", "yellow", "green", "off"]}

def label_names(model):
    if model in LABELS:
        return LABELS[model]
    try:
        return json.load(open(COCO_CFG))["model"]["heads"][0]["metadata"]["classes"]
    except (OSError, KeyError, ValueError):
        return []

def read_log(path):
    allmsgs, frames, perfs = [], [], []
    for m in can.LogReader(str(path)):
        allmsgs.append(m.timestamp)
        if m.arbitration_id == ID_FRAME:
            frames.append((m.timestamp, decode(m)[1]))
        elif m.arbitration_id == ID_PERF:
            perfs.append((m.timestamp, decode(m)[1]))
    return allmsgs, frames, perfs

def split_segments(frames):
    segs, cur = [], []
    for ts, v in frames:
        key = (int(v["ModelId"]), int(v["RawOn"]))
        if cur and (key != cur[0][2] or ts - cur[-1][0] > GAP_S):
            segs.append(cur)
            cur = []
        cur.append((ts, v, key))
    if cur:
        segs.append(cur)
    return segs

def read_run(d):
    rows = list(csv.DictReader(open(d / "frames.csv")))
    dets = list(csv.DictReader(open(d / "detections.csv"))) if (d / "detections.csv").exists() else []
    summ = list(csv.DictReader(open(d / "summary.csv")))[-1] if (d / "summary.csv").exists() else {}
    return rows, dets, summ

def slope_ppm(x, y):
    if len(x) < 3:
        return None
    return (float(np.polyfit(x, y, 1)[0]) - 1) * 1e6

def med(v, nd=2):
    return round(statistics.median(v), nd) if v else ""

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True)
    ap.add_argument("--runs-root", required=True)
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--warmup-s", type=float, default=3.0)
    a = ap.parse_args(argv)
    root = Path(a.runs_root).expanduser()

    allts, frames, perfs = read_log(a.log)
    segs = split_segments(frames)
    runs = {}
    for d in sorted(p for p in root.iterdir() if (p / "frames.csv").exists()):
        first = next(csv.DictReader(open(d / "frames.csv")), None)
        if first:
            runs.setdefault((MODEL_IDS[first["model"]], 1 if first["raw"] == "on" else 0), []).append(d)
    print(f"로그 프레임 {len(frames)}개 → 실행 {len(segs)}개로 나눔 / 실행 폴더 {sum(len(v) for v in runs.values())}개")

    compare, plots = [], []
    used = {}
    for seg in segs:
        key = seg[0][2]
        n = used.get(key, 0)
        used[key] = n + 1
        if key not in runs or n >= len(runs[key]):
            print(f"  짝 없는 구간 건너뜀: ModelId={key[0]} RawOn={key[1]} ({len(seg)}프레임)")
            continue
        d = runs[key][n]
        rows, dets, summ = read_run(d)
        j, pairs = 0, []
        for ts, v, _ in seg:
            s16 = int(v["Seq"])
            for k in range(j, min(j + 60, len(rows))):
                if int(rows[k]["seq"]) % 65536 == s16:
                    pairs.append((ts, rows[k]))
                    j = k + 1
                    break
        if not pairs:
            print(f"  {d.name}: 맞는 프레임 없음")
            continue
        ts0, dev0, send0 = pairs[0][0], float(pairs[0][1]["dev_t_s"]), float(pairs[0][1]["t_send_s"])
        ts_arr = np.array([p[0] - ts0 for p in pairs])
        dev_arr = np.array([float(p[1]["dev_t_s"]) - dev0 for p in pairs])
        snd_arr = np.array([float(p[1]["t_send_s"]) - send0 for p in pairs])
        keep = ts_arr >= a.warmup_s
        cam_ppm, pc_ppm = slope_ppm(ts_arr[keep], dev_arr[keep]), slope_ppm(ts_arr[keep], snd_arr[keep])
        t_axis = [round(t * 1000) for t in ts_arr]
        interval = np.diff(ts_arr) * 1000
        with open(d / "frames_axis.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["model", "raw", "seq", "t_axis_ms", "canoe_ts_s", "interval_ms", "cam_minus_canoe_ms",
                        "pc_minus_canoe_ms", "edge_ms", "pc_ms", "post_ms", "raw_bytes", "n_objects"])
            for i, (ts, r) in enumerate(pairs):
                w.writerow([r["model"], r["raw"], r["seq"], t_axis[i], f"{ts:.6f}",
                            round(float(interval[i - 1]), 3) if i else "",
                            round((dev_arr[i] - ts_arr[i]) * 1000, 3), round((snd_arr[i] - ts_arr[i]) * 1000, 3),
                            r["edge_ms"], r["pc_ms"], r["post_ms"], r["raw_bytes"], r["n_objects"]])
        plots.append((f"{pairs[0][1]['model']} raw {pairs[0][1]['raw']}", ts_arr, (dev_arr - ts_arr) * 1000))

        t_end = seg[-1][0]
        in_span = sum(1 for t in allts if seg[0][0] <= t <= t_end)
        span = max(t_end - seg[0][0], 1e-9)
        names = label_names(pairs[0][1]["model"])
        counts = {}
        for r in dets:
            lab = int(float(r["label"]))
            counts[lab] = counts.get(lab, 0) + 1
        top = ", ".join(f"{names[k] if k < len(names) else k}:{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:5])
        confs = [float(r["confidence"]) for r in dets]
        n_obj = [int(r["n_objects"]) for r in rows]
        sent = len(rows)
        compare.append(dict(
            model=pairs[0][1]["model"], raw=pairs[0][1]["raw"], run=d.name, frames_sent=sent, frames_rx=len(pairs),
            lost=sent - len(pairs), fps=round(len(pairs) / span, 2), interval_ms_median=med(list(interval)),
            interval_ms_std=round(float(np.std(interval)), 2) if len(interval) > 1 else "",
            edge_ms=summ.get("edge_ms", ""), pc_ms=summ.get("pc_ms", ""), post_ms=summ.get("post_ms", ""),
            eth_MBps=summ.get("eth_MBps", ""), can_load_pct=round(100 * in_span / span * BITS_PER_FRAME / a.bitrate, 2),
            camera_drift_ppm=round(cam_ppm, 1) if cam_ppm is not None else "",
            pc_drift_ppm=round(pc_ppm, 1) if pc_ppm is not None else "",
            frames_with_det_pct=round(100 * sum(1 for n in n_obj if n) / sent, 1) if sent else "",
            det_per_frame=round(sum(n_obj) / sent, 2) if sent else "",
            conf_mean=round(statistics.mean(confs), 3) if confs else "", top_classes=top))
        print(f"  {d.name}: 송신 {sent} / 수신 {len(pairs)}, 카메라 시계 {compare[-1]['camera_drift_ppm']} ppm")

    if not compare:
        print("비교할 실행이 없음")
        return 1
    with open(root / "compare.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(compare[0]))
        w.writeheader()
        w.writerows(compare)
    cols = ["model", "raw", "frames_rx", "lost", "fps", "interval_ms_std", "edge_ms", "pc_ms", "post_ms", "eth_MBps",
            "can_load_pct", "camera_drift_ppm", "frames_with_det_pct", "conf_mean"]
    with open(root / "compare.md", "w") as fh:
        fh.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for c in compare:
            fh.write("| " + " | ".join(str(c[k]) for k in cols) + " |\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4))
        for label, x, y in plots:
            ax.plot(x, y, label=label)
        ax.set_xlabel("CANoe time (s)")
        ax.set_ylabel("camera clock - CANoe clock (ms)")
        ax.legend(fontsize=7)
        fig.savefig(root / "drift.png", dpi=120, bbox_inches="tight")
    except ImportError:
        print("matplotlib 없음 → drift.png 건너뜀 (frames_axis.csv 의 cam_minus_canoe_ms 로 직접 그리면 됨)")
    print(f"→ {root / 'compare.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
