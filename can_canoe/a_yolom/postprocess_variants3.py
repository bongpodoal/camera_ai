"""lane 전용 변형(L0~L5) 출력용 호스트 후처리. 같은 폴더의 postprocess.py(ft1 원본, 수정 없음)를 불러 쓴다.
사용: postprocess_variants3.postprocess(variant, outputs, info, ow, oh, interp="linear")
  variant : 'L0_lane_only' | 'L1_lane_nop5' | 'L2_lane_resize' | 'L3_lane_lowres' | 'L4_lane_head36' | 'L5_lane_head72' (앞 토큰 L0~L5 만 줘도 됨)
  outputs : 이름→배열 dict 이거나 출력 순서 리스트 (det_p3, det_p4, [det_p5], lane)
  반환    : (박스 (n,6) 원본 정규화, lane bool 마스크 (oh, ow))
출력 형식 (입력 512x288):
  L0  det_p3/p4/p5 + lane (1,2,288,512) logits   → logit1-logit0 > 0  (원본과 같음)
  L1  det_p3/p4 (p5 없음) + lane (1,2,288,512)
  L2  L1 과 같은 모양 (ConvTranspose 대신 1x1+nearest 로 만든 lane)
  L3  lane (1,1,144,256) = logit1-logit0 (배율 2)
  L4  lane (1,1,36,64) (배율 8, 값>0 이 양성)   L5  lane (1,1,72,128) (배율 4)
저해상도 마스크: 레터박스 안 영역을 //배율 로 잘라 원본 크기로 보간(interp: linear|cubic|nearest) 후 > 0.
lane_summary: SEG_SUMMARY 용 (LanePresent, LaneConf%, LaneAreaPct) = base.seg_summary 와 같은 정의 (양성 픽셀 >= 50).
"""
import cv2
import numpy as np

import postprocess as base

# 앞 토큰: (검출 출력 수, lane 채널 수, 배율)
TABLE = {"L0": (3, 2, 1), "L1": (2, 2, 1), "L2": (2, 2, 1), "L3": (2, 1, 2), "L4": (2, 1, 8), "L5": (2, 1, 4)}
DET_NAMES = ["det_p3", "det_p4", "det_p5"]
INTERP = {"linear": cv2.INTER_LINEAR, "cubic": cv2.INTER_CUBIC, "nearest": cv2.INTER_NEAREST}


def spec(variant):
    k = variant.split("_")[0]
    if k not in TABLE:
        raise ValueError(f"알 수 없는 변형: {variant}")
    return TABLE[k]


def _crop(info, f, h, w):
    _, left, top, nw, nh = info
    return top // f, min(h, -(-(top + nh) // f)), left // f, min(w, -(-(left + nw) // f))


def _diff(out, nch):
    a = np.asarray(out, np.float32)[0]
    return a[1] - a[0] if nch == 2 else a[0]


def lane_mask(out, variant, info, ow, oh, interp="linear"):
    _, nch, f = spec(variant)
    d = _diff(out, nch)
    y0, y1, x0, x1 = _crop(info, f, *d.shape)
    return cv2.resize(d[y0:y1, x0:x1], (ow, oh), interpolation=INTERP[interp]) > 0


def lane_summary(out, mask, variant, info, min_pixels=50):
    """(present 0/1, conf 0~100 = 패딩 제외 영역 sigmoid(max 차이), area_pct 0~100)."""
    _, nch, f = spec(variant)
    d = _diff(out, nch)
    y0, y1, x0, x1 = _crop(info, f, *d.shape)
    n = int(mask.sum())
    return int(n >= min_pixels), 100.0 / (1.0 + np.exp(-float(d[y0:y1, x0:x1].max()))), 100.0 * n / mask.size


def postprocess(variant, outputs, info, ow, oh, conf=0.25, iou=0.7, interp="linear"):
    ndet, _, _ = spec(variant)
    if isinstance(outputs, dict):
        outputs = [outputs[n] for n in DET_NAMES[:ndet] + ["lane"]]
    det = base.boxes_to_original(base.detect(outputs[:ndet], conf, iou), info, ow, oh)
    return det, lane_mask(outputs[ndet], variant, info, ow, oh, interp)
