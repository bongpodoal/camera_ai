"""--raw on 전용: AI 연산이 끝난 결과값을 CAN 으로 보내기 전에 그대로 기록한다 (교수님 요구).

raw_ai_candidates.csv : 프레임마다 det_p3/p4/p5 의 모든 앵커 후보 중 (최대 클래스 점수 ≥ min_score) 인 것, 프레임당 점수 상위 top_k 개.
                        박스를 안 친 것(임계값·NMS 로 걸러진 것) 포함. kept_after_nms / sent_to_can 으로 살아남은 것을 표시.
raw_ai_seg.csv        : 프레임마다 차선·주행영역의 임계값 적용 전 값(최고 점수, 최대 logit 차이, 양성 픽셀 수, 면적 %, present 판정).
raw_tensors/*.npz     : (선택) 원시 출력 텐서 전체를 1초에 1프레임.

디코딩은 postprocess.py 의 decode_raw/nms 를 그대로 쓴다 (DFL softmax → 앵커 중심 +0.5 격자 → stride 곱, 클래스 sigmoid).
"""
import csv
from pathlib import Path

import numpy as np

import postprocess as base

CAND_COLS = ["frame_seq", "ts_device_ms", "scale", "gx", "gy", "x1", "y1", "x2", "y2",
             *[f"score_{n}" for n in base.NAMES], "max_cls", "max_score", "kept_after_nms", "sent_to_can"]
SEG_COLS = ["frame_seq", "ts_device_ms", "task", "max_score_pct", "max_logit_diff", "pos_pixels", "area_pct",
            "present", "sent_to_can"]


def detect_and_candidates(det_outs, conf, iou, max_det=300, max_sent=8, min_score=0.01, top_k=200):
    """base.detect 와 같은 결과 + 후보 목록.
    반환: det (n,6) [x1,y1,x2,y2,conf,cls] 입력 픽셀 (base.detect 와 같음),
          cand (m, 5+...) 구조화 dict: 열 이름 → 배열 (m = min(top_k, 점수 ≥ min_score 인 앵커 수), 점수 내림차순)."""
    boxes, probs = base.decode_raw(det_outs)
    cls = probs.argmax(1)
    score = probs.max(1)
    sel = np.where(score > conf)[0]
    if len(sel):
        off = cls[sel, None].astype(np.float32) * 7680.0
        keep = base.nms(boxes[sel] + off, score[sel], iou)[:max_det]
        kept_idx = sel[keep]
        det = np.concatenate([boxes[kept_idx], score[kept_idx, None], cls[kept_idx, None].astype(np.float32)], 1).astype(np.float32)
    else:
        kept_idx = np.zeros(0, np.int64)
        det = np.zeros((0, 6), np.float32)
    # 후보: 점수 ≥ min_score 인 앵커 중 상위 top_k
    cidx = np.where(score >= min_score)[0]
    if len(cidx) > top_k:
        cidx = cidx[np.argpartition(-score[cidx], top_k - 1)[:top_k]]
    cidx = cidx[np.argsort(-score[cidx])]
    sizes = [np.asarray(o).shape[2] * np.asarray(o).shape[3] for o in det_outs]
    widths = [np.asarray(o).shape[3] for o in det_outs]
    starts = np.cumsum([0] + sizes)
    scale_k = np.searchsorted(starts, cidx, side="right") - 1
    local = cidx - starts[scale_k]
    gw = np.asarray(widths)[scale_k]
    kept = np.zeros(len(score), bool)
    kept[kept_idx] = True
    sent = np.zeros(len(score), bool)
    sent[kept_idx[np.argsort(-score[kept_idx])][:max_sent]] = True
    cand = dict(scale=np.array(["p3", "p4", "p5"])[scale_k], gx=local % gw, gy=local // gw, box=boxes[cidx],
                probs=probs[cidx], max_cls=cls[cidx], max_score=score[cidx], kept=kept[cidx], sent=sent[cidx])
    return det, cand


def candidate_rows(seq, ts_device_ms, cand, w, h):
    """cand → CSV 행 목록. 박스는 모델 입력(레터박스 안 한 w×h)을 기준으로 0~1 정규화."""
    rows = []
    for i in range(len(cand["max_score"])):
        x1, y1, x2, y2 = cand["box"][i]
        rows.append([seq, round(ts_device_ms, 3), cand["scale"][i], int(cand["gx"][i]), int(cand["gy"][i]),
                     round(float(x1) / w, 5), round(float(y1) / h, 5), round(float(x2) / w, 5), round(float(y2) / h, 5),
                     *[round(float(p), 5) for p in cand["probs"][i]], base.NAMES[int(cand["max_cls"][i])],
                     round(float(cand["max_score"][i]), 5), int(cand["kept"][i]), int(cand["sent"][i])])
    return rows


def logit_diff_max(out, variant_kind, info, crop):
    """차선·주행영역 출력의 (logit1 − logit0) 최댓값 (패딩 제외). 임계값이 끝난 출력(v3)은 None."""
    a = np.asarray(out, np.float32)
    if variant_kind == "v3":
        return None
    if variant_kind == "original":
        _, left, top, nw, nh = info
        d = (a[0, 1] - a[0, 0])[top:top + nh, left:left + nw]
    else:
        y0, y1, x0, x1 = crop(a[0, 0].shape)
        d = a[0, 0][y0:y1, x0:x1]
    return float(d.max())


def seg_rows(seq, ts_device_ms, task, summary, logit_max, mask, sent=1):
    """summary = (present, conf%, area%) (postprocess.seg_summary 와 같은 정의)."""
    present, conf, area = summary
    return [seq, round(ts_device_ms, 3), task, "" if conf is None else round(float(conf), 3),
            "" if logit_max is None else round(logit_max, 4), int(mask.sum()), round(float(area), 4), int(present), sent]


class RawAiLogger:
    """CSV 두 개(+선택 npz)를 한 폴더에 쌓는다. close() 때 닫는다."""

    def __init__(self, out_dir, tensors_every=0.0, with_seg=True):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.out, self.tensors_every, self._last_t = out, tensors_every, -1e9
        self._fc = open(out / "raw_ai_candidates.csv", "w", newline="")
        self._fs = open(out / "raw_ai_seg.csv", "w", newline="") if with_seg else None   # with_seg=False: 후보만 기록
        self.wc, self.ws = csv.writer(self._fc), (csv.writer(self._fs) if with_seg else None)
        self.wc.writerow(CAND_COLS)
        if self.ws:
            self.ws.writerow(SEG_COLS)
        self.n_cand = self.n_tensor = 0
        if tensors_every > 0:
            (out / "raw_tensors").mkdir(exist_ok=True)

    def add(self, cand_rows, seg_rows_, seq, t_dev_s, outs):
        self.wc.writerows(cand_rows)
        if self.ws:
            self.ws.writerows(seg_rows_)
        self.n_cand += len(cand_rows)
        if self.tensors_every > 0 and t_dev_s - self._last_t >= self.tensors_every:
            self._last_t = t_dev_s
            np.savez(self.out / "raw_tensors" / f"{seq:06d}.npz", seq=np.int64(seq), **{k: np.asarray(v, np.float32) for k, v in outs.items() if k in ("det_p3", "det_p4", "det_p5", "lane")})
            self.n_tensor += 1

    def close(self):
        self._fc.close()
        if self._fs:
            self._fs.close()
