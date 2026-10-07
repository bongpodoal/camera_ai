"""클래스별 객체 검출 평가 (사람·자동차·장애물 등 임의 클래스). 카메라·모델과 무관한 순수 계산.

box 는 (x1, y1, x2, y2) 0~1 정규화. 예측: (이미지, 클래스, 신뢰도, x1, y1, x2, y2), 정답: {이미지: [(클래스, x1, y1, x2, y2)]}
지표(클래스마다): 정밀도·재현율·F1 (운영 문턱값에서), AP50 (모든 문턱값). 목표 "인식률 80%" 는 재현율(필요하면 F1)로 본다.
"""
from collections import defaultdict

from eval_core import average_precision, iou


def _match_class(preds, gts, cls, iou_thr):
    """한 클래스만 짝짓기. 반환: [(신뢰도, 'TP'|'FP')], 정답 수"""
    by_img = defaultdict(list)
    for p in preds:
        if p[1] == cls:
            by_img[p[0]].append(p)
    n_gt = sum(1 for boxes in gts.values() for g in boxes if g[0] == cls)
    flags = []
    for img, plist in by_img.items():
        cand = [g for g in gts.get(img, []) if g[0] == cls]
        used = set()
        for p in sorted(plist, key=lambda x: -x[2]):
            best, best_iou = None, iou_thr
            for k, g in enumerate(cand):
                if k in used:
                    continue
                v = iou(p[3:7], g[1:5])
                if v >= best_iou:
                    best, best_iou = k, v
            if best is None:
                flags.append((p[2], "FP"))
            else:
                used.add(best)
                flags.append((p[2], "TP"))
    return flags, n_gt


def evaluate_classes(preds, gts, classes, conf_thr, iou_thr=0.5):
    """클래스별 결과 dict. conf_thr 는 숫자 하나 또는 {클래스: 문턱값}."""
    out = {}
    for c in classes:
        thr = conf_thr[c] if isinstance(conf_thr, dict) else conf_thr
        flags, n_gt = _match_class(preds, gts, c, iou_thr)
        kept = [f for f in flags if f[0] >= thr]
        tp = sum(1 for f in kept if f[1] == "TP")
        fp = len(kept) - tp
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / n_gt if n_gt else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if tp and prec == prec and rec == rec else 0.0
        out[c] = dict(gt=n_gt, tp=tp, fp=fp, fn=n_gt - tp, precision=prec, recall=rec, f1=f1,
                      ap50=average_precision(flags, n_gt))
    return out


def macro(results, key):
    """클래스 평균 (정답이 있는 클래스만)."""
    v = [r[key] for r in results.values() if r["gt"] and r[key] == r[key]]
    return sum(v) / len(v) if v else float("nan")
