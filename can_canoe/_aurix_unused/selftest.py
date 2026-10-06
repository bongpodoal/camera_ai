#!/usr/bin/env python3
"""카메라·AURIX 보드 없이 전체 흐름을 검증한다 (가상 CAN 버스 + aurix_sim.py + 가짜 카메라).

확인하는 것
    1) 모든 프레임에 ECHO 가 돌아오고 시간축(t_axis_ms)이 정수로 단조 증가
    2) 카메라 시계를 일부러 3000 ppm 빠르게 했을 때 camera_drift_ppm 이 그 값 근처로 측정됨
    3) AURIX 시계를 일부러 -2000 ppm 틀어도 시간축은 AURIX 시계 기준으로 일관됨
"""
import csv
import sys
import tempfile
from pathlib import Path

import can

import can_demo
from aurix_sim import AurixSim


def run(raw, cam_ppm, aurix_ppm):
    out = Path(tempfile.mkdtemp())
    ch = f"selftest_{raw}"
    sim = AurixSim(can.Bus(interface="virtual", channel=ch), ppm=aurix_ppm, sync_period=0.5)
    sim.start()
    rc = can_demo.main(["--fake", "--fake-ppm", str(cam_ppm), "--raw", raw, "--fps", "10", "--duration", "20",
                        "--interface", "virtual", "--channel", ch, "--out-dir", str(out)])
    sim.stop()
    rows = list(csv.DictReader(open(out / "frames.csv")))
    summ = list(csv.DictReader(open(out / "summary.csv")))[0]
    return rc, rows, summ, sim


fails = []
for raw in ("off", "on"):
    # 카메라는 AURIX 보다 3000 ppm 빠르고, AURIX 는 진짜 시간보다 -2000 ppm 느린 상황
    rc, rows, s, sim = run(raw, cam_ppm=3000, aurix_ppm=-2000)
    t = [int(r["t_axis_ms"]) for r in rows]
    expect_ppm = (1 + 3000e-6) / (1 - 2000e-6) * 1e6 - 1e6      # 카메라 시계 / AURIX 시계
    checks = {
        "종료 코드 0": rc == 0,
        "ECHO 유실 0": int(s["echo_lost"]) == 0,
        "프레임 ≥ 150": len(rows) >= 150,
        "시간축 단조 증가(정수 ms)": all(b > a for a, b in zip(t, t[1:])),
        f"카메라 드리프트 {s['camera_drift_ppm']} ppm ≈ {expect_ppm:.0f}": abs(float(s["camera_drift_ppm"]) - expect_ppm) < 600,
        "AURIX 가 FRAME 수신": sim.frames >= len(rows),
        "SYNC 수신 → PC 시계 드리프트 계산": s["pc_drift_ppm"] != "",
    }
    print(f"[raw {raw}]", {k: ("OK" if v else "FAIL") for k, v in checks.items()})
    fails += [f"raw {raw}: {k}" for k, v in checks.items() if not v]
print("결과:", "통과" if not fails else f"실패 {fails}")
sys.exit(1 if fails else 0)
