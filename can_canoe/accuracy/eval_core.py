"""인식률 계산 핵심 (정답 비교). 카메라·모델과 무관한 순수 계산이라 맥에서 검증한다.

약속
    정답(GT) 클래스 번호: 0 red · 1 yellow · 2 green · 3 off   (신호등 데이터셋 라벨)
    박스는 모두 0~1 로 정규화한 (x1, y1, x2, y2). 축 방향 크기 변환에서 IoU 는 변하지 않으므로 정규화 좌표로 계산해도 된다.
    공통 비교 기준(RG): 채점 대상 정답 = red·green. yellow·off 정답은 "무시"(그 박스에 맞은 예측은 오검출로 세지 않음).
    예측 클래스 이름: red/yellow/green/off = 색이 있는 예측, "traffic light" = 색 없는 예측(COCO 모델), 그 밖은 버린다.
"""
from collections import defaultdict
from pathlib import Path

GT_NAMES = {0: "red", 1: "yellow", 2: "green", 3: "off"}
SCORED = {"red", "green"}
COLOR_NAMES = {"red", "yellow", "green", "off"}
COLORLESS = {"traffic light"}


def iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def load_gt(label_dir, stems):
    """{이미지 이름: [(색 이름, x1, y1, x2, y2)]}  (YOLO 형식 라벨: 클래스 cx cy w h)"""
    gt = {}
    for s in stems:
        boxes = []
        p = Path(label_dir) / f"{s}.txt"
        if p.exists():
            for line in p.read_text().split("\n"):
                f = line.split()
                if len(f) >= 5:
                    c, cx, cy, w, h = int(float(f[0])), *map(float, f[1:5])
                    boxes.append((GT_NAMES.get(c, str(c)), cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        gt[s] = boxes
    return gt


def normalize_preds(preds):
    """예측 목록에서 신호등 클래스만 남긴다. 각 항목: (이미지, 클래스 이름, 신뢰도, x1, y1, x2, y2)"""
    return [p for p in preds if p[1] in COLOR_NAMES or p[1] in COLORLESS]


def match(preds, gt, iou_thr=0.5):
    """이미지별로 신뢰도 높은 예측부터 정답과 짝짓는다 (색 무시, 위치만).
    결과: 예측마다 (conf, 상태, 정답색, 예측색)  상태 = TP(채점 정답에 맞음) | FP | IGN(무시 정답에 맞음)"""
    by_img = defaultdict(list)
    for p in preds:
        by_img[p[0]].append(p)
    out = []
    for img, plist in by_img.items():
        gts = gt.get(img, [])
        used = set()
        for p in sorted(plist, key=lambda x: -x[2]):
            best, best_iou = None, iou_thr
            for k, g in enumerate(gts):
                if k in used:
                    continue
                v = iou(p[3:7], g[1:5])
                if v >= best_iou:
                    best, best_iou = k, v
            if best is None:
                out.append((p[2], "FP", None, p[1]))
            else:
                used.add(best)
                g = gts[best]
                out.append((p[2], "TP" if g[0] in SCORED else "IGN", g[0], p[1]))
    return out


def count_scored_gt(gt):
    return sum(1 for boxes in gt.values() for g in boxes if g[0] in SCORED)


def average_precision(flags, n_gt):
    """flags: [(conf, 'TP'|'FP')] 무시 항목은 미리 뺀다. 모든 점 보간 방식 AP."""
    if n_gt == 0:
        return float("nan")
    flags = sorted(flags, key=lambda x: -x[0])
    tp = fp = 0
    prec, rec = [], []
    for _, s in flags:
        tp += s == "TP"
        fp += s == "FP"
        prec.append(tp / (tp + fp))
        rec.append(tp / n_gt)
    for i in range(len(prec) - 2, -1, -1):          # 정밀도 곡선을 오른쪽에서 왼쪽으로 단조 감소하게
        prec[i] = max(prec[i], prec[i + 1])
    ap, prev_r = 0.0, 0.0
    for p, r in zip(prec, rec):
        ap += (r - prev_r) * p
        prev_r = r
    return ap


def class_ap(preds, gt, cls, iou_thr=0.5):
    """색(클래스)까지 맞아야 맞는 클래스별 AP50. 학습 때 평가(mAP50)와 같은 방식 (이 클래스의 정답·예측만 사용)."""
    gt_c = {k: [g for g in v if g[0] == cls] for k, v in gt.items()}
    pr_c = [p for p in preds if p[1] == cls]
    flags = [(c, s) for c, s, _, _ in match(pr_c, gt_c, iou_thr)]
    return average_precision(flags, sum(len(v) for v in gt_c.values()))


def evaluate(preds, gt, conf_thr, iou_thr=0.5):
    """운영 문턱값(conf_thr)에서의 지표. preds 는 낮은 문턱값으로 모은 전체 예측."""
    preds = normalize_preds(preds)
    n_gt = count_scored_gt(gt)
    flags = match(preds, gt, iou_thr)                                  # 전체 예측으로 한 번 짝짓기 (문턱값 거르기와 무관)
    kept = [f for f in flags if f[0] >= conf_thr]
    tp = sum(1 for f in kept if f[1] == "TP")
    fp = sum(1 for f in kept if f[1] == "FP")
    ign = sum(1 for f in kept if f[1] == "IGN")
    fn = n_gt - tp
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / n_gt if n_gt else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if tp and prec == prec and rec == rec else 0.0
    has_color = any(p[1] in COLOR_NAMES for p in preds)
    conf_mat = defaultdict(int)
    for c, s, gcol, pcol in kept:
        if s == "TP":
            conf_mat[(gcol, pcol)] += 1
    color_ok = sum(v for (g, p), v in conf_mat.items() if g == p)
    swapped = conf_mat[("red", "green")] + conf_mat[("green", "red")]
    res = dict(conf_thr=conf_thr, gt_boxes=n_gt, tp=tp, fp=fp, fn=fn, ignored=ign,
               precision=prec, recall=rec, f1=f1,
               ap50_detection=average_precision([(c, s) for c, s, _, _ in flags if s != "IGN"], n_gt))
    if has_color:
        res.update(color_accuracy=color_ok / tp if tp else float("nan"), red_green_swapped=swapped,
                   end_to_end_recall=color_ok / n_gt if n_gt else float("nan"),
                   ap50_red=class_ap(preds, gt, "red", iou_thr), ap50_green=class_ap(preds, gt, "green", iou_thr),
                   confusion={f"{g}->{p}": v for (g, p), v in sorted(conf_mat.items())})
    return res
