"""A-YOLOM(n) CAM01 칩/ONNX 출력의 호스트 후처리 (NumPy 만 사용, OpenCV 는 레터박스·마스크 크기 변환에만).

입력 규약: BGR(OpenCV) 이미지를 레터박스(긴 변을 맞추고 위아래/좌우 회색 114 로 채움, 가운데 정렬)해 (H, W) 로 만든다.
          ONNX/블롭은 채널 뒤집기(BGR→RGB)와 /255 를 안에서 하는 것으로 가정 (블롭 컴파일 옵션 --reverse_input_channels, --scale_values=[255,255,255]).
          ONNX 를 onnxruntime 으로 직접 돌릴 때는 preprocess_onnx() 처럼 RGB·0~1 float 로 넣는다.
출력 규약 (이름 순서 그대로):
  det_p3 / det_p4 / det_p5 : (1, 69, H/s, W/s), s = 8/16/32. 채널 0~63 = 박스 DFL (l,t,r,b 4변 x 16칸 logits), 64~68 = 클래스 logits
  drivable / lane          : (1, 2, H, W) 원시 logits (0 배경, 1 대상). 대상 판정 = logit[1] > logit[0]
호스트가 하는 일: DFL(softmax 후 0~15 가중평균) → 앵커 중심 +0.5 격자에서 ltrb 를 xyxy 로 → x stride, 클래스 sigmoid,
                  conf 문턱 + 클래스별 NMS(IoU 0.7, ultralytics 와 같음), 레터박스 되돌림, 마스크는 logit 차이를 원본 크기로 보간 후 > 0.
"""
import cv2
import numpy as np

NAMES = ["person", "car", "tl_red", "tl_green", "tl_yellow"]
STRIDES = (8, 16, 32)
REG_MAX = 16
PAD_VALUE = 114


def letterbox_fixed(img, w, h):
    """BGR 이미지 → (h, w) 레터박스. 반환: 이미지, 되돌리기 정보 (r, left, top, new_w, new_h)."""
    oh, ow = img.shape[:2]
    r = min(w / ow, h / oh)
    nw, nh = round(ow * r), round(oh * r)
    left, top = (w - nw) // 2, (h - nh) // 2
    canvas = np.full((h, w, 3), PAD_VALUE, np.uint8)
    canvas[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, (r, left, top, nw, nh)


def preprocess_onnx(canvas_bgr):
    """레터박스된 BGR → onnxruntime 입력 (1, 3, H, W) float32, RGB, 0~1 (칩에서는 블롭이 같은 일을 함)."""
    return np.ascontiguousarray(canvas_bgr[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0)


def _softmax(x, axis):
    x = x - x.max(axis=axis, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=axis, keepdims=True)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def decode_raw(det_outs):
    """원시 3스케일 → 입력 이미지 픽셀 기준 박스 (N,4 xyxy)와 클래스 확률 (N,5). N = 모든 격자 합."""
    boxes, probs = [], []
    for out, s in zip(det_outs, STRIDES):
        o = np.asarray(out, np.float32)[0]  # (69, gh, gw)
        gh, gw = o.shape[1:]
        dist = _softmax(o[:REG_MAX * 4].reshape(4, REG_MAX, gh, gw), axis=1)
        dist = (dist * np.arange(REG_MAX, dtype=np.float32).reshape(1, REG_MAX, 1, 1)).sum(1)  # (4, gh, gw) = l,t,r,b
        gx = np.arange(gw, dtype=np.float32) + 0.5
        gy = np.arange(gh, dtype=np.float32) + 0.5
        cx, cy = np.meshgrid(gx, gy)
        x1, y1, x2, y2 = cx - dist[0], cy - dist[1], cx + dist[2], cy + dist[3]
        boxes.append((np.stack([x1, y1, x2, y2], -1) * s).reshape(-1, 4))
        probs.append(_sigmoid(o[REG_MAX * 4:]).reshape(len(NAMES), -1).T)
    return np.concatenate(boxes), np.concatenate(probs)


def nms(boxes, scores, iou_thr):
    """탐욕 NMS. 반환: 남긴 인덱스 (점수 높은 순)."""
    order = scores.argsort()[::-1]
    keep = []
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return np.array(keep, dtype=np.int64)


def detect(det_outs, conf=0.25, iou=0.7, max_det=300):
    """원시 출력 → (n, 6) [x1,y1,x2,y2, conf, cls] (입력 이미지 픽셀). 격자마다 최고 클래스 하나만 쓰고 클래스별 NMS (ultralytics 기본과 같음)."""
    boxes, probs = decode_raw(det_outs)
    cls = probs.argmax(1)
    score = probs.max(1)
    m = score > conf
    boxes, score, cls = boxes[m], score[m], cls[m]
    if not len(boxes):
        return np.zeros((0, 6), np.float32)
    off = cls[:, None].astype(np.float32) * 7680.0  # 클래스별 NMS (ultralytics max_wh)
    keep = nms(boxes + off, score, iou)[:max_det]
    return np.concatenate([boxes[keep], score[keep, None], cls[keep, None].astype(np.float32)], 1).astype(np.float32)


def boxes_to_original(det, info, ow, oh):
    """입력 픽셀 박스 → 원본 이미지 기준 0~1 정규화 박스 (x1,y1,x2,y2), 0~1 로 자름."""
    r, left, top, _, _ = info
    out = det.copy()
    out[:, [0, 2]] = (det[:, [0, 2]] - left) / r / ow
    out[:, [1, 3]] = (det[:, [1, 3]] - top) / r / oh
    out[:, :4] = np.clip(out[:, :4], 0.0, 1.0)
    return out


def mask_from_logits(logits, info, ow, oh):
    """(1,2,H,W) 원시 logits → 원본 크기 bool 마스크. 패딩을 잘라내고 (logit1 - logit0) 을 쌍선형 보간한 뒤 > 0.
    (두 채널을 따로 보간해 sigmoid 를 비교하는 것과 같은 결과: 보간이 선형이고 sigmoid 는 단조.)"""
    _, left, top, nw, nh = info
    d = np.asarray(logits, np.float32)[0]
    d = (d[1] - d[0])[top:top + nh, left:left + nw]
    return cv2.resize(d, (ow, oh), interpolation=cv2.INTER_LINEAR) > 0


def postprocess(outputs, info, ow, oh, conf=0.25, iou=0.7):
    """outputs: 위 이름 순서 5개 배열. 반환: (원본 정규화 박스 (n,6), drivable bool 마스크, lane bool 마스크)."""
    det = detect(outputs[:3], conf, iou)
    return boxes_to_original(det, info, ow, oh), mask_from_logits(outputs[3], info, ow, oh), \
        mask_from_logits(outputs[4], info, ow, oh)


def seg_summary(logits, mask, info, min_pixels=50):
    """프레임 단위 요약 (SEG_SUMMARY 용). logits: (1,2,H,W) 원시 출력, mask: mask_from_logits 결과(원본 크기 bool).
    반환: (present 0/1, conf 0~100 = 패딩 제외 영역에서 sigmoid(logit1-logit0) 최댓값, area_pct 0~100 = 마스크 픽셀/원본 전체 픽셀).
    present = 원본 크기 마스크 양성 픽셀이 min_pixels 이상 (평가 presence_stats 의 N=50 과 같음)."""
    _, left, top, nw, nh = info
    d = np.asarray(logits, np.float32)[0]
    d = (d[1] - d[0])[top:top + nh, left:left + nw]
    conf = 100.0 / (1.0 + np.exp(-float(d.max())))
    n = int(mask.sum())
    return int(n >= min_pixels), conf, 100.0 * n / mask.size
