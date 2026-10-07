#!/usr/bin/env python3
"""eval_det / eval_seg 검증: 직접 계산한 값과 비교 (카메라·데이터 불필요)."""
import sys

import numpy as np

import eval_det as D
import eval_seg as S

fails = []


def check(name, ok):
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(name)


box = lambda x, y, s=0.1: (x, y, x + s, y + s)
gts = {"a": [("person", *box(0.1, 0.1)), ("car", *box(0.5, 0.5)), ("obstacle", *box(0.8, 0.8))],
       "b": [("car", *box(0.3, 0.3)), ("car", *box(0.6, 0.1))]}
preds = [("a", "person", 0.9, *box(0.1, 0.1)),                 # 사람 맞음
         ("a", "car", 0.8, *box(0.5, 0.5)),                    # 자동차 맞음
         ("a", "car", 0.7, *box(0.0, 0.8)),                    # 자동차 오검출
         ("b", "car", 0.9, *box(0.3, 0.3)),                    # 자동차 맞음 (b 의 두 번째 car 는 놓침)
         ("b", "person", 0.6, *box(0.6, 0.1))]                 # 클래스가 틀림 → 사람 오검출, car 놓침
r = D.evaluate_classes(preds, gts, ["person", "car", "obstacle"], 0.5)
check(f"사람: TP1 FP1 FN0 = {r['person']['tp']},{r['person']['fp']},{r['person']['fn']}", (r["person"]["tp"], r["person"]["fp"], r["person"]["fn"]) == (1, 1, 0))
check(f"자동차: TP2 FP1 FN1 = {r['car']['tp']},{r['car']['fp']},{r['car']['fn']}", (r["car"]["tp"], r["car"]["fp"], r["car"]["fn"]) == (2, 1, 1))
check(f"자동차 재현율 2/3 = {r['car']['recall']:.3f}", abs(r["car"]["recall"] - 2 / 3) < 1e-9)
check(f"장애물: 예측 없음 → 재현율 0 = {r['obstacle']['recall']}", r["obstacle"]["recall"] == 0.0 and r["obstacle"]["tp"] == 0)
check("클래스 평균 재현율 (1 + 2/3 + 0)/3", abs(D.macro(r, "recall") - (1 + 2 / 3 + 0) / 3) < 1e-9)

H = W = 40
gt = np.zeros((H, W), np.uint8); gt[:, 20] = 1                   # 세로 선 1픽셀
perfect = gt.copy()
shifted = np.zeros_like(gt); shifted[:, 21] = 1                  # 1픽셀 어긋남
empty = np.zeros_like(gt)
m1 = S.seg_metrics(perfect, gt)
m2 = S.seg_metrics(shifted, gt)
m3 = S.seg_metrics(empty, gt)
check("완벽: IoU 1, 정확도 1", m1["iou"] == 1.0 and m1["pixel_accuracy"] == 1.0)
check(f"1픽셀 어긋남: IoU 0 (가는 선은 엄격) = {m2['iou']}", m2["iou"] == 0.0)
check(f"1픽셀 어긋남: 허용 오차 2 IoU 는 1 = {m2['iou_tol2']:.2f}", m2["iou_tol2"] == 1.0)
check(f"1픽셀 어긋남: 픽셀 정확도는 높음(0.95) = {m2['pixel_accuracy']:.3f}", abs(m2["pixel_accuracy"] - (1 - 2 / 40)) < 1e-9)
check("선을 못 찾음: 재현율 0, 프레임 검출 여부 불일치", m3["recall"] == 0.0 and m3["pred_present"] is False and m3["gt_present"] is True)
agg = S.aggregate([m1, m2, m3])
check(f"평균 재현율 (1+0+0)/3 = {agg['recall']:.3f}, 검출 여부 일치 2/3 = {agg['presence_match']:.3f} (정답에 선이 있고 예측이 비어 있는 1장만 불일치)",
      abs(agg["recall"] - 1 / 3) < 1e-9 and abs(agg["presence_match"] - 2 / 3) < 1e-9)
# 차선 검출 여부 (프레임 단위): 선 있음+찾음(TP) 2장, 선 있음+못 찾음(FN) 1장, 선 없음+안 냄(TN) 1장, 선 없음+냄(FP) 1장
m_tn = S.seg_metrics(empty, empty)
m_fp = S.seg_metrics(gt, empty)
ps = S.presence_stats([m1, m2, m3, m_tn, m_fp])
check(f"검출 여부: TP2 FN1 FP1 TN1 = {ps['tp']},{ps['fn']},{ps['fp']},{ps['tn']}", (ps["tp"], ps["fn"], ps["fp"], ps["tn"]) == (2, 1, 1, 1))
check(f"검출률(재현율) 2/3 = {ps['detection_rate']:.3f}, 정밀도 2/3 = {ps['precision']:.3f}", abs(ps["detection_rate"] - 2 / 3) < 1e-9 and abs(ps["precision"] - 2 / 3) < 1e-9)
check(f"오경보율 1/2 = {ps['false_alarm_rate']:.3f}, 정확도 3/5 = {ps['accuracy']:.3f}", ps["false_alarm_rate"] == 0.5 and abs(ps["accuracy"] - 0.6) < 1e-9)
print("결과:", "통과" if not fails else f"실패 {fails}")
sys.exit(1 if fails else 0)
