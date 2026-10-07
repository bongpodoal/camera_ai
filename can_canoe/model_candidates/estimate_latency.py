#!/usr/bin/env python3
"""구조 연산량(GMACs)으로 이 칩(OAK-D, RVC2)에서의 추론 시간과 칩 지연을 추정한다. 실측이 아니라 **추정**이다.

보정에 쓴 실측·공식 값 (연산량 ÷ 1프레임 시간 = 유효 처리량 GMACs/s):
    yolov6n 512×384        약 2.74 GMACs(11.4 GFLOPs@640 환산)  21.41 FPS  (이 저장소 실측)        → 약 58.7
    YOLOv8n 416×416        약 1.84 GMACs(8.7 GFLOPs@640 환산)   31.3 FPS   (Luxonis 공식 표)        → 약 57.6
    YOLO-P 320×320         3.85 GMACs (measure_arch.py)         15.61 inf/s (Luxonis 모델 저장소)   → 약 60.1
    신호등 YOLO11s 512×288 약 3.85 GMACs(21.4 GFLOPs@640 환산)  9.75 FPS   (이 저장소 실측)        → 약 37.6  (어텐션 등 새 블록이라 낮음)
→ 합성곱 중심의 YOLO 계열은 약 58 GMACs/s, 새 블록이 섞이면 약 38 GMACs/s 로 본다.
칩 지연 ≈ 추론 간격 × 1.5 (이 저장소 실측: yolov6n 71 ms / 46.7 ms = 1.51, YOLO11s 154 / 102.6 = 1.50, 최신화 큐 사용 시)
깊이를 켜면 신경망이 쓸 SHAVE 가 8 → 6 개로 줄어드니 처리량이 6/8 로 준다고 가정했다 (가정).
"""
EFF_FAST, EFF_SLOW = 58.0, 38.0
LAT_FACTOR = 1.5
DEPTH_FACTOR = 6 / 8
BUDGET_MS = 100

# (이름, 입력, GMACs, 효율 등급)  GMACs 는 measure_arch.py 결과
ROWS = [
    ("A-YOLOM(n)", "512x288", 3.35, "fast"), ("A-YOLOM(n)", "640x384", 5.58, "fast"),
    ("A-YOLOM(s)", "512x288", 10.52, "fast"),
    ("HybridNets(d3)", "512x256", 4.57, "slow"), ("HybridNets(d3)", "640x384", 8.58, "slow"),
    ("YOLOP", "320x320", 3.85, "fast"), ("YOLOP", "512x288", 5.55, "fast"),
    ("YOLOPX", "512x288", 26.66, "slow"),
    ("YOLOPv2", "512x288", 21.71, "slow"),
]


def estimate(g, grade, depth):
    eff = (EFF_FAST if grade == "fast" else EFF_SLOW) * (DEPTH_FACTOR if depth else 1.0)
    infer = g / eff * 1000
    return infer, infer * LAT_FACTOR


def main():
    print(f"| 모델 | 입력 | GMACs | 추론(ms) 깊이 끔 | 칩 지연(ms) 깊이 끔 | 추론(ms) 깊이 켬 | 칩 지연(ms) 깊이 켬 | ≤{BUDGET_MS} ms (끔/켬) |")
    print("|---|---|---|---|---|---|---|---|")
    for name, size, g, grade in ROWS:
        i0, l0 = estimate(g, grade, False)
        i1, l1 = estimate(g, grade, True)
        ok = lambda v: "O" if v <= BUDGET_MS else "X"
        print(f"| {name} | {size} | {g:.2f} | {i0:.0f} | {l0:.0f} | {i1:.0f} | {l1:.0f} | {ok(l0)} / {ok(l1)} |")


if __name__ == "__main__":
    main()
