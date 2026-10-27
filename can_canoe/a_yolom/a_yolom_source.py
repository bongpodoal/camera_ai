"""A-YOLOM(n) (검출 + 차선 + 주행영역) 용 can_demo 입력 소스.

일반 DetectionNetwork 대신 NeuralNetwork 노드로 원시 출력(det_p3/p4/p5, drivable, lane)을 받아 호스트에서 디코딩한다 (postprocess.py).
  - 검출은 기존 DET_BOX 로, 차선·주행영역은 프레임 요약(SEG_SUMMARY)으로 CAN 에 보낸다. 마스크 자체는 CAN 에 싣지 않는다.
  - **Raw 와 영상 송출은 서로 독립**이다 (--raw on|off, --video on|off. --video 를 안 주면 --raw 를 따라간다):
      Raw  = 숫자 데이터 전부(CAN 추가 메시지·AI 결과 기록·텔레메트리·보정). 깊이 좌표(X/Y/Z)·프레임 메타는 **칩 안에서** 계산해 숫자만 호스트로 보낸다.
      영상 = 이더넷으로 RGB 프레임과 깊이 프레임(그리고 디버그 모드의 마스크 오버레이)을 송출하는 것. 끄면 칩 안에서 버린다.
      (신경망 원시 출력 = 마스크 logit 은 호스트 디코딩에 필요해 어느 조건에서도 이더넷으로 온다.)
  - 깊이는 Raw 켬 또는 영상 켬일 때만 칩이 계산한다 (Raw 끔 + 영상 끔이면 계산하지 않음).
모델 파일 가정(출력 이름·모양·변형별 해상도)은 postprocess_variants*.py 한 곳에 모아 두었다. 변형 모델은 --archive 로 바꿔 끼운다
(.tar.xz = NNArchive, .blob = 최소 NNArchive 로 감싸 사용). 변형 이름은 파일명(_v1_, _v2b_, _L1_ …)에서 읽고 --variant 로 지정할 수도 있다.
"""
import json
import re
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import postprocess as base                # noqa: E402
import postprocess_variants as pv         # noqa: E402
import postprocess_variants3 as pv3       # noqa: E402
import raw_ai                             # noqa: E402

import oak_full                           # noqa: E402  (can_canoe/ 에 있음, can_demo 가 이미 경로에 둠)

SEG_MIN_PIXELS = 50
DEPTH_LO_MM, DEPTH_HI_MM = 100, 20000
ROI_SCALE = 0.5            # 깊이는 검출 박스 가운데 50% 영역의 중앙값 (SpatialDetectionNetwork 기본과 같음)

# 칩 위 Script: 신경망이 처리한 프레임(passthrough)의 메타데이터만 뽑아 작은 JSON 으로 내보낸다 (영상 송출을 끄고도 프레임 정보를 받기 위해).
# 주의: Script 안에서 msg.getTimestamp() 는 펌웨어 크래시라 쓰지 않는다 (호스트가 신경망 결과의 촬영 시각으로 대신 계산).
META_SCRIPT = """
import json
def g(fn, conv=lambda v: v, dflt=0):
    try:
        return conv(fn())
    except Exception:
        return dflt
while True:
    f = node.inputs['frame'].get()
    d = dict(seq=f.getSequenceNum(),
             expo=g(lambda: f.getExposureTime(), lambda v: int(v.total_seconds() * 1000000)),
             iso=g(lambda: f.getSensitivity()), ct=g(lambda: f.getColorTemperature()),
             lens=g(lambda: f.getLensPosition(), int, -1),
             sw=g(lambda: f.getSourceWidth()), sh=g(lambda: f.getSourceHeight()), inst=g(lambda: f.getInstanceNum()),
             typ=g(lambda: f.getType(), lambda v: int(v.value)), w=f.getWidth(), h=f.getHeight(),
             hfov=g(lambda: f.getSourceHFov()), vfov=g(lambda: f.getSourceVFov()),
             tsdev=g(lambda: f.getTimestampDevice(), lambda v: int(v.total_seconds() * 1000000)))
    data = json.dumps(d).encode()
    buf = Buffer(len(data))
    buf.setData(data)
    buf.setSequenceNum(f.getSequenceNum())
    node.outputs['meta'].send(buf)
"""


def variant_of(path, override=None):
    """파일명에서 변형 이름을 읽는다. 없으면 'original'."""
    if override:
        return override
    m = re.search(r"_(v1|v2a|v2b|v2c|v3|L[0-5])_", Path(str(path)).name)
    return m.group(1) if m else "original"


def input_size_of(path, default=(512, 288)):
    m = re.search(r"(\d{3,4})x(\d{3,4})", Path(str(path)).name)
    return (int(m.group(1)), int(m.group(2))) if m else default


def make_stereo_depth(pipeline, dai, fps, out_w, out_h):
    """깊이를 명시적 StereoDepth(왼쪽 CAM_B·오른쪽 CAM_C, 400P)로 만든다. 설정은 Depth 노드 기본(DEFAULT 프리셋)과 같다: LR check 켬, 서브픽셀·확장 끔, median 7.
    (Depth 노드의 자동 카메라 쌍 감지가 2026-10-13 19:42 이후 "Device has no stereo camera pair for Depth node" 로 계속 실패해 대체. 두 방식의 fps·지연은 같았음: 4.0 fps, 390 ms)
    깊이는 CAM_A 기준으로 정렬하고 신경망 입력과 같은 크기로 낸다."""
    left = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
    right = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
    st = pipeline.create(dai.node.StereoDepth)
    left.requestOutput((640, 400), dai.ImgFrame.Type.NV12, fps=fps).link(st.left)
    right.requestOutput((640, 400), dai.ImgFrame.Type.NV12, fps=fps).link(st.right)
    st.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.DEFAULT)
    st.setLeftRightCheck(True)
    st.setSubpixel(False)
    st.setExtendedDisparity(False)
    st.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)
    st.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    st.setOutputSize(out_w, out_h)
    return st


def use_factory_calibration(pipeline, device):
    """깊이를 쓰는 파이프라인에는 **공장 보정**을 적용한다 (장치에 저장된 값은 바꾸지 않는다).
    2026-10-13 이 카메라에 저장된 현재 보정의 좌우 카메라 외부 변환이 공장 값과 크게 달랐다(이동 [0.49,-1.0,-7.4] cm·회전 약 7° vs 공장 [-7.52,-0.01,-0.12] cm).
    그 상태에서는 스테레오 정렬이 깨져 깊이 유효율 0 %·Depth 노드 "no stereo camera pair" 오류. 공장 보정을 쓰면 깊이 96~98 % 유효.
    반환: 기록용 문자열."""
    import numpy as np
    import depthai as dai
    try:
        fac = device.readFactoryCalibration()
        cur = device.readCalibration()
        b, c = dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C
        diff_cm = float(np.linalg.norm(np.array(fac.getCameraExtrinsics(b, c))[:3, 3] - np.array(cur.getCameraExtrinsics(b, c))[:3, 3]))
        pipeline.setCalibrationData(fac)
        note = f"factory_override (저장 보정과 공장 보정의 B→C 이동 차이 {diff_cm:.2f} cm)"
    except Exception as e:                                   # 공장 보정을 못 읽으면 저장된 보정을 그대로 쓴다
        note = f"stored_calibration (공장 보정 적용 실패: {str(e)[:60]})"
    print("깊이 보정:", note)
    return note


class ModelIO:
    """모델 변형별 출력 이름·마스크 변환·요약을 한 곳에서 정한다 (변형이 바뀌어도 여기만 보면 된다)."""

    def __init__(self, variant, info, w, h):
        self.variant, self.info, self.w, self.h = variant, info, w, h
        self.lane_family = variant[:1] == "L" and variant[1:2].isdigit()     # L0~L5: 차선만 (주행영역 가지 없음)
        if self.lane_family:
            n_det, self.lane_ch, self.lane_f = pv3.spec(variant)
            self.det_names = pv3.DET_NAMES[:n_det]
            self.seg_tasks = ["lane"]
        else:
            self.kind = pv.kind(variant)
            self.det_names = list(pv.DET_NAMES)
            self.seg_tasks = [] if self.kind == "v1" else ["lane", "drivable"]

    @property
    def output_names(self):
        return self.det_names + self.seg_tasks

    def mask(self, task, out):
        if self.lane_family:
            return pv3.lane_mask(out, self.variant, self.info, self.w, self.h)
        return pv.mask_from_variant(out, self.variant, self.info, self.w, self.h)

    def summary(self, task, out, mask, min_pixels):
        if self.lane_family:
            return pv3.lane_summary(out, mask, self.variant, self.info, min_pixels)
        return pv.seg_summary(out, mask, self.variant, self.info, min_pixels)

    def logit_max(self, out):
        """임계값 적용 전 최대 (logit1−logit0) (패딩 제외). 임계값이 끝난 출력(v3)은 None."""
        if self.lane_family:
            d = pv3._diff(out, self.lane_ch)
            y0, y1, x0, x1 = pv3._crop(self.info, self.lane_f, *d.shape)
            return float(d[y0:y1, x0:x1].max())
        return raw_ai.logit_diff_max(out, self.kind, self.info, lambda shape: pv._crop(self.info, pv.SCALE[self.kind], *shape))

    def fake_outputs(self, rng):
        outs = {}
        for name, s in zip(self.det_names, base.STRIDES):
            o = rng.normal(-6.0, 1.0, (1, 69, self.h // s, self.w // s)).astype(np.float32)
            o[0, :64] = rng.normal(0.0, 1.0, o[0, :64].shape)
            for _ in range(3):
                gy, gx, c = rng.integers(0, self.h // s), rng.integers(0, self.w // s), rng.integers(0, 5)
                o[0, 64 + c, gy, gx] = rng.uniform(0.5, 4.0)
            outs[name] = o
        for task in self.seg_tasks:
            if self.lane_family:
                f, ch = self.lane_f, self.lane_ch
                outs[task] = rng.normal(0, 3, (1, ch, self.h // f, self.w // f)).astype(np.float32)
            elif self.kind == "original":
                outs[task] = rng.normal(0, 3, (1, 2, self.h, self.w)).astype(np.float32)
            elif self.kind == "v3":
                outs[task] = (rng.random((1, 1, self.h, self.w)) > 0.7).astype(np.float32)
            else:
                f = pv.SCALE[self.kind]
                outs[task] = rng.normal(0, 3, (1, 1, self.h // f, self.w // f)).astype(np.float32)
        return outs


class Processor:
    """원시 출력(이름 → 배열) → 검출 + 차선/주행영역 요약 (+ Raw 켬이면 AI 결과 기록). 카메라 없이도 시험할 수 있게 분리했다."""

    def __init__(self, variant, w, h, conf=0.25, iou=0.7, max_dets=8, min_pixels=SEG_MIN_PIXELS, raw_logger=None):
        self.variant, self.w, self.h, self.conf, self.iou = variant, w, h, conf, iou
        self.max_dets, self.min_pixels, self.raw_logger = max_dets, min_pixels, raw_logger
        self.info = (1.0, 0, 0, w, h)      # 카메라 프레임을 그대로 신경망에 넣으므로(16:9) 패딩 없음
        self.io = ModelIO(variant, self.info, w, h)
        self.last_masks = {}

    def __call__(self, outs, seq, ts_device_s):
        """반환: dict(dets=[(label, conf, xmin, ymin, xmax, ymax)] 신뢰도 높은 순, seg=(lane, da) 또는 None, post_ms)."""
        t0 = time.perf_counter()
        det_outs = [outs[n] for n in self.io.det_names]
        cand = None
        if self.raw_logger is not None:
            det_px, cand = raw_ai.detect_and_candidates(det_outs, self.conf, self.iou, max_sent=self.max_dets)
            det = base.boxes_to_original(det_px, self.info, self.w, self.h)
        else:
            det = base.boxes_to_original(base.detect(det_outs, self.conf, self.iou), self.info, self.w, self.h)
        dets = sorted(((int(c), float(cf), float(x1), float(y1), float(x2), float(y2)) for x1, y1, x2, y2, cf, c in det), key=lambda d: -d[1])
        seg, seg_log, summ = None, [], {}
        self.last_masks = {}
        for task in self.io.seg_tasks:
            out = outs[task]
            mask = self.io.mask(task, out)
            self.last_masks[task] = mask
            s = self.io.summary(task, out, mask, self.min_pixels)
            summ[task] = s
            if self.raw_logger is not None:
                seg_log.append(raw_ai.seg_rows(seq, ts_device_s * 1000, task, s, self.io.logit_max(out), mask))
        if self.io.seg_tasks:
            none = (0, None, 0.0)                    # 이 모델에 없는 출력(예: L 변형의 주행영역)은 0 으로 보낸다 (README 에 명시)
            seg = (summ.get("lane", none), summ.get("drivable", none))
        if self.raw_logger is not None:
            self.raw_logger.add(raw_ai.candidate_rows(seq, ts_device_s * 1000, cand, self.w, self.h), seg_log, seq, ts_device_s, outs)
        return dict(dets=dets, seg=seg, post_ms=(time.perf_counter() - t0) * 1000)


def draw_debug(frame, dets, masks):
    """디버그 모드 영상: 마스크(차선 자홍·주행영역 초록)와 박스·라벨을 그린다 (영상 송출 조건에서만)."""
    import cv2
    h, w = frame.shape[:2]
    for task, color, alpha in (("drivable", (0, 200, 0), 0.4), ("lane", (255, 0, 255), 0.6)):
        m = masks.get(task)
        if m is not None and m.any():
            tint = frame.copy()
            tint[m] = color
            frame = cv2.addWeighted(tint, alpha, frame, 1 - alpha, 0)
    for lab, cf, x1, y1, x2, y2 in dets:
        p0, p1 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
        cv2.rectangle(frame, p0, p1, (255, 0, 0), 2)
        cv2.putText(frame, f"{base.NAMES[lab]} {cf:.2f}", (p0[0], max(p0[1] - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    return frame


class RawLog:
    """RawAiLogger + 칩이 계산한 깊이 좌표 기록(raw_spatial.csv)을 한 곳에서 닫는다."""

    def __init__(self, out_dir, tensors_every, only_candidates=False):
        import csv
        self.logger = raw_ai.RawAiLogger(out_dir, tensors_every, with_seg=not only_candidates)
        self._fs = None if only_candidates else open(Path(out_dir) / "raw_spatial.csv", "w", newline="")
        self.ws = None if only_candidates else csv.writer(self._fs)
        if self.ws:
            self.ws.writerow(["frame_seq", "index", "label", "conf", "x_mm", "y_mm", "z_mm", "roi_x", "roi_y", "roi_w", "roi_h"])
        self.n_spatial = 0

    def add_spatial(self, seq, dets, ext):
        if not self.ws:
            return
        for i, (d, e) in enumerate(zip(dets, ext)):
            self.ws.writerow([seq, i, base.NAMES[d[0]], round(d[1], 4), round(e["x_mm"]), round(e["y_mm"]), round(e["z_mm"]),
                              e["roi_x"], e["roi_y"], e["roi_w"], e["roi_h"]])
            self.n_spatial += 1

    def close(self):
        self.logger.close()
        if self._fs:
            self._fs.close()
        print(f"AI 결과 기록: 후보 {self.logger.n_cand}행 (raw_ai_candidates.csv), 깊이 좌표 {self.n_spatial}행 (raw_spatial.csv), 원시 텐서 {self.logger.n_tensor}장")


class DepthCheck:
    """--depth-check on (debug 모드·영상 송출 켬): 프레임마다 RGB 원본 PNG(raw_rgb/)·깊이 요약(depth_stats.csv)·박스별 호스트 깊이(depth_boxes.csv)를
    기록하고, 수신 정보를 글자로 덧그린 영상을 만들어 debug 창에도 보여 준다.
    깊이는 그 프레임 처리 시점에 가장 최근 도착한 깊이 프레임이라 RGB 와 seq 가 다를 수 있다 (depth_seq 열로 확인, n_depth=0 이면 직전 것 재사용).
    박스별 깊이는 박스 중앙 50 % 영역의 유효(>0) 깊이 중앙값 — 칩이 계산하는 raw_spatial.csv 의 z_mm 와는 별도 값."""

    STATS_COLS = ["seq", "t_recv_s", "depth_seq", "n_depth", "valid_ratio", "zero_ratio", "min_mm", "median_mm", "max_mm", "center_mm"]
    BOX_COLS = ["seq", "index", "label", "conf", "z_host_mm", "valid_ratio_in_box"]

    def __init__(self, out_dir, window=True):
        import csv
        self.out, self.window, self.last_depth = Path(out_dir), window, None
        (self.out / "raw_rgb").mkdir(parents=True, exist_ok=True)
        self._fs, self._fb = open(self.out / "depth_stats.csv", "w", newline=""), open(self.out / "depth_boxes.csv", "w", newline="")
        self.ws, self.wb = csv.writer(self._fs), csv.writer(self._fb)
        self.ws.writerow(self.STATS_COLS)
        self.wb.writerow(self.BOX_COLS)

    @staticmethod
    def _med(a):
        v = a[a > 0]
        return (int(np.median(v)), len(v) / a.size) if v.size else ("", 0.0)

    def process(self, seq, rgb, drawn, depth_msgs, dets, t_recv, total_ms, edge_ms):
        """rgb: 원본, drawn: 박스·마스크가 그려진 영상. 반환: 수신 정보까지 덧그린 영상, 최신 깊이 프레임(없으면 None)."""
        import cv2
        import datetime
        if depth_msgs:
            self.last_depth = depth_msgs[-1]
        dm = self.last_depth
        d = dm.getFrame() if dm is not None else None
        cv2.imwrite(str(self.out / "raw_rgb" / f"{seq:06d}.png"), rgb)
        valid_ratio, center, med_all = 0.0, "", ""
        if d is not None:
            v = d[d > 0]
            valid_ratio = v.size / d.size
            h, w = d.shape
            center = self._med(d[h // 2 - 8:h // 2 + 8, w // 2 - 8:w // 2 + 8])[0]
            med_all = int(np.median(v)) if v.size else ""
            self.ws.writerow([seq, f"{t_recv:.6f}", dm.getSequenceNum(), len(depth_msgs), round(valid_ratio, 4), round(1 - valid_ratio, 4),
                              int(v.min()) if v.size else "", med_all, int(v.max()) if v.size else "", center])
        else:
            self.ws.writerow([seq, f"{t_recv:.6f}", "", 0, "", "", "", "", "", ""])
        img = drawn
        H, W = img.shape[:2]
        for i, (lab, cf, x1, y1, x2, y2) in enumerate(dets):
            z, vr = "", ""
            if d is not None:
                h, w = d.shape
                bx1, bx2 = x1 + 0.25 * (x2 - x1), x1 + 0.75 * (x2 - x1)
                by1, by2 = y1 + 0.25 * (y2 - y1), y1 + 0.75 * (y2 - y1)
                z, vr = self._med(d[int(by1 * h):max(int(by2 * h), int(by1 * h) + 1), int(bx1 * w):max(int(bx2 * w), int(bx1 * w) + 1)])
                vr = round(vr, 4)
            self.wb.writerow([seq, i, base.NAMES[lab], round(cf, 4), z, vr])
            cv2.putText(img, f"z={z}mm" if z != "" else "z=-", (int(x1 * W), min(int(y2 * H) + 14, H - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        ts = datetime.datetime.fromtimestamp(t_recv).strftime("%H:%M:%S.%f")[:-3]
        lines = [f"seq {seq}  recv {ts}  lat {total_ms:.0f}ms  edge {'-' if edge_ms is None else f'{edge_ms:.0f}'}ms",
                 f"depth valid {valid_ratio * 100:.1f}%  center {center}mm  median {med_all}mm  (depth seq {dm.getSequenceNum() if dm is not None else '-'}, n={len(depth_msgs)})"]
        for k, s in enumerate(lines):
            cv2.putText(img, s, (6, 16 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
            cv2.putText(img, s, (6, 16 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        if self.window:
            if d is not None:
                cm = cv2.applyColorMap(np.clip(d.astype(np.float32) / 5000 * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_JET)
                cm[d == 0] = 0
            else:
                cm = np.zeros_like(img)
            cv2.imshow("depth check (left: RGB + info, right: depth 0-5 m)", np.hstack([img, cm]))
            cv2.waitKey(1)
        return img, (d if d is not None else None)

    def close(self):
        self._fs.close()
        self._fb.close()
        if self.window:
            import cv2
            cv2.destroyAllWindows()


class _SourceBase:
    """실제·가짜 소스가 공유하는 부분: Raw/영상 상태, 칩에서 온 지연값·메타 기다리기, 깊이 좌표 결과 보관."""

    def __init__(self, args):
        self.args = args
        self.raw = args.raw == "on"
        vmode = getattr(args, "video", None)          # on = RGB+깊이 프레임, rgb = RGB 프레임만, off = 둘 다 안 보냄 (안 주면 --raw 를 따름)
        self.video = (vmode in ("on", "rgb")) if vmode else self.raw
        self.video_depth = (vmode == "on") if vmode else self.raw
        self.edge_by_seq, self.meta_by_seq, self.edge_queue, self.meta_queue = {}, {}, None, None
        self.ready = deque()          # (seq, dets, ext 목록): 칩이 깊이 좌표를 돌려주면 쌓인다 (can_demo 가 꺼내 CAN 으로 보냄)
        self.session = None
        self.raw_logger = None
        self.calib_note = ""

    def wait_edge(self, seq, timeout=0.25):
        end = time.monotonic() + timeout
        while seq not in self.edge_by_seq and self.edge_queue is not None and time.monotonic() < end:
            for buf in self.edge_queue.tryGetAll():
                self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
            time.sleep(0.01)

    def pop_ready(self):
        out = []
        while self.ready:
            out.append(self.ready.popleft())
        return out


class AYolomSource(_SourceBase):
    """실제 OAK-D. 프레임마다 dict 하나를 내준다 (can_demo.OakSource 와 같은 약속)."""

    def __init__(self, args, default_archive, edge_script, drop_script):
        super().__init__(args)
        self.default_archive = default_archive
        self.edge_script, self.drop_script = edge_script, drop_script      # 칩 위 Script 문자열은 can_demo.py 에 한 곳만 둔다
        path = args.archive or default_archive
        self.variant = variant_of(path, getattr(args, "variant", None))
        self.w, self.h = input_size_of(path)
        self.pending = deque()        # 깊이 좌표를 요청한 프레임: (seq, dets)

    def _archive(self, dai):
        path = Path(self.args.archive or self.default_archive).expanduser()
        if path.suffix == ".blob":                       # 변형 블롭: 최소 NNArchive 로 감싼다 (원시 출력 그대로, 칩 위 해석기 없음)
            sys.path.insert(0, str(HERE.parent / "model_candidates"))
            from chip_bench import wrap_blob
            return dai.NNArchive(str(wrap_blob(path, self.w, self.h)[0]))
        return dai.NNArchive(str(path))

    def _wait_meta(self, seq, timeout=0.15):
        end = time.monotonic() + timeout
        while seq not in self.meta_by_seq and time.monotonic() < end:
            for buf in self.meta_queue.tryGetAll():
                self.meta_by_seq[buf.getSequenceNum()] = json.loads(bytes(buf.getData()).decode())
            time.sleep(0.005)
        return self.meta_by_seq.pop(seq, None)

    def _spatial_config(self, dai, dets):
        """검출 박스(신뢰도 순) → 칩의 SpatialLocationCalculator 설정. 박스 가운데 50% 영역 중앙값, 100 mm~20 m. 검출이 없으면 아무 데나 한 칸(결과는 버림)."""
        cfg = dai.SpatialLocationCalculatorConfig()
        boxes = dets[:self.args.max_dets] or [(0, 0, 0.48, 0.48, 0.52, 0.52)]
        for _, _, x1, y1, x2, y2 in boxes:
            cx, cy, bw, bh = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) * ROI_SCALE, (y2 - y1) * ROI_SCALE
            d = dai.SpatialLocationCalculatorConfigData()
            d.depthThresholds.lowerThreshold = DEPTH_LO_MM
            d.depthThresholds.upperThreshold = DEPTH_HI_MM
            d.calculationAlgorithm = dai.SpatialLocationCalculatorAlgorithm.MEDIAN
            d.roi = dai.Rect(dai.Point2f(max(cx - bw / 2, 0.0), max(cy - bh / 2, 0.0)), dai.Point2f(min(cx + bw / 2, 1.0), min(cy + bh / 2, 1.0)))
            cfg.addROI(d)
        return cfg

    def _collect_spatial(self, calc_q):
        for res in calc_q.tryGetAll():
            if not self.pending:
                break
            seq0, dets0 = self.pending.popleft()
            ext = []
            for loc in res.getSpatialLocations()[:len(dets0)]:
                sc, r = loc.spatialCoordinates, loc.config.roi
                ext.append(dict(x_mm=sc.x, y_mm=sc.y, z_mm=sc.z, roi_x=int(r.x * self.w), roi_y=int(r.y * self.h),
                                roi_w=int(r.width * self.w), roi_h=int(r.height * self.h)))
            self.ready.append((seq0, dets0, ext))
            if self.raw_logger:
                self.raw_logger.add_spatial(seq0, dets0, ext)

    def frames(self, stop):
        import depthai as dai
        a = self.args
        raw, video, debug = self.raw, self.video, a.mode == "debug"
        video_depth = self.video_depth
        need_depth = raw or video_depth
        archive = self._archive(dai)
        device = dai.Device(dai.DeviceInfo(a.ip))
        out_dir = Path(a.out_dir).expanduser()
        if raw and getattr(a, "raw_log", "on") == "on":
            self.raw_logger = RawLog(out_dir, getattr(a, "raw_tensors_every", 0.0), getattr(a, "log_files", "all") == "candidates")
        proc = Processor(self.variant, self.w, self.h, a.conf, 0.7, a.max_dets, getattr(a, "seg_min_pixels", SEG_MIN_PIXELS),
                         self.raw_logger.logger if self.raw_logger else None)
        dc = None
        if getattr(a, "depth_check", "off") == "on":
            if not (debug and video and video_depth):
                print("경고: --depth-check on 은 --mode debug 와 영상 송출(--video on, RGB+깊이) 이 필요해 무시합니다")
            else:
                dc = DepthCheck(out_dir, window=not getattr(a, "no_window", False))
        with dai.Pipeline(device) as pipeline:
            if need_depth:
                self.calib_note = use_factory_calibration(pipeline, device)
            camera = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
            net = pipeline.create(dai.node.NeuralNetwork).build(camera, archive, fps=a.fps)
            net.input.setMaxSize(1)           # 최신화 큐 (can_demo 의 다른 모델과 같은 조건)
            net.input.setBlocking(False)
            print(f"설정: 모드 {a.mode} · 카메라 {a.fps:g} fps 고정 · AI 입력 큐 크기 1 · 비차단(최신 프레임만) · 모델 {a.model} "
                  f"(변형 {self.variant}, 입력 {self.w}x{self.h}) · raw {a.raw} · 영상 송출 {'켬' if video else '끔'}"
                  f" · 깊이 {'켬' if need_depth else '끔'}")
            edge_script = pipeline.create(dai.node.Script)
            edge_script.setScript(self.edge_script)
            edge_script.inputs["det"].setBlocking(False)
            edge_script.inputs["det"].setMaxSize(1)
            net.out.link(edge_script.inputs["det"])
            out_q = net.out.createOutputQueue()
            self.edge_queue = edge_q = edge_script.outputs["edge"].createOutputQueue()
            frame_q = depth_q = sys_q = calc_q = cfg_q = None
            stereo = make_stereo_depth(pipeline, dai, a.fps, self.w, self.h) if need_depth else None
            if video:                                         # 영상 송출: RGB 프레임(+ --video on 이면 깊이 프레임)을 이더넷으로
                frame_q = net.passthrough.createOutputQueue(maxSize=4, blocking=False)
                if video_depth:
                    depth_q = stereo.depth.createOutputQueue(maxSize=4, blocking=False)
            if raw:                                           # Raw 숫자 데이터: 칩 안에서 계산해 숫자만 받는다
                meta_script = pipeline.create(dai.node.Script)
                meta_script.setScript(META_SCRIPT)
                meta_script.inputs["frame"].setBlocking(False)
                meta_script.inputs["frame"].setMaxSize(1)
                net.passthrough.link(meta_script.inputs["frame"])
                self.meta_queue = meta_script.outputs["meta"].createOutputQueue(maxSize=8, blocking=False)
                calc = pipeline.create(dai.node.SpatialLocationCalculator)
                stereo.depth.link(calc.inputDepth)
                calc.inputDepth.setBlocking(False)
                calc.inputDepth.setMaxSize(1)
                try:
                    calc.inputConfig.setWaitForMessage(True)  # 프레임마다 호스트가 보낸 박스 설정이 있어야 한 번 계산 (보낸 순서대로 결과가 나옴)
                except AttributeError:
                    pass
                cfg_q = calc.inputConfig.createInputQueue()
                calc_q = calc.out.createOutputQueue(maxSize=8, blocking=False)
                syslog = pipeline.create(dai.node.SystemLogger)
                syslog.setRate(1.0)
                sys_q = syslog.out.createOutputQueue(maxSize=8, blocking=False)
            if not video and not raw:                         # 영상도 Raw 도 끔: 처리된 RGB 프레임을 칩 안에서 버린다 (그냥 두면 장치가 연결을 끊는 경우가 있음)
                drop = pipeline.create(dai.node.Script)
                drop.setScript(self.drop_script)
                net.passthrough.link(drop.inputs["x"])
            elif not video:                                   # Raw 켬 + 영상 끔: 프레임은 메타 Script 만 읽는다 (이더넷으로 안 나감)
                pass
            pipeline.start()
            try:
                while pipeline.isRunning() and not stop.is_set():
                    frame_msg = frame_q.get() if frame_q else None
                    msg = out_q.get()
                    t_pc = time.time()
                    now_dai = dai.Clock.now()
                    total_ms = (now_dai - msg.getTimestamp()).total_seconds() * 1000
                    dev_t = msg.getTimestampDevice().total_seconds()
                    seq = msg.getSequenceNum()
                    outs = {nm: np.asarray(msg.getTensor(nm, dequantize=True), np.float32) for nm in msg.getAllLayerNames()}
                    res = proc(outs, seq, dev_t)
                    raw_bytes, frame, extra = 0, None, {}
                    depth_bytes, depth_frame = 0, None
                    if frame_msg is not None:
                        raw_bytes = int(frame_msg.getData().nbytes)
                        depth_msgs = depth_q.tryGetAll() if depth_q is not None else []
                        depth_bytes = sum(int(m.getData().nbytes) for m in depth_msgs)
                        if debug:                              # 디버그 모드: 영상을 변환하고 마스크·박스를 그린다 (실차 모드는 하지 않음 → 후처리 시간 비교용)
                            t_draw = time.perf_counter()
                            rgb = frame_msg.getCvFrame()
                            frame = draw_debug(rgb.copy() if dc else rgb, res["dets"], proc.last_masks)
                            depth_frame = depth_msgs[-1].getFrame() if depth_msgs else None
                            res["post_ms"] += (time.perf_counter() - t_draw) * 1000
                            if dc:      # post_ms 에 포함하지 않음 (저장·창 표시 시간은 별도)
                                frame, depth_frame = dc.process(seq, rgb, frame, depth_msgs, res["dets"], t_pc, total_ms, self.edge_by_seq.get(seq))
                        raw_bytes += depth_bytes
                    if raw:
                        cfg_q.send(self._spatial_config(dai, res["dets"]))        # 이 프레임의 박스 → 칩이 다음 깊이 프레임으로 X/Y/Z 계산
                        self.pending.append((seq, res["dets"][:a.max_dets]))
                        self._collect_spatial(calc_q)
                        js = self._wait_meta(seq) or {}
                        if self.session is None:
                            shim = SimpleNamespace(getClasses=lambda: base.NAMES, getConfidenceThreshold=lambda: a.conf)
                            self.session = oak_full.session_info(device, dai, shim, a.model, js.get("w", self.w), js.get("h", self.h))
                        extra = dict(meta=dict(exposure_us=js.get("expo", 0), iso=js.get("iso", 0), color_temp_k=js.get("ct", 0),
                                               lens_pos=js.get("lens", -1), source_w=js.get("sw", 0), source_h=js.get("sh", 0),
                                               cam_instance=js.get("inst", 0), frame_type=js.get("typ", 0), frame_w=js.get("w", self.w),
                                               frame_h=js.get("h", self.h), hfov_deg=js.get("hfov", 0), vfov_deg=js.get("vfov", 0),
                                               ts_device_us=js.get("tsdev", 0), ts_host_us=int(msg.getTimestamp().total_seconds() * 1e6),
                                               det_latency_ms=total_ms,
                                               frame_latency_ms=(now_dai - frame_msg.getTimestamp()).total_seconds() * 1000 if frame_msg is not None else 0),
                                     ext=None, tele=[oak_full.telemetry_row(x) for x in sys_q.tryGetAll()],
                                     depth_bytes=depth_bytes, depth_frame=depth_frame)
                    for buf in edge_q.tryGetAll():
                        self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
                    yield dict(seq=seq, dev_t=dev_t, t_pc=t_pc, total_ms=total_ms, post_ms=res["post_ms"], raw_bytes=raw_bytes,
                               frame=frame, dets=res["dets"], seg=res["seg"], **extra)
            finally:
                time.sleep(0.4)
                if raw:
                    self._collect_spatial(calc_q)
                for buf in edge_q.tryGetAll():
                    self.edge_by_seq[buf.getSequenceNum()] = float(bytes(buf.getData()).decode())
                if self.raw_logger:
                    self.raw_logger.close()
                if dc:
                    dc.close()


class AYolomFake(_SourceBase):
    """카메라 없이 같은 후처리·기록·CAN 경로를 시험하는 가짜 입력 (모양은 진짜와 같은 무작위 원시 출력)."""

    def __init__(self, args):
        super().__init__(args)
        self.variant = variant_of(args.archive or "", getattr(args, "variant", None))
        self.w, self.h = 512, 288
        self.session = oak_full.fake_session(args.model) if self.raw else None
        self.rng = np.random.default_rng(0)

    def frames(self, stop):
        a, t0, seq, last_tele = self.args, time.monotonic(), 0, 0.0
        out_dir = Path(a.out_dir).expanduser()
        if self.raw and getattr(a, "raw_log", "on") == "on":
            self.raw_logger = RawLog(out_dir, getattr(a, "raw_tensors_every", 0.0), getattr(a, "log_files", "all") == "candidates")
        proc = Processor(self.variant, self.w, self.h, a.conf, 0.7, a.max_dets, getattr(a, "seg_min_pixels", SEG_MIN_PIXELS),
                         self.raw_logger.logger if self.raw_logger else None)
        prev = None
        try:
            while not stop.is_set():
                seq += 1
                true_t = time.monotonic() - t0
                edge = 80 + float(self.rng.uniform(-5, 5))
                self.edge_by_seq[seq] = edge
                dev_t = 1000 + true_t * (1 + a.fake_ppm * 1e-6)      # 카메라 시계가 --fake-ppm 만큼 빠르게 (드리프트 시험용)
                res = proc(proc.io.fake_outputs(self.rng), seq, dev_t)
                extra = {}
                if self.raw:
                    tele = []
                    if true_t - last_tele >= 1.0:
                        tele, last_tele = [oak_full.fake_telemetry()], true_t
                    if prev is not None:                                  # 칩 깊이 좌표는 한 프레임 늦게 돌아온다 (진짜와 같은 흐름)
                        ext = [oak_full.fake_ext() for _ in prev[1]]
                        self.ready.append((prev[0], prev[1], ext))
                        if self.raw_logger:
                            self.raw_logger.add_spatial(prev[0], prev[1], ext)
                    prev = (seq, res["dets"][:a.max_dets])
                    extra = dict(meta=oak_full.fake_meta(seq), ext=None, tele=tele,
                                 depth_bytes=self.w * self.h * 2 if self.video_depth else 0, depth_frame=None)
                yield dict(seq=seq, dev_t=dev_t, t_pc=time.time(), total_ms=edge + 8, post_ms=res["post_ms"],
                           raw_bytes=(self.w * self.h * 3 + (self.w * self.h * 2 if self.video_depth else 0)) if self.video else 0, frame=None,
                           dets=res["dets"], seg=res["seg"], **extra)
                time.sleep(max(0, t0 + seq / a.fps - time.monotonic()))
        finally:
            if self.raw_logger:
                self.raw_logger.close()
