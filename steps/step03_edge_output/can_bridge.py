"""OAK-D 토출 데이터를 CAN 프레임으로 바꿔 보내고, 받아서 다시 푼다.

OAK-D PoE에는 CAN 포트가 없다 (연결은 PoE 이더넷뿐). 그래서 경로는
    OAK-D --이더넷--> 호스트(이 스크립트) --USB-CAN 어댑터--> CAN 버스
이고, 메시지 형식은 oakd_edge.dbc가 정의한다.

    python3 can_bridge.py dbc                                   # 메시지 표
    python3 can_bridge.py selftest [--run runs/<폴더>]           # 가상 버스 왕복 검증 (하드웨어 불필요)
    python3 can_bridge.py replay runs/<폴더> --interface socketcan --channel vcan0
    python3 can_bridge.py listen --interface socketcan --channel vcan0 --seconds 10 --out rx.csv
"""
import argparse
import csv
import time
from pathlib import Path

import can
import cantools

from common import fnum, read_csv

HERE = Path(__file__).resolve().parent
DB = cantools.database.load_file(str(HERE / "oakd_edge.dbc"))
MSG = {m.name: m for m in DB.messages}
BITS_PER_FRAME = 135      # 11비트 ID + 8바이트 데이터, 비트 스터핑 최악 근사


def _clamp(msg_name, values):
    msg = MSG[msg_name]
    out = {}
    for s in msg.signals:
        v = values.get(s.name, 0)
        v = 0 if v in (None, "") else float(v)
        lo, hi = s.minimum, s.maximum
        out[s.name] = min(max(v, lo), hi)
    return out


def _msg(name, values):
    m = MSG[name]
    return can.Message(arbitration_id=m.frame_id, is_extended_id=False,
                       data=m.encode(_clamp(name, values), strict=False))


# ---------------------------------------------------------------- 인코딩
def encode_frame(frow, drows, max_dets=8):
    """frames.csv 1행 + 그 프레임의 detections 행 → CAN 메시지 목록."""
    seq = int(fnum(frow["seq"], 0))
    nz = fnum(frow.get("nearest_z_mm"))
    msgs = [_msg("FRAME_STATUS", dict(
        Seq=seq % 65536, DetCount=len(drows), Fps=fnum(frow.get("fps_inst"), 0),
        LatencyMs=fnum(frow.get("latency_ms"), 0), SeqGap=fnum(frow.get("seq_gap"), 0),
        NearestZ=nz / 1000 if nz else 0))]
    top = sorted(drows, key=lambda d: -fnum(d["confidence"], 0))[:min(max_dets, 16)]
    for i, d in enumerate(top):
        x0, y0, x1, y1 = (fnum(d[k], 0) for k in ("xmin", "ymin", "xmax", "ymax"))
        msgs.append(_msg("DET_BOX", dict(SeqLo=seq % 16, Index=i, Label=fnum(d["label"], 0),
                                         Conf=fnum(d["confidence"], 0), Cx=(x0 + x1) / 2,
                                         Cy=(y0 + y1) / 2, W=x1 - x0, H=y1 - y0)))
        if fnum(d.get("z_mm")) is not None:
            msgs.append(_msg("DET_POS", dict(SeqLo=seq % 16, Index=i, X=fnum(d["x_mm"]),
                                             Y=fnum(d["y_mm"]), Z=fnum(d["z_mm"]))))
    return msgs


def encode_telemetry(t):
    temps = [fnum(t.get(k)) for k in ("temp_css", "temp_mss", "temp_upa", "temp_dss")]
    temps = [v for v in temps if v is not None]

    def pct(u, tot):
        u, tot = fnum(t.get(u)), fnum(t.get(tot))
        return 100 * u / tot if u is not None and tot else 0

    return _msg("DEV_STATUS", dict(
        TempAvg=fnum(t.get("temp_avg"), -40), TempMax=max(temps) if temps else -40,
        CpuCss=fnum(t.get("cpu_css_pct"), 0), CpuMss=fnum(t.get("cpu_mss_pct"), 0),
        DdrUsed=pct("ddr_used_mb", "ddr_total_mb"), CmxUsed=pct("cmx_used_kb", "cmx_total_kb"),
        CssHeap=pct("css_heap_used_kb", "css_heap_total_kb"),
        MssHeap=pct("mss_heap_used_kb", "mss_heap_total_kb")))


def decode(msg):
    m = DB.get_message_by_frame_id(msg.arbitration_id)
    return m.name, m.decode(msg.data, decode_choices=False)


class CanPublisher:
    """edge_logger.py가 기록하면서 동시에 송출할 때 쓴다."""

    def __init__(self, interface, channel, bitrate=500000, max_dets=8):
        kw = {} if interface == "virtual" else {"bitrate": bitrate}
        self.bus = can.Bus(interface=interface, channel=channel, **kw)
        self.max_dets = max_dets
        self.sent = self.errors = 0

    def _send(self, msgs):
        for m in msgs:
            try:
                self.bus.send(m, timeout=0.01)
                self.sent += 1
            except can.CanError:
                self.errors += 1

    def send_frame(self, frow, drows):
        self._send(encode_frame(frow, drows, self.max_dets))

    def send_telemetry(self, t):
        self._send([encode_telemetry(t)])

    def close(self):
        self.bus.shutdown()


# ---------------------------------------------------------------- 기록 불러오기
def load_run(run):
    run = Path(run)
    frames = read_csv(run / "frames.csv")
    dets = {}
    for d in read_csv(run / "detections.csv"):
        dets.setdefault(d["seq"], []).append(d)
    tele = read_csv(run / "telemetry.csv")
    return frames, dets, tele


def timeline(run, max_dets):
    """(t_s, [메시지]) 를 시간순으로."""
    frames, dets, tele = load_run(run)
    events = [(fnum(f["t_s"], 0), encode_frame(f, dets.get(f["seq"], []), max_dets)) for f in frames]
    events += [(fnum(t["t_s"], 0), [encode_telemetry(t)]) for t in tele]
    return sorted(events, key=lambda e: e[0]), frames, dets, tele


# ---------------------------------------------------------------- 명령
def cmd_dbc(args):
    for m in DB.messages:
        print(f"0x{m.frame_id:03X} {m.name:<13} {m.length}B  {m.comment or ''}")
        for s in m.signals:
            sign = "s" if s.is_signed else "u"
            print(f"      {s.name:<10} bit {s.start:>2}+{s.length:<2} {sign}  ×{s.scale} {s.offset:+g}"
                  f"  [{s.minimum}..{s.maximum}] {s.unit or ''}")


def cmd_selftest(args):
    """가상 버스 두 개(송신·수신)로 인코딩 → 전송 → 수신 → 디코딩을 확인한다."""
    if args.run:
        events, frames, dets, tele = timeline(args.run, args.max_dets)
    else:
        f = dict(seq=1234, fps_inst=29.97, latency_ms=41.2, seq_gap=0, nearest_z_mm=6234)
        d = [dict(label=9, confidence=0.87, xmin=0.4, ymin=0.1, xmax=0.44, ymax=0.26,
                  x_mm=-512.3, y_mm=-1500.2, z_mm=6234.0)]
        t = dict(temp_css=45.1, temp_mss=44.2, temp_upa=46.0, temp_dss=44.8, temp_avg=45.0,
                 cpu_css_pct=33.0, cpu_mss_pct=18.0, ddr_used_mb=150, ddr_total_mb=340,
                 cmx_used_kb=2000, cmx_total_kb=2048, css_heap_used_kb=3e4, css_heap_total_kb=8e4,
                 mss_heap_used_kb=1e4, mss_heap_total_kb=4e4)
        events, frames, dets, tele = [(0, encode_frame(f, d)), (0, [encode_telemetry(t)])], [f], {"1234": d}, [t]

    tx = can.Bus(interface="virtual", channel="oakd_selftest")
    rx = can.Bus(interface="virtual", channel="oakd_selftest")
    sent = 0
    for _, msgs in events:
        for m in msgs:
            tx.send(m)
            sent += 1
    got = []
    while True:
        m = rx.recv(timeout=0.2)
        if m is None:
            break
        got.append(decode(m))
    tx.shutdown()
    rx.shutdown()

    # 원본과 비교 (양자화 오차 허용)
    by = {}
    for name, v in got:
        by.setdefault(name, []).append(v)
    errs = {}

    def err(key, a, b):
        errs[key] = max(errs.get(key, 0), abs(a - b))

    for f, v in zip(frames, by.get("FRAME_STATUS", [])):
        err("Seq", fnum(f["seq"]) % 65536, v["Seq"])
        err("DetCount", len(dets.get(str(f["seq"]), [])), v["DetCount"])
    pos = by.get("DET_POS", [])
    all_d = [dd for f in frames for dd in sorted(dets.get(str(f["seq"]), []),
                                                 key=lambda d: -fnum(d["confidence"], 0))[:args.max_dets]]
    for d, v in zip(all_d, by.get("DET_BOX", [])):
        err("Conf", fnum(d["confidence"]), v["Conf"])
        err("Cx", (fnum(d["xmin"]) + fnum(d["xmax"])) / 2, v["Cx"])
    for d, v in zip([d for d in all_d if fnum(d.get("z_mm")) is not None], pos):
        err("Z_mm", fnum(d["z_mm"]), v["Z"])

    dur = max((e[0] for e in events), default=0) or 1
    rate = sent / dur if args.run else float("nan")
    print(f"송신 {sent}  수신 {len(got)}  {'일치' if sent == len(got) else '불일치'}")
    for name in MSG:
        print(f"  {name:<13} {len(by.get(name, [])):>7}개")
    print("최대 오차 (양자화 포함):")
    for k, v in errs.items():
        print(f"  {k:<9} {v:.4g}")
    if args.run:
        for br in (500000, 1000000):
            print(f"버스 점유율 추정 @ {br//1000} kbps: {100 * rate * BITS_PER_FRAME / br:.1f}%  "
                  f"({rate:.0f} 메시지/s)")
    ok = sent == len(got) and errs.get("Seq", 0) == 0 and errs.get("Conf", 0) <= 0.006 \
        and errs.get("Cx", 0) <= 0.0006 and errs.get("Z_mm", 0) <= 0.51
    print("결과:", "통과" if ok else "실패")
    return 0 if ok else 1


def cmd_replay(args):
    events, *_ = timeline(args.run, args.max_dets)
    kw = {} if args.interface == "virtual" else {"bitrate": args.bitrate}
    bus = can.Bus(interface=args.interface, channel=args.channel, **kw)
    t_start = time.monotonic()
    sent = errors = 0
    try:
        for t, msgs in events:
            if args.speed > 0:
                wait = t / args.speed - (time.monotonic() - t_start)
                if wait > 0:
                    time.sleep(wait)
            for m in msgs:
                try:
                    bus.send(m, timeout=0.05)
                    sent += 1
                except can.CanError:
                    errors += 1
    finally:
        bus.shutdown()
    print(f"송신 {sent}, 오류 {errors}, {time.monotonic() - t_start:.1f}s")


def cmd_listen(args):
    kw = {} if args.interface == "virtual" else {"bitrate": args.bitrate}
    bus = can.Bus(interface=args.interface, channel=args.channel, **kw)
    ids = {m.frame_id for m in DB.messages}
    writer = None
    if args.out:
        fh = open(args.out, "w", newline="")
        writer = csv.writer(fh)
        writer.writerow(["t_s", "id", "name", "signals"])
    t0 = time.monotonic()
    counts, last = {}, 0.0
    try:
        while args.seconds <= 0 or time.monotonic() - t0 < args.seconds:
            m = bus.recv(timeout=0.5)
            if m is None or m.arbitration_id not in ids:
                continue
            name, v = decode(m)
            counts[name] = counts.get(name, 0) + 1
            t = time.monotonic() - t0
            if writer:
                writer.writerow([f"{t:.4f}", f"0x{m.arbitration_id:03X}", name,
                                 " ".join(f"{k}={v[k]:g}" for k in v)])
            if name == "FRAME_STATUS" and t - last >= 1.0:
                last = t
                print(f"t={t:6.1f}s  seq={v['Seq']:.0f} det={v['DetCount']:.0f} fps={v['Fps']:.1f} "
                      f"lat={v['LatencyMs']:.0f}ms  누적 {counts}")
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
        if writer:
            fh.close()
    print("수신:", counts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def bus_args(p):
        p.add_argument("--interface", default="socketcan", help="socketcan | virtual | slcan | pcan ...")
        p.add_argument("--channel", default="vcan0")
        p.add_argument("--bitrate", type=int, default=500000)

    p = sub.add_parser("dbc")
    p.set_defaults(fn=cmd_dbc)
    p = sub.add_parser("selftest")
    p.add_argument("--run", help="기록 폴더 (없으면 예시 1프레임)")
    p.add_argument("--max-dets", type=int, default=8)
    p.set_defaults(fn=cmd_selftest)
    p = sub.add_parser("replay")
    p.add_argument("run")
    p.add_argument("--speed", type=float, default=1.0, help="1=원래 속도, 0=최대 속도")
    p.add_argument("--max-dets", type=int, default=8)
    bus_args(p)
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("listen")
    p.add_argument("--seconds", type=float, default=0, help="0=Ctrl+C까지")
    p.add_argument("--out", help="수신 기록 CSV")
    bus_args(p)
    p.set_defaults(fn=cmd_listen)

    args = ap.parse_args()
    raise SystemExit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
