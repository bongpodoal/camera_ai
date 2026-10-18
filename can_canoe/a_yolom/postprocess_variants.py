"""진단용 변형(v1~v3) 출력용 호스트 후처리. 기존 postprocess.py(ft1 원본용)는 수정하지 않고 같은 폴더의 것을 불러 쓴다.
사용: postprocess_variants.postprocess(variant, outputs_by_name_or_list, info, ow, oh)
  outputs: dict{이름: 배열} 또는 변형의 출력 순서 리스트 (det_p3, det_p4, det_p5[, drivable, lane]).
  variant: 'original' | 'v1_det_only' | 'v2a_seg1ch' | 'v2b_seg_half' | 'v2c_seg_quarter' | 'v3_seg_u8'  (접두사 v1/v2a/... 만 줘도 됨)
  반환: (박스 (n,6) 원본 정규화, drivable bool 마스크 또는 None, lane bool 마스크 또는 None)
변형별 차이: v1 마스크 없음(None). v2*: (1,1,h,w) 가 이미 logit1-logit0 → 차이 계산 생략. v2b/v2c: 출력이 입력의 1/2, 1/4 해상도라
레터박스 자르기 좌표를 //f. v3: 임계값이 끝난 U8(0/1) → 보간 없이 nearest 로 원본 크기.
"""
import cv2
import numpy as np

import postprocess as base

SCALE = {"original": 1, "v1": 1, "v2a": 1, "v2b": 2, "v2c": 4, "v3": 1}
DET_NAMES = ["det_p3", "det_p4", "det_p5"]
SEG_NAMES = ["drivable", "lane"]


def kind(variant):
    k = variant.split("_")[0]
    if k not in SCALE:
        raise ValueError(f"알 수 없는 변형: {variant}")
    return k


def _crop(info, f, h, w):
    """레터박스 안의 실제 이미지 영역을 출력 해상도(1/f) 좌표로. 가장자리는 바깥쪽으로 올림."""
    _, left, top, nw, nh = info
    y0, y1 = top // f, min(h, -(-(top + nh) // f))
    x0, x1 = left // f, min(w, -(-(left + nw) // f))
    return y0, y1, x0, x1


def mask_from_variant(out, variant, info, ow, oh):
    """변형의 분할 출력 하나 → 원본 크기 bool 마스크."""
    k = kind(variant)
    a = np.asarray(out)
    if k == "original":
        return base.mask_from_logits(a, info, ow, oh)
    d = a[0, 0]
    y0, y1, x0, x1 = _crop(info, SCALE[k], *d.shape)
    d = d[y0:y1, x0:x1]
    if k == "v3":
        return cv2.resize((d > 0).astype(np.uint8), (ow, oh), interpolation=cv2.INTER_NEAREST).astype(bool)
    return cv2.resize(d.astype(np.float32), (ow, oh), interpolation=cv2.INTER_LINEAR) > 0


def seg_summary(out, mask, variant, info, min_pixels=50):
    """base.seg_summary 와 같은 (present, conf, area_pct). v3 는 logit 이 없어 conf = None."""
    k = kind(variant)
    n = int(mask.sum())
    present, area = int(n >= min_pixels), 100.0 * n / mask.size
    if k == "original":
        return base.seg_summary(out, mask, info, min_pixels)
    if k == "v3":
        return present, None, area
    d = np.asarray(out)[0, 0]
    y0, y1, x0, x1 = _crop(info, SCALE[k], *d.shape)
    return present, 100.0 / (1.0 + np.exp(-float(d[y0:y1, x0:x1].max()))), area


def postprocess(variant, outputs, info, ow, oh, conf=0.25, iou=0.7):
    k = kind(variant)
    if isinstance(outputs, dict):
        outputs = [outputs[n] for n in DET_NAMES + ([] if k == "v1" else SEG_NAMES)]
    det = base.boxes_to_original(base.detect(outputs[:3], conf, iou), info, ow, oh)
    if k == "v1":
        return det, None, None
    return det, mask_from_variant(outputs[3], variant, info, ow, oh), mask_from_variant(outputs[4], variant, info, ow, oh)
