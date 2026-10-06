#!/usr/bin/env python3
"""AURIX 흉내 (보드 없이 PC 쪽 프로그램을 검증하는 용도).

진짜 AURIX 펌웨어(aurix_tc275/)와 같은 일을 한다:
    1초마다 SYNC 송신 (자기 시계 µs)
    FRAME_STATUS 를 받는 순간 자기 시계를 읽어 ECHO 로 돌려보냄
--ppm 은 이 시계가 얼마나 빠르게 가는지(100만분율) — 드리프트 검증용으로 일부러 틀어 둔다.

단독 실행: python3 aurix_sim.py --interface socketcan --channel vcan0
"""
import argparse
import threading
import time

import can

from aurix_can import ID_DET, ID_FRAME, WRAP_US, decode, echo_msg, sync_msg


class AurixSim(threading.Thread):
    def __init__(self, bus, ppm=0.0, sync_period=1.0):
        super().__init__(daemon=True)
        self.bus, self.ppm, self.sync_period = bus, ppm, sync_period
        self.t0 = time.monotonic()
        self.stop_flag = threading.Event()
        self.frames = self.dets = self.syncs = 0
        self.last = None                    # 마지막 FRAME_STATUS 신호 (AURIX 화면에 보여줄 값)

    def tick_us(self):
        return int((time.monotonic() - self.t0) * 1e6 * (1 + self.ppm * 1e-6)) % WRAP_US

    def run(self):
        next_sync, cnt = time.monotonic(), 0
        while not self.stop_flag.is_set():
            if time.monotonic() >= next_sync:
                self.bus.send(sync_msg(cnt, self.tick_us()))
                cnt, self.syncs, next_sync = cnt + 1, self.syncs + 1, next_sync + self.sync_period
            m = self.bus.recv(timeout=0.005)
            if m is None:
                continue
            t_rx = self.tick_us()           # 받자마자 읽는다 (진짜 보드는 수신 인터럽트 첫 줄)
            if m.arbitration_id == ID_FRAME:
                name, v = decode(m)
                self.frames += 1
                self.last = v
                self.bus.send(echo_msg(int(v["Seq"]), t_rx))
            elif m.arbitration_id == ID_DET:
                self.dets += 1

    def stop(self):
        self.stop_flag.set()
        self.join(timeout=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="vcan0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--ppm", type=float, default=0.0)
    a = ap.parse_args()
    kw = {} if a.interface == "virtual" else {"bitrate": a.bitrate}
    sim = AurixSim(can.Bus(interface=a.interface, channel=a.channel, **kw), a.ppm)
    sim.start()
    try:
        while True:
            time.sleep(1)
            print(f"SYNC {sim.syncs}  FRAME {sim.frames}  DET {sim.dets}  마지막 {sim.last}")
    except KeyboardInterrupt:
        sim.stop()
