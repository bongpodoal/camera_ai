#!/usr/bin/env python3
r"""과제용 CAN 수신 로거 (Windows 노트북 + Vector VN1630A). CANoe Logging 이 없을 때, 또는 나란히 쓴다.

시간축 = 이 노트북(Vector 하드웨어)이 프레임을 받은 시각 하나. 첫 프레임 = 0, 정수 ms (t_axis_ms).
카메라·PC 시계는 CAN 에 실리지 않는다 (can_msgs.py 규칙).

하는 일
    1) 받은 프레임을 canoe.asc 에 그대로 저장한다 (1초마다 디스크에 반영 → 강제 종료해도 거의 안 잃음)
    2) 끝나면 canoe.asc 에서 아래를 만든다 (--summarize 로 나중에 다시 만들 수도 있다)
         FRAME_STATUS.csv / DET_BOX.csv / PERF.csv   메시지별 값 + 실행 번호 + 시간열
                                                     (FRAME_STATUS·DET_BOX 는 t_axis_ms, PERF 는 t_axis_s = 정수 초)
         runs_summary.csv / .md                      실행(모델 × Raw)별 비교표
    3) 5초마다 진행 상황을 한 줄 출력한다

종료: Ctrl+C, --duration, --idle-exit (프레임이 N초 끊기면 끝), 또는 출력 폴더에 STOP 파일 만들기
실행을 나누는 규칙은 analyze.py 와 같다 (ModelId·RawOn 이 바뀌거나 5초 넘게 끊기면 새 실행).

예)  python canoe_logger.py --idle-exit 60
     (저장 위치 기본값: 바탕화면\can_logs\<날짜_시각>)
     python canoe_logger.py --summarize "%USERPROFILE%\Desktop\can_logs\20261006_220000"
"""
import argparse
import bisect
import csv
import json
import signal
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import can

from analyze import label_names, split_segments
from can_msgs import BITS_PER_FRAME, ID_DET, ID_FRAME, ID_PERF, MODEL_NAMES, decode, open_bus

HERE = Path(__file__).resolve().parent
LOG_DIR_NAME = "can_logs"     # 바탕화면 아래 이 폴더에 실행마다 하위 폴더를 만든다


def desktop_dir():
    """윈도우의 실제 바탕화면 경로 (OneDrive 로 옮겨져 있어도 맞게). 못 찾으면 이 폴더 옆 logs."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:   # 0x10 = CSIDL_DESKTOPDIRECTORY
            return Path(buf.value)
    except (ImportError, AttributeError, OSError):
        pass
    home = Path.home() / "Desktop"
    return home if home.is_dir() else HERE / "logs"


TAIL_S = 1.0     # 실행의 마지막 FRAME_STATUS 뒤 이 시간 안에 온 DET_BOX/PERF 는 그 실행 것으로 본다


def med(v, nd=2):
    return round(statistics.median(v), nd) if v else ""


def pct(v, p):
    if not v:
        return ""
    s = sorted(v)
    return round(s[min(len(s) - 1, int(len(s) * p / 100))], 2)


def seq_missing(seqs):
    """Seq(0~65535 순환) 가 건너뛴 개수 (카메라가 버린 것 + CAN 으로 잃은 것의 합)."""
    return seq_gaps(seqs, [0] * len(seqs))[0]


def seq_gaps(seqs, gaps):
    """(건너뛴 총수, 카메라가 버렸다고 SeqGap 으로 알린 수, CAN 으로 잃은 수).
    SeqGap = 카메라가 직전에 버린 프레임 수(송신 쪽이 센 값, 최대 15). Seq 가 건너뛴 곳의 SeqGap 만큼은 카메라 탓, 나머지는 CAN 결번."""
    total = cam = 0
    for a, b, g in zip(seqs, seqs[1:], gaps[1:]):
        d = (b - a) % 65536
        if 1 < d < 32768:
            miss = d - 1
            flagged = min(int(g), miss)
            total += miss
            cam += flagged
    return total, cam, total - cam


def record(a, out):
    kw = {} if a.interface == "virtual" else {"bitrate": a.bitrate}
    if a.fd and a.interface != "virtual":
        kw.update(fd=True, data_bitrate=a.data_bitrate)
    if a.app_name:
        kw["app_name"] = a.app_name
    channel = int(a.channel) if str(a.channel).isdigit() else a.channel
    bus = open_bus(a.interface, channel, **kw)
    writer = can.ASCWriter(str(out / "canoe.asc"))
    try:                                               # 이 프로세스가 도는 동안만 절전 방지 요청 (전원 설정은 안 바꿈, 끝나면 자동 해제)
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except (ImportError, AttributeError, OSError):
        pass
    if a.interface == "vector":
        ts_source = ("VN1630A 하드웨어 수신 시각 (Vector XL 드라이버 이벤트 timeStamp, ns). 프레임 간 간격과 t_axis_ms 는 이 하드웨어 시각이고, "
                     "절대 시각(first_frame_abs_*)의 기준점만 버스를 연 순간의 PC 시계(PC 시계 - xlGetSyncTime)")
    else:
        ts_source = f"python-can {a.interface} 인터페이스의 msg.timestamp (하드웨어 시각 아님일 수 있음)"
    meta = dict(logger="canoe_logger.py", start_wallclock=datetime.now().isoformat(timespec="milliseconds"),
                interface=a.interface, channel=str(a.channel), bitrate=a.bitrate, fd=a.fd, python_can=can.__version__,
                timestamp_source=ts_source, receiver="CANoe 대체 로거 (CANoe 로 받은 것이 아님)")
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")

    stop = []
    for name in ("SIGINT", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.append(1))

    counts, cur = Counter(), "-"
    t_begin = time.monotonic()
    last_rx = last_flush = last_print = t_begin
    first_wall = first_abs = last_abs = first_delay = None
    print(f"수신 시작: {a.interface} ch{a.channel} {a.bitrate} bps → {out}", flush=True)
    while not stop:
        msg = bus.recv(timeout=0.2)
        now = time.monotonic()
        if msg is not None:
            writer.on_message_received(msg)
            last_rx = now
            if first_wall is None:
                first_wall = datetime.now().isoformat(timespec="milliseconds")
                first_abs = msg.timestamp
                first_delay = now - t_begin          # 로거를 켠 뒤 첫 프레임까지 (= 송신 시작 지연 + 켠 시각 차이)
            last_abs = msg.timestamp
            if msg.is_error_frame:
                counts["error"] += 1
            else:
                counts[hex(msg.arbitration_id)] += 1
                if msg.arbitration_id == ID_FRAME:
                    v = decode(msg)[1]
                    cur = f"{MODEL_NAMES.get(int(v['ModelId']), v['ModelId'])} raw {'on' if v['RawOn'] else 'off'} seq {int(v['Seq'])}"
        if now - last_flush >= 1.0:
            writer.file.flush()
            last_flush = now
        if now - last_print >= 5.0:
            last_print = now
            print(f"[{now - t_begin:6.0f}s] 0x300 {counts[hex(ID_FRAME)]} · 0x310 {counts[hex(ID_DET)]} · "
                  f"0x320 {counts[hex(ID_PERF)]} · 에러 {counts['error']} · 현재 {cur}", flush=True)
        if a.duration and now - t_begin >= a.duration:
            break
        if a.idle_exit and first_wall and now - last_rx >= a.idle_exit:
            print(f"{a.idle_exit:.0f}초 동안 프레임 없음 → 종료", flush=True)
            break
        if (out / "STOP").exists():
            print("STOP 파일 발견 → 종료", flush=True)
            break
    writer.stop()
    bus.shutdown()
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)    # ES_CONTINUOUS 만 = 절전 방지 해제
    except (NameError, AttributeError, OSError):
        pass
    meta.update(first_frame_wallclock=first_wall, end_wallclock=datetime.now().isoformat(timespec="milliseconds"),
                counts=dict(counts))
    if first_abs is not None:
        meta.update(first_frame_abs_s=round(first_abs, 6), last_frame_abs_s=round(last_abs, 6),
                    first_frame_abs_iso=datetime.fromtimestamp(first_abs).isoformat(timespec="milliseconds"),
                    first_frame_s=0.0, last_frame_s=round(last_abs - first_abs, 3),
                    rx_duration_s=round(last_abs - first_abs, 3), logger_start_to_first_frame_s=round(first_delay, 1))
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")


def summarize(out, bitrate=500000):
    """canoe.asc 하나에서 모든 표를 만든다."""
    msgs = [m for m in can.LogReader(str(out / "canoe.asc"))]
    if not msgs:
        print("로그가 비어 있음")
        return 1
    t0 = min(m.timestamp for m in msgs)
    meta_path = out / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    base_abs = meta.get("first_frame_abs_s")      # 첫 프레임의 절대 시각 (record 가 적어 둠)
    if base_abs is None:                          # 예전 로그: .asc 머리의 "Begin Triggerblock <시각>" 이 첫 프레임 시각
        with open(out / "canoe.asc", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("Begin Triggerblock"):
                    try:
                        base_abs = datetime.strptime(line.split("Triggerblock", 1)[1].strip(), "%a %b %d %H:%M:%S.%f %Y").timestamp()
                    except ValueError:
                        pass
                    break
    frames, dets, perfs, errors = [], [], [], 0
    for m in msgs:
        if m.is_error_frame:
            errors += 1
        elif m.arbitration_id == ID_FRAME:
            frames.append((m.timestamp, decode(m)[1]))
        elif m.arbitration_id == ID_DET:
            dets.append((m.timestamp, decode(m)[1]))
        elif m.arbitration_id == ID_PERF:
            perfs.append((m.timestamp, decode(m)[1]))
    segs = split_segments(frames)
    spans = [(s[0][0], s[-1][0]) for s in segs]

    def run_of(ts):
        """ts 가 몇 번째 실행에 속하는가 (없으면 0)."""
        for i, (a, b) in enumerate(spans):
            nxt = spans[i + 1][0] if i + 1 < len(spans) else float("inf")
            if a <= ts <= b + TAIL_S and ts < nxt:
                return i + 1
        return 0

    def tms(ts):
        return round((ts - t0) * 1000)

    info = {}
    for i, seg in enumerate(segs, 1):
        model = MODEL_NAMES.get(seg[0][2][0], str(seg[0][2][0]))
        info[i] = (model, "on" if seg[0][2][1] else "off")

    with open(out / "FRAME_STATUS.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run", "model", "raw", "t_axis_ms", "canoe_ts_s", "interval_ms", "Seq", "DetCount", "Fps", "EdgeMs", "SeqGap"])
        for i, seg in enumerate(segs, 1):
            prev = None
            for ts, v, _ in seg:
                w.writerow([i, *info[i], tms(ts), f"{ts:.6f}", round((ts - prev) * 1000, 3) if prev else "",
                            int(v["Seq"]), int(v["DetCount"]), v["Fps"], v["EdgeMs"], int(v["SeqGap"])])
                prev = ts
    with open(out / "DET_BOX.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run", "t_axis_ms", "canoe_ts_s", "SeqLo", "Index", "Label", "class", "Conf", "Cx", "Cy", "W", "H"])
        for ts, v in dets:
            r = run_of(ts)
            names = label_names(info[r][0]) if r else []
            lab = int(v["Label"])
            w.writerow([r, tms(ts), f"{ts:.6f}", int(v["SeqLo"]), int(v["Index"]), lab,
                        names[lab] if lab < len(names) else "", v["Conf"], v["Cx"], v["Cy"], v["W"], v["H"]])
    # PERF 시각마다 "그 초의 마지막 완결 프레임" 값을 붙인다 (CAN 메시지는 그대로, 이미 받은 FRAME_STATUS·DET_BOX 를 합침)
    frame_ts = [ts for ts, _ in frames]
    frame_boxes = {}                                   # 프레임 번호(목록 위치) -> 그 프레임의 DET_BOX 들
    for ts, v in dets:
        k = bisect.bisect_right(frame_ts, ts) - 1      # 이 박스 직전의 FRAME_STATUS
        if k >= 0 and int(v["SeqLo"]) == int(frames[k][1]["Seq"]) % 16:
            frame_boxes.setdefault(k, []).append((ts, v))

    def last_complete_frame(perf_ts, run_start):
        """PERF 수신 시각 이전의 마지막 '완결' 프레임. 완결 = 그 시각까지 DET_BOX 를 min(DetCount, 8) 개 이상 받음."""
        k = bisect.bisect_right(frame_ts, perf_ts) - 1
        for _ in range(5):                             # 박스를 잃은 프레임이 연달아 있어도 5개까지만 거슬러 올라감
            if k < 0 or frame_ts[k] < run_start:
                return None, []
            got = [bv for bts, bv in frame_boxes.get(k, []) if bts <= perf_ts]
            if len(got) >= min(int(frames[k][1]["DetCount"]), 8):
                return k, got
            k -= 1
        return None, []

    perf_frame_seqs = {}                               # 실행 -> PERF 행마다의 frame_seq (없으면 None), 요약의 검사용
    with open(out / "PERF.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        # PERF 만 시간열이 정수 초: t_axis_s = (실행의 첫 0x300 수신 시각 기준) 수신 시각의 소수점 버림 (사용자 요청)
        w.writerow(["run", "t_axis_s", "canoe_ts_s", "PcMs", "PostMs", "EthKBps", "CanLoadPct", "DroppedTotal",
                    "frame_seq", "frame_ts_s", "edge_ms", "det_count",
                    "box_class", "box_label", "box_conf", "box_cx", "box_cy", "box_w", "box_h"])
        for ts, v in perfs:
            r = run_of(ts)
            k, got = last_complete_frame(ts, spans[r - 1][0]) if r else (None, [])
            extra = [""] * 11
            if k is not None:
                fv = frames[k][1]
                b0 = next((bv for bv in got if int(bv["Index"]) == 0), None)          # 박스 Index 0 = 가장 신뢰도 높은 박스
                names = label_names(info[r][0])
                extra = [int(fv["Seq"]), f"{frame_ts[k]:.6f}", fv["EdgeMs"] if fv["EdgeMs"] > 0 else "", int(fv["DetCount"])]
                if b0 is not None:
                    lab = int(b0["Label"])
                    extra += [names[lab] if lab < len(names) else "", lab, b0["Conf"], b0["Cx"], b0["Cy"], b0["W"], b0["H"]]
                else:
                    extra += [""] * 7
            if r:
                perf_frame_seqs.setdefault(r, []).append(extra[0] if extra[0] != "" else None)
            w.writerow([r, int(ts - spans[r - 1][0]) if r else "", f"{ts:.6f}", v["PcMs"], v["PostMs"], v["EthKBps"],
                        v["CanLoadPct"], int(v["DroppedTotal"]), *extra])

    rows = []
    for i, seg in enumerate(segs, 1):
        model, raw = info[i]
        a, b = spans[i - 1]
        span = max(b - a, 1e-9)
        vals = [v for _, v, _ in seg]
        iv = [(seg[k][0] - seg[k - 1][0]) * 1000 for k in range(1, len(seg))]
        iv2 = iv[2:]                                    # 첫 2프레임 이후의 간격 (시작 직후 워밍업 제외)
        my_dets = [v for ts, v in dets if run_of(ts) == i]
        my_perf_all = [v for ts, v in perfs if run_of(ts) == i]
        perf_secs = [int(ts - a) for ts, v in perfs if run_of(ts) == i]       # PERF 의 t_axis_s (정수 초)
        perf_dup = len(perf_secs) - len(set(perf_secs))                        # 같은 초가 두 번 나온 개수
        perf_missing = (max(perf_secs) - min(perf_secs) + 1 - len(set(perf_secs))) if perf_secs else ""   # 최소~최대 사이 빠진 초
        pfs = perf_frame_seqs.get(i, [])
        seqs_ok = [s for s in pfs if s is not None]
        perf_frame_blank = len(pfs) - len(seqs_ok)                              # 붙일 완결 프레임이 없던 PERF 행 수
        perf_frame_stalls = sum(1 for p, q in zip(seqs_ok, seqs_ok[1:]) if not 0 < (q - p) % 65536 < 32768)   # frame_seq 가 늘지 않은 횟수
        my_perf = my_perf_all[1:] if len(my_perf_all) > 2 else my_perf_all   # 첫 PERF 는 워밍업 값이라 통계에서 제외
        edge = [v["EdgeMs"] for v in vals if v["EdgeMs"] > 0]                # EdgeMs 0 = 값 없음 (시작 직후 2프레임)
        fps10 = [round(sum(1 for ts, _, _ in seg if a + 10 * w <= ts < a + 10 * (w + 1)) / 10, 2)
                 for w in range(int(span // 10))]       # 꽉 찬 10초 구간만 (마지막 부분 구간은 뺌)
        gap_before = round(a - spans[i - 2][1], 1) if i > 1 else ""
        wall = (datetime.fromtimestamp(base_abs + (a - t0)).isoformat(timespec="milliseconds") if base_abs else "")
        n_msgs = sum(1 for m in msgs if a <= m.timestamp <= b + TAIL_S and run_of(m.timestamp) == i and not m.is_error_frame)
        names = label_names(model)
        cnt = Counter(int(v["Label"]) for v in my_dets)
        top = ", ".join(f"{names[k] if k < len(names) else k}:{n}" for k, n in cnt.most_common(5))
        all_classes = ", ".join(f"{names[k] if k < len(names) else k}:{n}" for k, n in sorted(cnt.items()))
        det_total = sum(int(v["DetCount"]) for v in vals)                         # 칩이 낸 검출 수 합
        expected = sum(min(int(v["DetCount"]), 8) for v in vals)                  # DET_BOX 는 프레임당 최대 8개만 보냄 (max_dets 8)
        rows.append(dict(
            run=i, model=model, raw=raw, t_start_ms=tms(a), t_end_ms=tms(b), t_start_wall_iso=wall, gap_before_s=gap_before,
            duration_s=round(span, 1),
            frames_rx=len(seg), seq_missing=seq_gaps([int(v["Seq"]) for v in vals], [v["SeqGap"] for v in vals])[0],
            cam_dropped_seqgap=seq_gaps([int(v["Seq"]) for v in vals], [v["SeqGap"] for v in vals])[1],
            can_lost_frames=seq_gaps([int(v["Seq"]) for v in vals], [v["SeqGap"] for v in vals])[2],
            n_0x300=len(seg), n_0x310=len(my_dets), n_0x320=len(my_perf_all), perf_dup_s=perf_dup, perf_missing_s=perf_missing,
            perf_frame_blank=perf_frame_blank, perf_frame_stalls=perf_frame_stalls,
            fps_rx=round((len(seg) - 1) / span, 2) if len(seg) > 1 else "", fps_10s=";".join(str(x) for x in fps10),
            fps_cam=med([v["Fps"] for v in vals]),
            interval_ms_median=med(iv), interval_ms_p95=pct(iv, 95), interval_ms_std=round(statistics.pstdev(iv), 2) if len(iv) > 1 else "",
            interval_ms_median_skip2=med(iv2), interval_ms_std_skip2=round(statistics.pstdev(iv2), 2) if len(iv2) > 1 else "",
            edge_ms=med(edge), edge_zero_frames=len(vals) - len(edge), pc_ms=med([v["PcMs"] for v in my_perf]),
            post_ms=med([v["PostMs"] for v in my_perf]), eth_KBps=med([v["EthKBps"] for v in my_perf]),
            can_load_pct_rx=round(100 * n_msgs * BITS_PER_FRAME / (span + TAIL_S) / bitrate, 2),
            can_load_pct_tx=med([v["CanLoadPct"] for v in my_perf]),
            dropped_total=int(my_perf[-1]["DroppedTotal"]) if my_perf else "",
            det_boxes_rx=len(my_dets), det_boxes_expected=expected, det_count_sum=det_total,
            frames_det_over8=sum(1 for v in vals if int(v["DetCount"]) > 8),
            frames_with_det_pct=round(100 * sum(1 for v in vals if v["DetCount"]) / len(vals), 1),
            det_per_frame=round(det_total / len(vals), 2),
            conf_mean=round(statistics.mean(v["Conf"] for v in my_dets), 3) if my_dets else "", top_classes=top,
            class_counts=all_classes))

    if rows:
        with open(out / "runs_summary.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        cols = ["run", "model", "raw", "duration_s", "frames_rx", "seq_missing", "cam_dropped_seqgap", "can_lost_frames", "fps_rx", "fps_10s", "interval_ms_std_skip2",
                "edge_ms", "edge_zero_frames", "pc_ms", "post_ms", "eth_KBps", "can_load_pct_rx", "n_0x300", "n_0x310",
                "n_0x320", "perf_dup_s", "perf_missing_s", "perf_frame_blank", "perf_frame_stalls", "det_boxes_rx", "det_boxes_expected", "frames_with_det_pct", "conf_mean", "class_counts"]
        with open(out / "runs_summary.md", "w", encoding="utf-8") as fh:
            fh.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
            for r in rows:
                fh.write("| " + " | ".join(str(r[k]) for k in cols) + " |\n")
    meta["definitions"] = dict(
        det_boxes_expected="sum(min(DetCount, 8)) — DET_BOX 는 프레임당 최대 8개만 전송되므로 기대값도 8개로 자름. 칩 검출 수의 합은 det_count_sum, 8개 넘은 프레임 수는 frames_det_over8",
        t_axis_ms="첫 프레임 = 0, VN1630A 수신 시각, 정수 ms (FRAME_STATUS.csv·DET_BOX.csv)",
        t_axis_s="PERF.csv 만: 실행의 첫 0x300 수신 시각 기준 수신 시각의 소수점 버림 정수 초 (예 1.05 → 1). canoe_ts_s 는 소수 초 그대로",
        n_0x320="PERF 는 프레임과 무관한 1초 타이머로 첫 프레임 기준 k초+50ms 에 송신 → 개수 = 정수 초 구간 수 (30초 run 이면 약 29~30개)",
        perf_dup_s_perf_missing_s="PERF t_axis_s 의 중복 개수 / 최소~최대 사이 빠진 초 (둘 다 0 이면 1,2,3… 연속)",
        PERF_frame_columns=("PERF.csv 의 frame_seq·frame_ts_s·edge_ms·det_count·box_*: 그 초(PERF 수신 시각)의 '마지막 완결 프레임' 값이며 평균·집계가 아님. "
                            "완결 프레임 = PERF 수신 시각 이전에 받은 FRAME_STATUS 중 DET_BOX 를 min(DetCount, 8)개 이상 이미 받은 마지막 것 "
                            "(DET_BOX 는 SeqLo=Seq 하위 4비트로 짝지음). box_* 는 DET_BOX Index 0(최고 신뢰도), 검출 0개면 빈 칸. "
                            "edge_ms 는 EdgeMs=0(값 없음)이면 빈 칸. CAN 메시지·DBC 는 바뀌지 않았고 로거가 이미 받은 값을 합침"),
        perf_frame_blank_perf_frame_stalls="붙일 완결 프레임이 없던 PERF 행 수 / frame_seq 가 이전 PERF 보다 늘지 않은 횟수 (0 이면 PERF 마다 프레임이 앞으로 감)",
        fps_rx="(0x300 개수 - 1) / (첫~마지막 0x300 시각). 송신 시작 지연은 빠짐. 카메라 쪽 fps_avg 는 시작 지연이 섞여 더 낮게 나올 수 있음",
        fps_10s="실행 시작부터 꽉 찬 10초 구간별 fps (구간이 없으면 빈 칸)",
        seq_missing="Seq 가 건너뛴 총 개수 = 카메라가 버린 것 + CAN 으로 잃은 것",
        cam_dropped_seqgap="Seq 가 건너뛴 곳의 SeqGap(카메라가 버렸다고 알린 수, 최대 15) 합 = 카메라 입력 큐가 버린 프레임",
        can_lost_frames="seq_missing - cam_dropped_seqgap = CAN 으로 잃은 프레임 (이 값이 진짜 CAN 결번, 0 이어야 정상)",
        edge_ms="EdgeMs 가 0 인 프레임(시작 직후 값 없음) 제외한 중앙값, 0 이었던 프레임 수는 edge_zero_frames",
        pc_ms_post_ms_eth_KBps="PERF 의 중앙값, 실행의 첫 PERF 는 워밍업이라 제외 (PERF 가 3개 이하면 전부 사용)",
        interval_ms_skip2="첫 2프레임 이후 간격만의 통계",
        can_load_pct_rx="수신 개수 x 135비트 / 구간 / 비트레이트 (최악 근사)",
        t_start_wall_iso="실행 시작의 절대 시각 = 첫 프레임 절대 시각 + t_start_ms",
        gap_before_s="앞 실행의 마지막 프레임부터 이 실행의 첫 프레임까지 (카메라 재시작 대기 등)")
    meta_path.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    other = len(msgs) - len(frames) - len(dets) - len(perfs) - errors
    print(f"프레임 {len(msgs)}개 (0x300 {len(frames)} · 0x310 {len(dets)} · 0x320 {len(perfs)} · 그 밖 {other} · 에러 {errors}) → 실행 {len(segs)}개")
    for r in rows:
        print(f"  실행 {r['run']}: {r['model']} raw {r['raw']} · {r['duration_s']}s · 수신 {r['frames_rx']} (결번 {r['seq_missing']}) · "
              f"{r['fps_rx']} fps · 엣지 {r['edge_ms']} ms · 박스 {r['det_boxes_rx']}/{r['det_boxes_expected']}")
    print(f"→ {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", default="vector")
    ap.add_argument("--channel", default="0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--fd", action="store_true")
    ap.add_argument("--data-bitrate", type=int, default=2000000)
    ap.add_argument("--app-name", help="vector 전용: Vector Hardware Config 에 등록한 응용 이름")
    ap.add_argument("--out-dir", help="기본: 바탕화면\\can_logs\\<날짜_시각>")
    ap.add_argument("--duration", type=float, default=0, help="초 (0 = 무제한)")
    ap.add_argument("--idle-exit", type=float, default=0, help="프레임이 이 초 동안 끊기면 종료 (0 = 끔)")
    ap.add_argument("--summarize", metavar="DIR", help="받지 않고 DIR/canoe.asc 에서 표만 다시 만든다")
    a = ap.parse_args(argv)
    if a.summarize:
        return summarize(Path(a.summarize), a.bitrate)
    out = Path(a.out_dir) if a.out_dir else desktop_dir() / LOG_DIR_NAME / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    record(a, out)
    return summarize(out, a.bitrate)


if __name__ == "__main__":
    raise SystemExit(main())
