#!/usr/bin/env bash
# 3모델(YOLOv6n · YOLOv8n · 신호등 YOLO11s, 있으면 신호등 YOLO11n 까지)을 차례로 latency_latest.py 로 잰다.
# 카메라 FPS 와 측정 시간을 인자로 받는다. 최신화 큐 켬 · 화면 창 끔.
# 예) ./run_latest_3models.sh            → 5 fps, 5분씩
#     ./run_latest_3models.sh 5 60       → 5 fps, 1분씩 (빠른 확인)
# 파이썬은 PYTHON 으로 바꿀 수 있다 (카메라 PC: PYTHON=~/venvs/camera_ai/bin/python ./run_latest_3models.sh)
set -u
cd "$(dirname "$0")"

FPS=${1:-5}
DURATION=${2:-300}
PYTHON=${PYTHON:-python3}
OUT="latency_runs/$(date +%Y%m%d_%H%M)_fps${FPS}_latest"

MODELS="yolov6n yolov8n traffic_light"
# YOLO11n 신호등 재학습본이 변환돼 있으면 함께 잰다
[ -f ../traffic_light/05_nnarchive/traffic_light_11n-416x416.tar.xz ] && MODELS="$MODELS traffic_light_11n"
LAST=${MODELS##* }

for MODEL in $MODELS; do
    echo "=== $MODEL (카메라 ${FPS} fps, ${DURATION}초) ==="
    "$PYTHON" latency_latest.py --model "$MODEL" --fps "$FPS" --duration "$DURATION" --out-dir "$OUT" \
        || echo "!! $MODEL 실패 — 다음 모델로 넘어감"
    # 장치가 파이프라인 종료 때 재부팅하며 링크가 끊긴다 → 다음 실행 전 대기
    if [ "$MODEL" != "$LAST" ]; then sleep 20; fi
done

echo
echo "=== 요약: $OUT/summary.csv ==="
column -s, -t "$OUT/summary.csv"
