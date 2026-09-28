#!/usr/bin/env python3
# ============================================================================
# 모델이 처리한 이미지를 1초에 정해진 장 수(기본 5장)만큼 골라 JPEG로 저장하는 모듈.
# data_logger.py 처럼 혼자 실행하지 않고, run_yolov6n.py 가 불러서(import) 같이 돈다.
#
# 모델은 1초에 약 21번 연산하는데, 그걸 전부 저장하면 5분에 6000장이 넘는다.
# 그래서 0.2초(= 1/5초)마다 한 장씩만 골라 저장한다 → 5분이면 약 1500장.
#
# 저장 위치: runs/<날짜_시각>/images/  (events.csv 등이 있는 같은 실행 폴더 안)
# 파일 이름: 00012_t002.412s_seq000051.jpg
#            │     │          └ 칩이 붙인 프레임 순번 → events.csv 의 seq 와 같은 번호라 서로 찾아볼 수 있다
#            │     └ 기록 시작 후 몇 초에 저장했는지
#            └ 저장 순서 (0부터)
# ============================================================================

import time                         # 0.2초 간격을 재려고
from pathlib import Path            # 폴더 경로를 다루려고

import cv2                          # 이미지를 JPEG 파일로 쓰려고 (OpenCV)


class ImageSaver:
    def __init__(self, folder, per_second=5):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.period = 1.0 / per_second      # 저장 간격(초). 5장/초면 0.2초
        self.start = time.monotonic()       # 기록 시작 시각 (파일 이름의 t 값 기준)
        self.next_time = self.start         # 다음 저장 예정 시각
        self.count = 0                      # 지금까지 저장한 장 수
        print(f"이미지 저장 시작: {self.folder} (1초에 {per_second}장)")

    def save(self, frame, seq):
        """카메라 코드가 프레임을 받을 때마다 부른다. 저장할 차례일 때만 실제로 저장한다."""
        now = time.monotonic()
        if now < self.next_time:
            return                          # 아직 0.2초가 안 지났으면 이번 프레임은 건너뜀

        # 다음 예정 시각을 "지금 + 0.2초"가 아니라 "이전 예정 + 0.2초"로 잡는다.
        # 프레임은 약 47ms 간격으로 오기 때문에, 지금 기준으로 잡으면 매번 조금씩 늦어져서
        # 1초에 5장보다 적게 저장된다. 예정 시각 기준으로 잡으면 평균이 정확히 5장이 된다.
        self.next_time += self.period
        if self.next_time < now:
            # 화면이 멈추는 등으로 한참 밀렸으면, 밀린 만큼 몰아서 저장하지 않고 지금부터 다시 센다.
            self.next_time = now + self.period

        name = f"{self.count:05d}_t{now - self.start:07.3f}s_seq{seq:06d}.jpg"
        cv2.imwrite(str(self.folder / name), frame)
        self.count += 1

    def close(self):
        """카메라 코드가 끝날 때 부른다. 몇 장 저장했는지 알려준다."""
        duration = time.monotonic() - self.start
        print(f"이미지 {self.count}장 저장 ({duration:.1f}s) → {self.folder}")
