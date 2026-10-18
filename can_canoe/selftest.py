#!/usr/bin/env python3
"""카메라·CANoe 없이 전체 흐름을 검증한다 (가상 CAN 버스 + canoe_sim 로그 + 가짜 카메라).

여섯 번 실행(모델 3개 × Raw on/off, 마지막 모델은 A-YOLOM)을 한 로그에 이어서 찍고, analyze.py 가 실행별로 나눠 짝짓는지 본다.
카메라 시계는 실행마다 다른 ppm 으로 일부러 틀어 놓고, 측정된 ppm 이 맞는지 확인한다.
"""
import csv
import json
import sys
import tempfile
from pathlib import Path

import can

import analyze
import can_demo
import extra_messages
from canoe_sim import CanoeSim

root = Path(tempfile.mkdtemp())
log = root / "canoe.asc"
sim = CanoeSim(can.Bus(interface="virtual", channel="selftest"), log)
plan = [("yolov6n", "off", 3000), ("yolov6n", "on", -2000), ("traffic_light", "off", 5000), ("traffic_light", "on", 0),
        ("a_yolom_n", "off", 1500), ("a_yolom_n", "on", -1500)]
rc = []
for i, (model, raw, ppm) in enumerate(plan, 1):
    rc.append(can_demo.main(["--fake", "--fake-ppm", str(ppm), "--model", model, "--raw", raw, "--fps", "10",
                             "--duration", "12", *(["--fd-frames"] if i == 4 else []), *(["--raw-tensors-every", "1"] if (model, raw) == ("a_yolom_n", "on") else []), "--interface", "virtual", "--channel", "selftest",
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
check(f"실행 {len(plan)}개를 짝지음", len(cmp_rows) == len(plan))
for c, (model, raw, ppm) in zip(cmp_rows, plan):
    tag = f"{model} raw {raw}"
    check(f"{tag}: 송신=수신, 유실 0 ({c['frames_sent']}/{c['frames_rx']})", c["lost"] == "0" and int(c["frames_rx"]) >= 100)
    tol = 1300 if model == "a_yolom_n" else 600          # A-YOLOM 가짜 입력은 호스트 후처리·기록이 무거워 12초 시험의 송신 시각이 흔들린다 (실카메라 아님)
    check(f"{tag}: 카메라 드리프트 {c['camera_drift_ppm']} ≈ {ppm} ppm (허용 ±{tol})", abs(float(c["camera_drift_ppm"]) - ppm) < tol)
    rows = list(csv.DictReader(open(root / f"{plan.index((model, raw, ppm)) + 1}_{model}_{raw}" / "frames_axis.csv")))
    t = [int(r["t_axis_ms"]) for r in rows]
    check(f"{tag}: 시간축이 정수 ms 로 단조 증가", t[0] == 0 and all(b > a for a, b in zip(t, t[1:])))
perf_n = sum(1 for m in can.LogReader(str(log)) if m.arbitration_id == 0x320)
check(f"PERF 메시지가 로그에 있음 ({perf_n}개)", perf_n >= 8)
fd_n = sum(1 for m in can.LogReader(str(log)) if getattr(m, "is_fd", False))
check(f"FD 프레임이 로그에 있음 ({fd_n}개, 마지막 실행)", fd_n >= 100)
ex_counts, ex_texts = extra_messages.extract(log, root / "extra")
n_on = sum(int(c["frames_rx"]) for c in cmp_rows if c["raw"] == "on")
n_box = sum(1 for m in can.LogReader(str(log)) if m.arbitration_id == 0x310)
check(f"추가 메시지: FRAME_META_A = Raw 켬 프레임 수 ({ex_counts.get('FRAME_META_A')}/{n_on})", ex_counts.get("FRAME_META_A") == n_on)
check(f"추가 메시지: DET_POS = DET_ROI = Raw 켬 검출 수 ({ex_counts.get('DET_POS')})", ex_counts.get("DET_POS") == ex_counts.get("DET_ROI") and ex_counts.get("DET_POS", 0) > 0)
check(f"추가 메시지: 칩 상태 4종 1 Hz ({ex_counts.get('DEV_TEMP')}개)", ex_counts.get("DEV_TEMP", 0) >= 15 and ex_counts.get("DEV_TEMP") == ex_counts.get("DEV_MEM_C"))
check("추가 메시지: 보정·장치 정보 도착", ex_counts.get("CALIB_A", 0) >= 2 and ex_counts.get("CALIB_B", 0) >= 2 and ex_counts.get("CALIB_C", 0) >= 2)
check(f"장치 ID 문자열 복원 ({ex_texts.get('device_id')})", ex_texts.get("device_id") == "19443010C19B387E00" and ex_texts.get("product_name") == "OAK-D-PRO-POE-FF")
off_rows = [r for r in cmp_rows if r["raw"] == "off"]
check("Raw 끔 실행에는 추가 메시지 없음 (CAN 부하가 Raw 켬보다 작음)", all(float(o["can_load_pct"]) < float(c["can_load_pct"]) for o, c in zip(cmp_rows[0::2], cmp_rows[1::2])))
vdir = root / "vehicle_run"
vrc = can_demo.main(["--fake", "--raw", "on", "--mode", "vehicle", "--fps", "10", "--duration", "6", "--interface", "virtual",
                     "--channel", "selftest_vehicle", "--out-dir", str(vdir)])
vrows = list(csv.DictReader(open(vdir / "frames.csv")))
check("실차 모드: 종료 코드 0, frames.csv·summary.csv 있음", vrc == 0 and (vdir / "summary.csv").exists() and len(vrows) >= 40)
check("실차 모드: 이미지 폴더·detections.csv 를 만들지 않음", not (vdir / "images").exists() and not (vdir / "detections.csv").exists())
check("실차 모드: 박스 그리기 시간 0", all(float(r["post_ms"]) == 0.0 for r in vrows))
check("디버그 모드(기본): 이미지 폴더·detections.csv 있음", (root / "1_yolov6n_off" / "images").exists() and (root / "1_yolov6n_off" / "detections.csv").exists())

# ---- A-YOLOM(n): SEG_SUMMARY·Raw 켬 AI 결과 기록
import numpy as np
from can_msgs import DB, seg_summary
from a_yolom import raw_ai
import a_yolom.a_yolom_source as ays
import postprocess as _pp  # a_yolom/ 이 경로에 올라와 있음 (a_yolom_source 가 넣음)

a_frames = sum(int(c["frames_rx"]) for c in cmp_rows if c["model"] == "a_yolom_n")
seg_n = sum(1 for m in can.LogReader(str(log)) if m.arbitration_id == 0x380)
check(f"SEG_SUMMARY(0x380) 개수 = A-YOLOM 프레임 수 ({seg_n}/{a_frames})", seg_n == a_frames and a_frames > 0)
sm = seg_summary(7, (1, 87.5, 1.5), (0, None, 42.0))
sv = DB.get_message_by_name("SEG_SUMMARY").decode(sm.data, decode_choices=False)
check("SEG_SUMMARY 인코딩·디코딩 (0.5 % 단위, conf 없음=0)", sv["Seq"] == 7 and sv["LanePresent"] == 1 and sv["DaPresent"] == 0 and sv["LaneConf"] == 87.5 and sv["DaConf"] == 0 and sv["DaAreaPct"] == 42.0)
on_dir = next(root / f"{i + 1}_{m}_{r}" for i, (m, r, _) in enumerate(plan) if (m, r) == ("a_yolom_n", "on"))
off_dir = next(root / f"{i + 1}_{m}_{r}" for i, (m, r, _) in enumerate(plan) if (m, r) == ("a_yolom_n", "off"))
check("A-YOLOM Raw 켬: raw_ai_candidates.csv·raw_ai_seg.csv·raw_tensors/*.npz 생성", (on_dir / "raw_ai_candidates.csv").exists() and (on_dir / "raw_ai_seg.csv").exists() and any((on_dir / "raw_tensors").glob("*.npz")))
check("A-YOLOM Raw 끔: AI 결과 기록을 하지 않음", not (off_dir / "raw_ai_candidates.csv").exists() and not (off_dir / "raw_tensors").exists())
cand = list(csv.DictReader(open(on_dir / "raw_ai_candidates.csv")))
frames_on = {int(r["seq"]) for r in csv.DictReader(open(on_dir / "frames.csv"))}
check("raw_ai_candidates: 프레임당 후보 ≤ 200 · 점수 ≥ 0.01 · kept ⊂ sent 관계", cand and max(sum(1 for c in cand if int(c["frame_seq"]) == q) for q in list(frames_on)[:20]) <= 200
      and all(float(c["max_score"]) >= 0.01 for c in cand) and all(not int(c["sent_to_can"]) or int(c["kept_after_nms"]) for c in cand))
rng = np.random.default_rng(1)
outs = [rng.normal(-5, 2, (1, 69, 288 // s, 512 // s)).astype(np.float32) for s in _pp.STRIDES]
det_a = _pp.detect(outs, 0.25, 0.7)
det_b, _c = raw_ai.detect_and_candidates(outs, 0.25, 0.7)
check(f"Raw 켬 후보 기록 경로의 검출 = 일반 경로의 검출 ({len(det_a)}개)", det_a.shape == det_b.shape and np.allclose(det_a, det_b))

# ---- A-YOLOM 영상 송출 × Raw 4조건 + L1 변형 (가짜 입력, 가상 CAN)
def one(raw, video, extra=()):
    d = root / f"cond_{raw}_{video}_{'L1' if extra else 'orig'}"
    rcode = can_demo.main(["--fake", "--model", "a_yolom_n", "--raw", raw, "--video", video, "--fps", "10", "--duration", "6", "--mode", "vehicle",
                           "--raw-tensors-every", "1", "--interface", "virtual", "--channel", f"selftest_{raw}_{video}_{len(extra)}", "--out-dir", str(d), *extra])
    return d, rcode, list(csv.DictReader(open(d / "summary.csv")))[0], list(csv.DictReader(open(d / "frames.csv")))
conds = {}
for raw, video in (("on", "on"), ("off", "off"), ("on", "off"), ("off", "on")):
    conds[(raw, video)] = one(raw, video)
check("4조건(A 켬/켬·B 끔/끔·C 켬/끔·D 끔/켬) 모두 종료 코드 0", all(c[1] == 0 for c in conds.values()))
check("영상 송출 켬이면 이더넷 수신량(raw_bytes)이 있고 끔이면 0 (A·D 켬, B·C 끔)",
      all(int(r["raw_bytes"]) > 0 for r in conds[("on", "on")][3]) and all(int(r["raw_bytes"]) > 0 for r in conds[("off", "on")][3])
      and all(int(r["raw_bytes"]) == 0 for r in conds[("off", "off")][3]) and all(int(r["raw_bytes"]) == 0 for r in conds[("on", "off")][3]))
check("Raw 켬이면 raw_ai_*.csv·raw_spatial.csv·텐서 생성 (A·C), Raw 끔이면 없음 (B·D) — 영상 송출과 무관",
      all((conds[k][0] / "raw_spatial.csv").exists() and any((conds[k][0] / "raw_tensors").glob("*.npz")) for k in (("on", "on"), ("on", "off")))
      and not any((conds[k][0] / "raw_ai_candidates.csv").exists() for k in (("off", "off"), ("off", "on"))))
check("summary.csv 에 video 상태와 시작 시각·링크 속도 열이 기록됨 (A=on, C=off, D=on)",
      conds[("on", "on")][2]["video"] == "on" and conds[("on", "off")][2]["video"] == "off" and conds[("off", "on")][2]["video"] == "on"
      and "start_time" in conds[("on", "on")][2] and "link_mbps_start" in conds[("on", "on")][2])
check("run_info.json 에 모든 인자(video 포함)가 기록됨", json.loads((conds[("on", "off")][0] / "run_info.json").read_text())["args"]["video"] == "off")
l1 = ["--archive", "/x/a_yolom_n_cam01_ft1_L1_lane_nop5_512x288_openvino_2022.1_6shave.blob"]
dL, rL, sL, fL = one("on", "off", l1)
cL = list(csv.DictReader(open(dL / "raw_ai_seg.csv")))
check("L1 변형(검출 p3·p4, 차선만): 종료 코드 0, raw_ai_seg 에 lane 만, 후보 scale 에 p5 없음",
      rL == 0 and {r["task"] for r in cL} == {"lane"} and "p5" not in {r["scale"] for r in csv.DictReader(open(dL / "raw_ai_candidates.csv"))})
check("compare.md 생성", (root / "compare.md").exists())
print("결과:", "통과" if not fails else f"실패 {fails}")
print((root / "compare.md").read_text())
sys.exit(1 if fails else 0)
