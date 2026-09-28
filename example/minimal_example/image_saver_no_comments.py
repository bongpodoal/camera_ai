#!/usr/bin/env python3

import time
from pathlib import Path

import cv2


class ImageSaver:
    def __init__(self, folder, per_second=5):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.period = 1.0 / per_second
        self.start = time.monotonic()
        self.next_time = self.start
        self.count = 0
        print(f"이미지 저장 시작: {self.folder} (1초에 {per_second}장)")

    def save(self, frame, seq):
        now = time.monotonic()
        if now < self.next_time:
            return

        self.next_time += self.period
        if self.next_time < now:
            self.next_time = now + self.period

        name = f"{self.count:05d}_t{now - self.start:07.3f}s_seq{seq:06d}.jpg"
        cv2.imwrite(str(self.folder / name), frame)
        self.count += 1

    def close(self):
        duration = time.monotonic() - self.start
        print(f"이미지 {self.count}장 저장 ({duration:.1f}s) → {self.folder}")
