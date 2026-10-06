"""CAN 메시지 정의·변환 (oakd_canoe.dbc). PC(카메라 쪽) → CANoe 로 보낸다.

시간축 규칙: 시간축은 CANoe 가 프레임을 받은 시각(Trace 시각 = 로그 파일의 시각) 하나뿐이다.
이 프로그램은 시각을 CAN 에 싣지 않는다. 카메라 시계와 PC 시계는 CANoe 시계와 얼마나 벌어지는지만 나중에 잰다.
"""
from pathlib import Path

import can
import cantools

HERE = Path(__file__).resolve().parent
DB = cantools.database.load_file(str(HERE / "oakd_canoe.dbc"))
MSG = {m.name: m for m in DB.messages}
ID_FRAME, ID_DET, ID_PERF = (MSG[n].frame_id for n in ("FRAME_STATUS", "DET_BOX", "PERF"))
MODEL_IDS = {"yolov6n": 0, "yolov8n": 1, "traffic_light": 2, "traffic_light_11n": 3}
MODEL_NAMES = {v: k for k, v in MODEL_IDS.items()}
BITS_PER_FRAME = 135        # 11비트 ID + 8바이트 데이터, 비트 스터핑 최악 근사


FD_FRAMES = False     # True 면 같은 8바이트 내용을 CAN FD 프레임(전송 속도 전환 BRS 켬)으로 보낸다
FD_BRS = True


def set_fd_frames(on, brs=True):
    global FD_FRAMES, FD_BRS
    FD_FRAMES, FD_BRS = on, brs


def _msg(name, values):
    """신호 범위를 넘는 값은 잘라서(clamp) CAN 프레임으로 만든다."""
    m = MSG[name]
    out = {}
    for s in m.signals:
        v = float(values.get(s.name, 0) or 0)
        out[s.name] = min(max(v, s.minimum), s.maximum)
    return can.Message(arbitration_id=m.frame_id, is_extended_id=False, data=m.encode(out, strict=False),
                       is_fd=FD_FRAMES, bitrate_switch=FD_FRAMES and FD_BRS)


def frame_status(seq, det_count, fps, edge_ms, seq_gap, model_id, raw_on):
    return _msg("FRAME_STATUS", dict(Seq=seq % 65536, DetCount=det_count, Fps=fps, EdgeMs=edge_ms,
                                     SeqGap=seq_gap, ModelId=model_id, RawOn=int(raw_on)))


def det_box(seq, index, label, conf, xmin, ymin, xmax, ymax):
    return _msg("DET_BOX", dict(SeqLo=seq % 16, Index=index, Label=label, Conf=conf,
                                Cx=(xmin + xmax) / 2, Cy=(ymin + ymax) / 2, W=xmax - xmin, H=ymax - ymin))


def perf(pc_ms, post_ms, eth_kbps, can_load_pct, dropped_total):
    return _msg("PERF", dict(PcMs=pc_ms, PostMs=post_ms, EthKBps=eth_kbps, CanLoadPct=can_load_pct,
                             DroppedTotal=dropped_total))


def decode(msg):
    m = DB.get_message_by_frame_id(msg.arbitration_id)
    return m.name, m.decode(msg.data, decode_choices=False)
