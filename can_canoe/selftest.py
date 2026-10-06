#!/usr/bin/env python3
"""카메라·CANoe 없이 전체 흐름을 검증한다 (가상 CAN 버스 + canoe_sim 로그 + 가짜 카메라).

네 번 실행(모델 2개 × Raw on/off)을 한 로그에 이어서 찍고, analyze.py 가 실행별로 나눠 짝짓는지 본다.
카메라 시계는 실행마다 다른 ppm 으로 일부러 틀어 놓고, 측정된 ppm 이 맞는지 확인한다.
"""
import csv
import sys
import tempfile
from pathlib import Path

import can

import analyze
import can_demo
from canoe_sim import CanoeSim

root = Path(tempfile.mkdtemp())
log = root / "canoe.asc"
sim = CanoeSim(can.Bus(interface="virtual", channel="selftest"), log)
plan = [("yolov6n", "off", 3000), ("yolov6n", "on", -2000), ("traffic_light", "off", 5000), ("traffic_light", "on", 0)]
rc = []
for i, (model, raw, ppm) in enumerate(plan, 1):
    rc.append(can_demo.main(["--fake", "--fake-ppm", str(ppm), "--model", model, "--raw", raw, "--fps", "10",
                             "--duration", "12", "--interface", "virtual", "--channel", "selftest",
                             "--out-dir", str(root / f"{i}_{model}_{raw}")]))
sim.stop()
arc = analyze.main(["--log", str(log), "--runs-root", str(root)])
cmp_rows = list(csv.DictReader(open(root / "compare.csv")))

fails = []


def check(name, ok):
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(name)


check("can_demo 종료 코드 모두 0", all(r == 0 for r in rc))
check("analyze 종료 코드 0", arc == 0)
check("실행 4개를 짝지음", len(cmp_rows) == 4)
for c, (model, raw, ppm) in zip(cmp_rows, plan):
    tag = f"{model} raw {raw}"
    check(f"{tag}: 송신=수신, 유실 0 ({c['frames_sent']}/{c['frames_rx']})", c["lost"] == "0" and int(c["frames_rx"]) >= 100)
    check(f"{tag}: 카메라 드리프트 {c['camera_drift_ppm']} ≈ {ppm} ppm", abs(float(c["camera_drift_ppm"]) - ppm) < 600)
    rows = list(csv.DictReader(open(root / f"{plan.index((model, raw, ppm)) + 1}_{model}_{raw}" / "frames_axis.csv")))
    t = [int(r["t_axis_ms"]) for r in rows]
    check(f"{tag}: 시간축이 정수 ms 로 단조 증가", t[0] == 0 and all(b > a for a, b in zip(t, t[1:])))
perf_n = sum(1 for m in can.LogReader(str(log)) if m.arbitration_id == 0x320)
check(f"PERF 메시지가 로그에 있음 ({perf_n}개)", perf_n >= 8)
check("compare.md 생성", (root / "compare.md").exists())
print("결과:", "통과" if not fails else f"실패 {fails}")
print((root / "compare.md").read_text())
sys.exit(1 if fails else 0)
