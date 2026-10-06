"""PC 와 AURIX 가 공유하는 CAN 메시지 정의·변환 (oakd_aurix.dbc).

시간축 규칙: 모든 시각은 AURIX 의 STM 타이머(µs, 32비트) 하나로 통일한다.
    SYNC  (AURIX → PC, 1초마다) : 지금 AURIX 시각
    FRAME_STATUS (PC → AURIX)   : 처리한 프레임 1장마다 1개
    ECHO  (AURIX → PC)          : FRAME_STATUS 를 받은 순간의 AURIX 시각 (= 그 프레임의 시간축 값)
"""
from pathlib import Path

import can
import cantools

HERE = Path(__file__).resolve().parent
DB = cantools.database.load_file(str(HERE / "oakd_aurix.dbc"))
MSG = {m.name: m for m in DB.messages}
ID_SYNC, ID_ECHO, ID_FRAME, ID_DET = (MSG[n].frame_id for n in ("SYNC", "ECHO", "FRAME_STATUS", "DET_BOX"))
MODEL_IDS = {"yolov6n": 0, "yolov8n": 1, "traffic_light": 2, "traffic_light_11n": 3}
BITS_PER_FRAME = 135        # 11비트 ID + 8바이트 데이터, 비트 스터핑 최악 근사
WRAP_US = 2 ** 32


def _msg(name, values):
    """신호 범위를 넘는 값은 잘라서(clamp) CAN 프레임으로 만든다."""
    m = MSG[name]
    out = {}
    for s in m.signals:
        v = float(values.get(s.name, 0) or 0)
        out[s.name] = min(max(v, s.minimum), s.maximum)
    return can.Message(arbitration_id=m.frame_id, is_extended_id=False, data=m.encode(out, strict=False))


def frame_status(seq, det_count, fps, edge_ms, seq_gap, model_id, raw_on):
    return _msg("FRAME_STATUS", dict(Seq=seq % 65536, DetCount=det_count, Fps=fps, EdgeMs=edge_ms,
                                     SeqGap=seq_gap, ModelId=model_id, RawOn=int(raw_on)))


def det_box(seq, index, label, conf, xmin, ymin, xmax, ymax):
    return _msg("DET_BOX", dict(SeqLo=seq % 16, Index=index, Label=label, Conf=conf,
                                Cx=(xmin + xmax) / 2, Cy=(ymin + ymax) / 2, W=xmax - xmin, H=ymax - ymin))


def sync_msg(cnt, time_us):
    return _msg("SYNC", dict(SyncCnt=cnt % 256, TimeUs=time_us % WRAP_US))


def echo_msg(seq, rx_time_us):
    return _msg("ECHO", dict(Seq=seq % 65536, RxTimeUs=rx_time_us % WRAP_US))


def decode(msg):
    m = DB.get_message_by_frame_id(msg.arbitration_id)
    return m.name, m.decode(msg.data, decode_choices=False)


class Unwrap32:
    """32비트 µs 값이 71.6분마다 0으로 돌아가는 것을 이어 붙인다 (직전 값과 가장 가까운 쪽으로 선택)."""

    def __init__(self):
        self.ref = None

    def __call__(self, x):
        if self.ref is None:
            v = x
        else:
            v = x + round((self.ref - x) / WRAP_US) * WRAP_US
        if self.ref is None or v > self.ref:
            self.ref = v
        return v
