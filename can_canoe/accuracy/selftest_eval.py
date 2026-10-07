#!/usr/bin/env python3
"""eval_core 검증: 직접 계산한 값과 비교한다 (카메라·데이터 불필요)."""
import math
import sys

import eval_core as E

fails = []


def check(name, ok):
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(name)


box = lambda x, y, s=0.1: (x, y, x + s, y + s)
gt = {"a": [("red", *box(0.1, 0.1)), ("green", *box(0.5, 0.5)), ("yellow", *box(0.8, 0.1))],
      "b": [("green", *box(0.3, 0.3))], "c": []}
preds = [
    ("a", "red", 0.9, *box(0.1, 0.1)),          # 맞음 (색 맞음)
    ("a", "red", 0.8, *box(0.5, 0.5)),          # 위치는 green 정답에 맞지만 색이 틀림 (red<->green)
    ("a", "yellow", 0.7, *box(0.8, 0.1)),       # 무시 정답(yellow)에 맞음 → 오검출로 세지 않음
    ("a", "green", 0.6, *box(0.1, 0.8)),        # 정답 없는 곳 → 오검출
    ("b", "green", 0.4, *box(0.3, 0.3)),        # 맞음 (문턱값 0.35 이상)
    ("b", "green", 0.2, *box(0.3, 0.31)),       # 이미 짝지어진 정답과 겹침 + 문턱값 미만 → 오검출(낮은 점수)
    ("c", "green", 0.95, *box(0.2, 0.2)),       # 정답 없는 이미지 → 오검출
    ("c", "person", 0.99, *box(0.2, 0.2)),      # 신호등이 아닌 클래스 → 버림
]
r = E.evaluate(preds, gt, 0.35)
check(f"정답 3개 (red 1, green 2) = {r['gt_boxes']}", r["gt_boxes"] == 3)
check(f"TP 3 (red, 위치만 맞은 green, b 의 green) = {r['tp']}", r["tp"] == 3)
check(f"FP 2 (a 의 빈 곳, c 의 오검출) = {r['fp']} (문턱값 미만 0.2 는 제외)", r["fp"] == 2)
check(f"무시 1 (yellow 정답에 맞음) = {r['ignored']}", r["ignored"] == 1)
check(f"FN 0 = {r['fn']}", r["fn"] == 0)
check(f"정밀도 3/5 = {r['precision']:.3f}, 재현율 1.0", abs(r["precision"] - 0.6) < 1e-9 and r["recall"] == 1.0)
check(f"색 정확도 2/3 (red→red, b green→green 맞음, a green→red 틀림) = {r['color_accuracy']:.3f}", abs(r["color_accuracy"] - 2 / 3) < 1e-9)
check(f"red↔green 혼동 1 = {r['red_green_swapped']}", r["red_green_swapped"] == 1)
check(f"끝까지 맞춘 재현율 2/3 = {r['end_to_end_recall']:.3f}", abs(r["end_to_end_recall"] - 2 / 3) < 1e-9)
check("AP: 완벽한 예측이면 1.0", E.average_precision([(0.9, "TP"), (0.8, "TP")], 2) == 1.0)
check("AP: 놓침 있으면 재현율만큼 (TP 1/정답 2 → 0.5)", abs(E.average_precision([(0.9, "TP")], 2) - 0.5) < 1e-9)
check("AP: 앞선 오검출이 있으면 낮아짐 (FP 후 TP, 정답 1 → 0.5)", abs(E.average_precision([(0.9, "FP"), (0.8, "TP")], 1) - 0.5) < 1e-9)
check("IoU: 같은 박스 1.0, 안 겹치면 0", E.iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0 and E.iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0)
r2 = E.evaluate([("a", "traffic light", 0.9, *box(0.1, 0.1)), ("a", "traffic light", 0.8, *box(0.5, 0.5))], gt, 0.5)
check("색 없는 예측(COCO)은 색 지표 없음", "color_accuracy" not in r2 and r2["tp"] == 2)
print("결과:", "통과" if not fails else f"실패 {fails}")
sys.exit(1 if fails else 0)
