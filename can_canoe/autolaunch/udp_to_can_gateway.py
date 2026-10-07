#!/usr/bin/env python3
"""카메라가 UDP 로 보내는 검출 결과를 받아 CAN 메시지(oakd_canoe.dbc)로 바꿔 보낸다. 카메라 PC·Linux 보드·소형 컴퓨터에서 상시 실행하는 **변환 장치**의 기준 구현.

카메라(RVC2)에는 CAN 포트가 없고 standalone 에서는 Script 가 이더넷/UART/GPIO 로만 내보낼 수 있으므로, CAN 까지 가려면 이런 변환 장치가 필요하다.
예) python3 udp_to_can_gateway.py --port 5005 --interface socketcan --channel can0
    python3 udp_to_can_gateway.py --port 5005 --interface virtual --channel gw      (시험)
"""
import argparse
import json
import socket
import sys
from pathlib import Path

import can

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from can_msgs import MODEL_IDS, det_box, frame_status, open_bus      # noqa: E402


def packet_to_can(msg, model_id=2):
    """UDP 패킷 하나 → CAN 메시지 목록 (FRAME_STATUS + DET_BOX 들)."""
    dets = sorted(msg["d"], key=lambda d: -d[1])[:8]
    out = [frame_status(msg["n"], len(msg["d"]), 0, msg.get("lat_ms", 0), 0, model_id, False)]
    for i, d in enumerate(dets):
        out.append(det_box(msg["n"], i, *d))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--model", choices=MODEL_IDS, default="traffic_light")
    ap.add_argument("--seconds", type=float, default=0, help="0 이면 계속 실행")
    a = ap.parse_args(argv)
    bus = open_bus(a.interface, a.channel, **({} if a.interface == "virtual" else {"bitrate": a.bitrate}))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", a.port))
    sock.settimeout(0.5)
    sent = 0
    import time
    t0 = time.monotonic()
    try:
        while not a.seconds or time.monotonic() - t0 < a.seconds:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            for m in packet_to_can(json.loads(data), MODEL_IDS[a.model]):
                bus.send(m)
                sent += 1
    finally:
        bus.shutdown()
        sock.close()
    print(f"CAN 송신 {sent}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
