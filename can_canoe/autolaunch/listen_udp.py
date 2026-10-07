#!/usr/bin/env python3
"""카메라가 자동 실행 후 UDP 로 보내는 결과를 받아 주기와 지연을 센다 (PC 쪽, 어느 환경에서나 실행 가능).

예) python3 listen_udp.py --port 5005 --seconds 60
출력: 첫 패킷까지 걸린 시간(전원 켠 시각부터 재려면 스크립트를 먼저 켜 두고 카메라 전원을 켠다), 초당 패킷 수, 칩 지연(lat_ms) 중앙값.
"""
import argparse
import json
import socket
import statistics
import time

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--port", type=int, default=5005)
ap.add_argument("--seconds", type=float, default=60)
a = ap.parse_args()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", a.port))
sock.settimeout(1.0)
t0 = time.monotonic()
first, lat, times, n_det = None, [], [], 0
print(f"UDP {a.port} 대기 중 ({a.seconds:.0f}초)… 카메라 전원을 켜세요")
while time.monotonic() - t0 < a.seconds:
    try:
        data, addr = sock.recvfrom(65535)
    except socket.timeout:
        continue
    now = time.monotonic()
    if first is None:
        first = now - t0
        print(f"첫 패킷: {first:.1f}초 (보낸 곳 {addr[0]})")
    msg = json.loads(data)
    lat.append(msg["lat_ms"])
    times.append(now)
    n_det += len(msg["d"])
if times:
    span = times[-1] - times[0]
    print(f"패킷 {len(times)}개, 주기 {len(times) / span:.2f}/s, 칩 지연 중앙 {statistics.median(lat):.1f} ms, 검출 {n_det}개")
else:
    print("패킷이 오지 않았다 (플래시 실패, 목적지 IP/포트, 방화벽, 링크를 확인)")
