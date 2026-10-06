#!/usr/bin/env python3
"""CANoe 흉내: CAN 버스에서 받은 프레임을 시각과 함께 .asc 로그로 저장한다.

실제 측정에서는 CANoe 의 Logging 이 이 일을 한다 (README 의 CANoe 설정 참고).
이 스크립트는 CANoe 가 없는 곳에서 흐름을 시험할 때 쓴다 (맥의 가상 버스, 리눅스의 vcan0).

단독 실행: python3 canoe_sim.py --interface socketcan --channel vcan0 --out log.asc
"""
import argparse
import time

import can


class CanoeSim:
    def __init__(self, bus, out_path):
        self.logger = can.Logger(str(out_path))
        self.notifier = can.Notifier(bus, [self.logger])

    def stop(self):
        self.notifier.stop()
        self.logger.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="vcan0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--fd", action="store_true")
    ap.add_argument("--data-bitrate", type=int, default=2000000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    kw = {} if a.interface == "virtual" else {"bitrate": a.bitrate}
    if a.fd and a.interface != "virtual":
        kw.update(fd=True, data_bitrate=a.data_bitrate)
    sim = CanoeSim(can.Bus(interface=a.interface, channel=a.channel, **kw), a.out)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
