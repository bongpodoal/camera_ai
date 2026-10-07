#!/usr/bin/env python3
"""변환 장치 검증 (카메라 불필요): 가짜 카메라 패킷을 UDP 로 보내고 CAN 으로 제대로 나오는지 가상 버스에서 확인한다."""
import json
import socket
import sys
import threading
import time

import can

import udp_to_can_gateway as G
from can_msgs import DB, ID_DET, ID_FRAME

rx = can.Bus(interface="virtual", channel="gw")
t = threading.Thread(target=G.main, args=(["--port", "5099", "--interface", "virtual", "--channel", "gw", "--seconds", "3"],), daemon=True)
t.start()
time.sleep(0.5)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for n in range(1, 6):
    pkt = {"n": n, "lat_ms": 80.0 + n, "d": [[0, 0.91, 0.4, 0.1, 0.44, 0.26], [2, 0.55, 0.7, 0.2, 0.73, 0.3]][: 2 if n % 2 else 1]}
    s.sendto(json.dumps(pkt).encode(), ("127.0.0.1", 5099))
    time.sleep(0.1)
t.join(5)
frames, boxes, last = [], [], None
while True:
    m = rx.recv(timeout=0.3)
    if m is None:
        break
    v = DB.get_message_by_frame_id(m.arbitration_id).decode(m.data, decode_choices=False)
    (frames if m.arbitration_id == ID_FRAME else boxes).append(v)
ok = len(frames) == 5 and len(boxes) == 8 and frames[0]["Seq"] == 1 and abs(frames[2]["EdgeMs"] - 83) < 1
print(f"FRAME_STATUS {len(frames)}개 (기대 5), DET_BOX {len(boxes)}개 (기대 8: 2+1+2+1+2), 첫 Seq {frames[0]['Seq'] if frames else None}")
print("결과:", "통과" if ok else "실패")
sys.exit(0 if ok else 1)
