"""분할(차선·주행 영역·정지선·연석) 평가. 마스크 두 장(예측, 정답)을 비교하는 순수 계산이라 카메라·모델과 무관하다.

마스크: 0/1 numpy 배열 (H, W). 지표를 여러 개 같이 낸다 — 논문마다 "정확도" 정의가 달라서, 목표(인식률 80%)에 어느 지표를 쓸지는 사용자가 정한다.
    pixel_accuracy : 전체 픽셀 중 맞은 비율 (배경이 대부분이라 가는 선은 높게 나옴)
    recall         : 정답 선 픽셀 중 찾은 비율
    precision      : 예측 선 픽셀 중 정답인 비율
    iou            : 겹침 / 합집합 (가는 선은 원래 낮음. 공개 모델도 차선 IoU 26~34%)
    iou_tol(px)    : 위치 허용 오차를 둔 IoU. 가는 선은 1~2픽셀만 어긋나도 IoU 가 크게 떨어져서 허용 오차 버전을 같이 본다
    presence       : 프레임 단위로 "선이 있는가/예측했는가" 의 일치 (검출 여부)
"""
import numpy as np


def _dilate(mask, r):
    """정사각 구조 요소로 팽창 (scipy 없이). r=0 이면 그대로."""
    if r <= 0:
        return mask.astype(bool)
    m = mask.astype(bool)
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, axis=0), dx, axis=1)
    return out


def seg_metrics(pred, gt, tol_px=2):
    p, g = pred.astype(bool), gt.astype(bool)
    tp = int((p & g).sum())
    fp = int((p & ~g).sum())
    fn = int((~p & g).sum())
    tn = int((~p & ~g).sum())
    total = p.size
    iou = tp / (tp + fp + fn) if tp + fp + fn else float("nan")
    # 허용 오차 IoU: 예측이 정답 주변 tol 안이면 맞은 것으로, 정답이 예측 주변 tol 안이면 찾은 것으로 센다
    gt_d, pr_d = _dilate(g, tol_px), _dilate(p, tol_px)
    tp_p = int((p & gt_d).sum())          # 정답 근처에 있는 예측 픽셀
    tp_g = int((g & pr_d).sum())          # 예측 근처에 있는 정답 픽셀
    iou_tol = (tp_p + tp_g) / (2 * p.sum() + 2 * g.sum() - tp_p - tp_g) if (p.sum() + g.sum()) else float("nan")
    return dict(pixel_accuracy=(tp + tn) / total,
                recall=tp / (tp + fn) if tp + fn else float("nan"),
                precision=tp / (tp + fp) if tp + fp else float("nan"),
                iou=iou, **{f"iou_tol{tol_px}": iou_tol},
                gt_present=bool(g.any()), pred_present=bool(p.any()))


def presence_stats(per_image):
    """프레임 단위 "차선이 있는가" 검출 여부 (사용자 확정 지표: 차선은 검출 여부로 본다).
    정답에 선이 있는 프레임에서 예측도 선을 냈으면 맞음(TP), 못 냈으면 놓침(FN), 정답에 선이 없는데 냈으면 오경보(FP)."""
    tp = sum(1 for r in per_image if r["gt_present"] and r["pred_present"])
    fn = sum(1 for r in per_image if r["gt_present"] and not r["pred_present"])
    fp = sum(1 for r in per_image if not r["gt_present"] and r["pred_present"])
    tn = sum(1 for r in per_image if not r["gt_present"] and not r["pred_present"])
    n = len(per_image)
    return dict(frames=n, tp=tp, fn=fn, fp=fp, tn=tn,
                detection_rate=tp / (tp + fn) if tp + fn else float("nan"),         # 선이 있는 프레임에서 찾은 비율 (재현율)
                precision=tp / (tp + fp) if tp + fp else float("nan"),
                false_alarm_rate=fp / (fp + tn) if fp + tn else float("nan"),       # 선이 없는 프레임에서 잘못 낸 비율
                accuracy=(tp + tn) / n if n else float("nan"))


def aggregate(per_image):
    """이미지별 결과 목록 → 전체 평균 + 프레임 단위 검출 여부 일치율."""
    keys = ("pixel_accuracy", "recall", "precision", "iou")
    tol_key = next((k for k in per_image[0] if k.startswith("iou_tol")), None)
    res = {}
    for k in keys + ((tol_key,) if tol_key else ()):
        v = [r[k] for r in per_image if r[k] == r[k]]
        res[k] = float(np.mean(v)) if v else float("nan")
    res["presence_match"] = float(np.mean([r["gt_present"] == r["pred_present"] for r in per_image]))
    return res
