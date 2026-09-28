#!/usr/bin/env python3

import csv
import json
import time
from datetime import datetime
from pathlib import Path

import depthai as dai

STREAMS = ("frame", "detections", "system")


def _seconds(value):
    try:
        seconds = value.total_seconds()
    except Exception:
        return ""
    return round(seconds, 6) if seconds > 0 else ""


class DataLogger:
    def __init__(self, folder=None):
        if folder is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder = Path(__file__).resolve().parent / "runs" / stamp
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

        self.start = time.monotonic()

        self.events_file = open(self.folder / "events.csv", "w", newline="")
        self.events = csv.writer(self.events_file)
        self.events.writerow([
            "host_time_s",
            "stream",
            "seq",
            "device_time_s",
            "interval_ms",
            "device_interval_ms",
            "latency_ms",
            "width", "height", "frame_type",
            "n_objects", "objects",
            "temp_c", "cpu_css_pct", "cpu_mss_pct",
        ])

        self.fps_file = open(self.folder / "fps.csv", "w", newline="")
        self.fps = csv.writer(self.fps_file)
        self.fps.writerow(["time_s"] + [f"{s}_per_s" for s in STREAMS] + ["objects_per_s"])

        self.last_host = {}
        self.last_device = {}

        self.counts = {}
        self.device_intervals = {}
        self.host_intervals = {}

        self.window_start = 0.0
        self.window_counts = {}
        self.window_objects = 0

        print(f"데이터 기록 시작: {self.folder}")

    def log(self, stream, message):
        now = time.monotonic() - self.start

        seq = message.getSequenceNum()
        device_time = _seconds(message.getTimestampDevice())

        interval = ""
        if stream in self.last_host:
            interval = round((now - self.last_host[stream]) * 1000, 2)
            self.host_intervals.setdefault(stream, []).append(interval)
        device_interval = ""
        if stream in self.last_device and device_time != "":
            device_interval = round((device_time - self.last_device[stream]) * 1000, 2)
            self.device_intervals.setdefault(stream, []).append(device_interval)
        self.last_host[stream] = now
        if device_time != "":
            self.last_device[stream] = device_time

        latency = ""
        if device_time != "":
            latency = round((dai.Clock.now() - message.getTimestamp()).total_seconds() * 1000, 2)

        width = height = frame_type = n_objects = objects = temp = cpu_css = cpu_mss = ""
        if isinstance(message, dai.ImgFrame):
            width, height = message.getWidth(), message.getHeight()
            frame_type = str(message.getType()).split(".")[-1]
        elif isinstance(message, dai.ImgDetections):
            n_objects = len(message.detections)
            objects = " ".join(f"{d.label}:{d.confidence:.2f}" for d in message.detections)
            self.window_objects += n_objects
        elif isinstance(message, dai.SystemInformation):
            temp = round(message.chipTemperature.average, 2)
            cpu_css = round(message.leonCssCpuUsage.average * 100, 1)
            cpu_mss = round(message.leonMssCpuUsage.average * 100, 1)

        self.events.writerow([round(now, 4), stream, seq, device_time, interval, device_interval,
                              latency, width, height, frame_type, n_objects, objects,
                              temp, cpu_css, cpu_mss])

        self.counts[stream] = self.counts.get(stream, 0) + 1
        self.window_counts[stream] = self.window_counts.get(stream, 0) + 1

        elapsed = now - self.window_start
        if elapsed >= 1.0:
            rates = [round(self.window_counts.get(s, 0) / elapsed, 2) for s in STREAMS]
            objects_rate = round(self.window_objects / elapsed, 2)
            self.fps.writerow([round(now, 3)] + rates + [objects_rate])
            print(f"[{now:6.1f}s] 모델 연산 {rates[1]:5.1f} fps | 프레임 {rates[0]:5.1f} fps"
                  f" | 물체 {objects_rate:5.1f}개/s")
            self.window_start = now
            self.window_counts = {}
            self.window_objects = 0
            self.events_file.flush()
            self.fps_file.flush()

    def close(self):
        duration = time.monotonic() - self.start
        summary = {"duration_s": round(duration, 2), "streams": {}}
        for stream, count in self.counts.items():
            intervals = self.device_intervals.get(stream, [])
            info = {"count": count, "interval_basis": "device"}
            if not intervals:
                intervals = self.host_intervals.get(stream, [])
                info["interval_basis"] = "host"
            if intervals:
                mean = sum(intervals) / len(intervals)
                info.update(mean_interval_ms=round(mean, 2),
                            min_interval_ms=round(min(intervals), 2),
                            max_interval_ms=round(max(intervals), 2),
                            rate_hz=round(1000 / mean, 2) if mean > 0 else None)
            summary["streams"][stream] = info

        with open(self.folder / "summary.json", "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        self.events_file.close()
        self.fps_file.close()

        print(f"\n기록 종료 ({duration:.1f}s) → {self.folder}")
        for stream, info in summary["streams"].items():
            if "rate_hz" in info:
                print(f"  {stream:10s} {info['count']:6d}개  평균 주기 {info['mean_interval_ms']:7.2f} ms"
                      f"  ({info['rate_hz']:.2f} Hz)")
            else:
                print(f"  {stream:10s} {info['count']:6d}개")
