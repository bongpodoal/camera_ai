"""edge_logger.py 기록을 검토한다. 모든 결과는 기록 폴더 안 review/ 에 저장된다.

    python3 review.py summary  runs/<폴더>              # 통계 + 파라미터 추출 개수 (50개 이상인지)
    python3 review.py frame    runs/<폴더> --t 125.3    # 그 시각에 신경망이 처리한 이미지 + 검출 + 메타데이터
    python3 review.py frame    runs/<폴더> --seq 3760
    python3 review.py sheet    runs/<폴더> --every 10   # 10초 간격 이미지를 한 장에 (5분 = 30칸)
    python3 review.py timeline runs/<폴더>              # FPS·지연·검출 수·칩 온도·CPU 시간 그래프
"""
import argparse
import json
import statistics
from pathlib import Path

import cv2
import numpy as np

import params
from common import draw_detections, draw_header, fnum, read_csv


def load(run):
    run = Path(run)
    frames = read_csv(run / "frames.csv")
    dets = {}
    for d in read_csv(run / "detections.csv"):
        dets.setdefault(d["seq"], []).append(d)
    tele = read_csv(run / "telemetry.csv")
    sess = json.loads((run / "session.json").read_text()) if (run / "session.json").exists() else {}
    return run, frames, dets, tele, sess


def _out(run, name):
    d = Path(run) / "review"
    d.mkdir(exist_ok=True)
    return d / name


def _pct(vals, q):
    vals = sorted(vals)
    return vals[min(int(q * len(vals)), len(vals) - 1)] if vals else float("nan")


# ---------------------------------------------------------------- summary
def cmd_summary(args):
    run, frames, dets, tele, sess = load(args.run)
    all_d = [d for ds in dets.values() for d in ds]
    t_end = fnum(frames[-1]["t_s"], 0) if frames else 0
    lat = [v for v in (fnum(f["latency_ms"]) for f in frames) if v is not None]
    fps = [v for v in (fnum(f["fps_inst"]) for f in frames) if v is not None]
    gaps = sum(int(fnum(f["seq_gap"], 0)) for f in frames)
    saved = sum(1 for f in frames if f["image_file"] and (run / f["image_file"]).exists())

    print(f"기록       : {run.name}  ({sess.get('source', '?')}, 모델 {sess.get('model', '?')})")
    print(f"장치       : {sess.get('product_name', '?')} {sess.get('device_id', '')}")
    print(f"길이       : {t_end:.1f}s  프레임 {len(frames)}  평균 {len(frames) / t_end if t_end else 0:.2f} fps")
    print(f"누락       : seq 누락 {gaps}  저장 누락 {sess.get('recorder_dropped', '?')}")
    print(f"이미지     : {saved}/{len(frames)} 저장됨  영상 {'있음' if (run / 'annotated.mp4').exists() else '없음'}")
    if lat:
        print(f"지연 [ms]  : 중앙 {statistics.median(lat):.1f}  p95 {_pct(lat, 0.95):.1f}  최대 {max(lat):.1f}")
    if fps:
        print(f"순간 fps   : 중앙 {statistics.median(fps):.2f}  p5 {_pct(fps, 0.05):.2f}")
    by = {}
    for d in all_d:
        by[d["label_name"]] = by.get(d["label_name"], 0) + 1
    print(f"검출       : {len(all_d)}개  " + ", ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda x: -x[1])[:8]))
    if tele:
        temps = [fnum(t["temp_avg"]) for t in tele if fnum(t["temp_avg"]) is not None]
        print(f"칩 온도    : {min(temps):.1f} → {max(temps):.1f} °C  ({len(tele)}회 기록)")

    # 파라미터 추출 확인: 카탈로그의 각 항목이 실제로 값을 가졌는가
    have = {}
    for p in params.CATALOG:
        if p.file == "session":
            ok = sess.get(p.name) not in (None, "")
        else:
            rows = {"frames": frames, "detections": all_d, "telemetry": tele}[p.file]
            ok = any(r.get(p.name) not in (None, "") for r in rows)
        have.setdefault(p.name, False)
        have[p.name] = have[p.name] or ok
    got = [k for k, v in have.items() if v]
    miss = [k for k, v in have.items() if not v]
    print(f"파라미터   : {len(got)}/{len(have)}개 값 있음  → {'50개 이상 충족' if len(got) >= 50 else '50개 미만'}")
    if miss:
        print(f"값 없음    : {', '.join(miss)}")
    _out(run, "summary.json").write_text(json.dumps(
        dict(frames=len(frames), duration_s=t_end, seq_gaps=gaps, detections=len(all_d), by_class=by,
             params_with_value=len(got), params_total=len(have), missing=miss), indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- frame
def _nearest(frames, t=None, seq=None):
    cand = [f for f in frames if f["image_file"]]
    if seq is not None:
        return min(cand, key=lambda f: abs(int(f["seq"]) - seq))
    return min(cand, key=lambda f: abs(fnum(f["t_s"], 0) - t))


def render(run, f, dets):
    img = cv2.imread(str(Path(run) / f["image_file"]))
    if img is None:
        raise SystemExit(f"이미지 없음: {f['image_file']}")
    ds = dets.get(f["seq"], [])
    draw_detections(img, ds)
    draw_header(img, f"t={fnum(f['t_s'], 0):.2f}s seq={f['seq']} det={len(ds)} lat={f['latency_ms']}ms")
    return img, ds


def cmd_frame(args):
    run, frames, dets, tele, _ = load(args.run)
    f = _nearest(frames, args.t, args.seq)
    img, ds = render(run, f, dets)
    # 오른쪽에 이 프레임의 파라미터를 붙인다
    keys = ["t_s", "seq", "latency_ms", "det_latency_ms", "fps_inst", "seq_gap", "exposure_us", "iso",
            "lens_pos", "color_temp_k", "det_count", "conf_max", "top_label", "nearest_z_mm"]
    lines = [f"{k}: {f.get(k, '')}" for k in keys]
    near_t = min(tele, key=lambda t: abs(fnum(t["t_s"], 0) - fnum(f["t_s"], 0))) if tele else None
    if near_t:
        lines += [f"temp_avg: {near_t['temp_avg']}", f"cpu_css_pct: {near_t['cpu_css_pct']}"]
    lines += [""] + [f"#{d['idx']} {d['label_name']} {fnum(d['confidence'], 0):.2f}"
                     + (f" z={fnum(d['z_mm'], 0) / 1000:.2f}m" if d.get("z_mm") else "") for d in ds[:12]]
    panel = np.zeros((max(img.shape[0], 14 * len(lines) + 10), 260, 3), np.uint8)
    for i, s in enumerate(lines):
        cv2.putText(panel, s, (6, 16 + 14 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (230, 230, 230), 1, cv2.LINE_AA)
    canvas = np.zeros((panel.shape[0], img.shape[1] + panel.shape[1], 3), np.uint8)
    canvas[:img.shape[0], :img.shape[1]] = img
    canvas[:, img.shape[1]:] = panel
    path = Path(args.out) if args.out else _out(run, f"frame_{int(f['seq']):06d}.png")
    cv2.imwrite(str(path), canvas)
    print(f"seq {f['seq']} (t={f['t_s']}s), 검출 {len(ds)}개 → {path}")
    if args.show:
        cv2.imshow("frame", canvas)
        cv2.waitKey(0)


# ---------------------------------------------------------------- sheet
def cmd_sheet(args):
    run, frames, dets, _, _ = load(args.run)
    t_end = fnum(frames[-1]["t_s"], 0)
    tiles = []
    t = 0.0
    while t <= t_end + 1e-6:
        img, _ = render(run, _nearest(frames, t=t), dets)
        tiles.append(cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2)))
        t += args.every
    cols = args.cols
    th, tw = tiles[0].shape[:2]
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.zeros((rows * th, cols * tw, 3), np.uint8)
    for i, tile in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = tile
    path = Path(args.out) if args.out else _out(run, f"sheet_every{args.every:g}s.jpg")
    cv2.imwrite(str(path), sheet)
    print(f"{len(tiles)}칸 ({args.every:g}s 간격) → {path}")


# ---------------------------------------------------------------- timeline
def _plot(ax_img, xs, ys, title, color, x_max):
    h, w = ax_img.shape[:2]
    l, r, t, b = 50, 10, 18, 22
    cv2.putText(ax_img, title, (l, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1, cv2.LINE_AA)
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if not pts:
        return
    lo, hi = min(p[1] for p in pts), max(p[1] for p in pts)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    cv2.rectangle(ax_img, (l, t), (w - r, h - b), (90, 90, 90), 1)
    for frac in (0, 0.5, 1):
        v = lo + (hi - lo) * frac
        y = int(h - b - frac * (h - b - t))
        cv2.putText(ax_img, f"{v:.4g}", (2, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (180, 180, 180), 1)
    for s in range(0, int(x_max) + 1, max(int(x_max // 10), 1)):
        x = int(l + s / x_max * (w - l - r)) if x_max else l
        cv2.putText(ax_img, f"{s}", (x - 6, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (180, 180, 180), 1)
    poly = np.array([[int(l + x / x_max * (w - l - r)) if x_max else l,
                      int(h - b - (y - lo) / (hi - lo) * (h - b - t))] for x, y in pts], np.int32)
    cv2.polylines(ax_img, [poly], False, color, 1, cv2.LINE_AA)


def cmd_timeline(args):
    run, frames, _, tele, _ = load(args.run)
    ft = [fnum(f["t_s"], 0) for f in frames]
    tt = [fnum(t["t_s"], 0) for t in tele]
    x_max = max(ft + tt + [1])
    series = [
        (ft, [fnum(f["fps_inst"]) for f in frames], "fps_inst [fps]", (0, 200, 255)),
        (ft, [fnum(f["latency_ms"]) for f in frames], "latency_ms [ms]", (255, 160, 0)),
        (ft, [fnum(f["det_count"]) for f in frames], "det_count", (0, 255, 0)),
        (ft, [fnum(f["nearest_z_mm"]) for f in frames], "nearest_z_mm [mm]", (255, 0, 255)),
        (tt, [fnum(t["temp_avg"]) for t in tele], "temp_avg [C]", (0, 0, 255)),
        (tt, [fnum(t["cpu_css_pct"]) for t in tele], "cpu_css_pct [%]", (255, 255, 0)),
    ]
    ph, pw = 150, 900
    canvas = np.zeros((ph * len(series) + 20, pw, 3), np.uint8)
    for i, (xs, ys, title, color) in enumerate(series):
        _plot(canvas[i * ph:(i + 1) * ph], xs, ys, title, color, x_max)
    cv2.putText(canvas, "t [s]", (pw // 2, canvas.shape[0] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    path = Path(args.out) if args.out else _out(run, "timeline.png")
    cv2.imwrite(str(path), canvas)
    print(f"그래프 {len(series)}개 → {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("summary")
    p.add_argument("run")
    p.set_defaults(fn=cmd_summary)
    p = sub.add_parser("frame")
    p.add_argument("run")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--t", type=float, help="시각 [s]")
    g.add_argument("--seq", type=int, help="프레임 순번")
    p.add_argument("--out")
    p.add_argument("--show", action="store_true")
    p.set_defaults(fn=cmd_frame)
    p = sub.add_parser("sheet")
    p.add_argument("run")
    p.add_argument("--every", type=float, default=10.0, help="간격 [s]")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("timeline")
    p.add_argument("run")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_timeline)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
