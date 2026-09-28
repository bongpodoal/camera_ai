#!/usr/bin/env python3
# ============================================================================
# 카메라가 켜져 있는 동안 "칩이 무엇을, 어떤 주기로 보내는지"를 시간축으로 기록하는 모듈.
# 혼자 실행하는 파일이 아니라, run_yolov6n.py 가 불러서(import) 같이 돈다.
#
# 왜 따로 실행하지 않나?
#   OAK-D는 한 번에 한 프로그램만 연결할 수 있다. 기록 프로그램이 카메라에 따로 붙으면
#   카메라 코드가 연결을 못 한다. 그래서 카메라 코드가 받은 데이터를 이 모듈에 그대로
#   넘겨주고(logger.log), 이 모듈은 받은 시각·주기만 계산해서 파일에 적는다.
#
# 실행하면 minimal_example/runs/<날짜_시각>/ 아래에 세 파일이 생긴다:
#   events.csv    칩에서 받은 메시지 1개당 1행 (시간축 원자료)
#   fps.csv       1초당 1행 (그 1초 동안 모델 연산 몇 번, 프레임 몇 장, 물체 몇 개)
#   summary.json  종료할 때 한 번: 데이터 종류별 개수, 평균 주기, 초당 개수
#                 (interval_basis: device=칩 시계 기준, host=칩 시각이 없어 PC 도착 기준)
#
# 기록하는 데이터 종류(stream):
#   "frame"      신경망이 실제로 본 영상 프레임 (passthrough)
#   "detections" 신경망 결과 (1개 = 모델 연산 1번) → 이 개수로 모델 FPS를 잰다
#   "system"     칩 온도·CPU 사용률 (SystemLogger 노드가 1초마다 보냄)
# ============================================================================

import csv                          # 표 형태(CSV) 파일을 쓰려고
import json                         # 요약(summary.json)을 쓰려고
import time                         # 호스트(PC) 쪽 시간을 재려고
from datetime import datetime       # 폴더 이름에 날짜·시각을 넣으려고
from pathlib import Path            # 파일 경로를 다루려고

import depthai as dai               # 메시지 종류 구분(ImgFrame 등)과 장치 시계(dai.Clock)에 씀

# fps.csv 의 열 순서를 고정하려고 데이터 종류 이름을 미리 정해둔다.
STREAMS = ("frame", "detections", "system")


def _seconds(value):
    """timedelta(시간 간격 객체)를 초 단위 숫자로 바꾼다. 값이 없으면 빈칸."""
    try:
        seconds = value.total_seconds()
    except Exception:
        return ""
    # 0초는 "칩이 시각을 안 붙여 보냈다"는 뜻이다 (예: SystemLogger 메시지). 없는 값으로 취급.
    return round(seconds, 6) if seconds > 0 else ""


class DataLogger:
    def __init__(self, folder=None):
        # 저장 폴더: 따로 안 주면 이 파일 옆의 runs/날짜_시각/ 에 만든다.
        if folder is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder = Path(__file__).resolve().parent / "runs" / stamp
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

        # 기록 시작 시각. 이후 모든 host_time_s 는 "시작 후 몇 초"로 적는다.
        # time.monotonic() 은 컴퓨터 시계를 바꿔도 뒤로 가지 않는 시계라 간격 재기에 알맞다.
        self.start = time.monotonic()

        # --- events.csv : 받은 메시지 1개당 1행 ---
        self.events_file = open(self.folder / "events.csv", "w", newline="")
        self.events = csv.writer(self.events_file)
        self.events.writerow([
            "host_time_s",          # PC가 이 메시지를 받은 시각 (시작 후 초)
            "stream",               # 데이터 종류 (frame / detections / system)
            "seq",                  # 칩이 붙인 순번 (빠진 번호가 있으면 중간에 유실된 것)
            "device_time_s",        # 칩이 이 데이터를 만든 시각 (칩 내부 시계, 초)
            "interval_ms",          # 같은 종류의 직전 메시지와 PC 도착 간격
            "device_interval_ms",   # 같은 종류의 직전 메시지와 칩 생성 간격 (진짜 토출 주기)
            "latency_ms",           # 칩이 만든 뒤 PC가 받기까지 걸린 시간
            "width", "height", "frame_type",        # frame 일 때만
            "n_objects", "objects",                 # detections 일 때만
            "temp_c", "cpu_css_pct", "cpu_mss_pct", # system 일 때만
        ])

        # --- fps.csv : 1초당 1행 ---
        self.fps_file = open(self.folder / "fps.csv", "w", newline="")
        self.fps = csv.writer(self.fps_file)
        # detections_per_s 가 곧 "모델 연산 FPS" 다 (결과 1개 = 연산 1번).
        self.fps.writerow(["time_s"] + [f"{s}_per_s" for s in STREAMS] + ["objects_per_s"])

        # 종류별로 "직전 메시지를 받은 시각"을 기억해 간격을 계산한다.
        self.last_host = {}      # stream -> 직전 PC 도착 시각
        self.last_device = {}    # stream -> 직전 칩 생성 시각
        # 종료 시 요약용: 종류별 개수와 칩 기준 간격 목록
        self.counts = {}
        self.device_intervals = {}
        self.host_intervals = {}
        # 1초 구간 집계용
        self.window_start = 0.0
        self.window_counts = {}
        self.window_objects = 0

        print(f"데이터 기록 시작: {self.folder}")

    def log(self, stream, message):
        """카메라 코드가 큐에서 꺼낸 메시지를 받을 때마다 부른다."""
        now = time.monotonic() - self.start

        # 칩이 메시지에 붙여 보낸 정보: 순번, 칩 시계 기준 생성 시각
        seq = message.getSequenceNum()
        device_time = _seconds(message.getTimestampDevice())

        # 같은 종류의 직전 메시지와의 간격 (첫 메시지는 비교 대상이 없어 빈칸)
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

        # 지연: dai.Clock.now() 는 PC 시계를, getTimestamp() 는 칩 시각을 PC 시계로 맞춘 값을 준다.
        # 둘의 차이 = 칩에서 만들어진 뒤 PC 손에 들어오기까지 걸린 시간.
        latency = ""
        if device_time != "":
            latency = round((dai.Clock.now() - message.getTimestamp()).total_seconds() * 1000, 2)

        # 종류별로 내용 요약 (해당 없는 칸은 빈칸)
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

        # 1초가 지났으면 그 구간의 초당 개수를 fps.csv 에 한 줄 쓰고 화면에도 보여준다.
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
            # 1초마다 파일에 실제로 써서, 실행 중에도 파일을 열어 볼 수 있게 한다.
            self.events_file.flush()
            self.fps_file.flush()

    def close(self):
        """카메라 코드가 끝날 때 부른다. 파일을 닫고 summary.json 을 쓴다."""
        duration = time.monotonic() - self.start
        summary = {"duration_s": round(duration, 2), "streams": {}}
        for stream, count in self.counts.items():
            intervals = self.device_intervals.get(stream, [])
            info = {"count": count, "interval_basis": "device"}
            # 칩 시각이 없는 종류(system)는 PC 도착 간격으로 대신 계산한다.
            if not intervals:
                intervals = self.host_intervals.get(stream, [])
                info["interval_basis"] = "host"
            if intervals:
                # 평균 주기(ms)와 그 역수인 초당 개수(Hz). 칩 시계 기준이라 PC 쪽 지연에 흔들리지 않는다.
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
