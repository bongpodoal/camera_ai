#!/usr/bin/env bash
# 반복 측정으로 평균 기준선을 만든다. MATLAB/Simulink 모델과 비교할 기준이 되므로
# 모든 모델을 **같은 조건**(측정 길이/워밍업/반복 횟수)으로 잰다.
#
#   ./benchmark/run_averaged_baseline.sh [장치IP]
#
# 측정 길이가 10초인 이유: 신호등 YOLOv8n 블롭이 30초 연속 포화에서 장치를 멈추게 한다
# (재현 확인). 비교 조건을 맞추려면 전체를 가장 짧은 쪽에 맞춰야 한다.
set -uo pipefail   # -e 없음: 한 건 실패해도 나머지는 계속
cd "$(dirname "$0")/.."

IP="${1:-169.254.1.222}"
REPS="${REPS:-3}"
DURATION="${DURATION:-10}"
WARMUP="${WARMUP:-3}"

BLOB="benchmark/models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob"

MODELS=(
  "luxonis/yolov6-nano:r2-coco-512x288|yolov6n-stock"
  "luxonis/yolov10-nano:coco-512x288|yolov10n-stock"
  "luxonis/yolo26-nano:coco-512x288|yolo26n-stock"
  "$BLOB|yolov8n-traffic"
)

for entry in "${MODELS[@]}"; do
  slug="${entry%%|*}"; label="${entry##*|}"
  for mode in throughput camera; do
    for r in $(seq 1 "$REPS"); do
      echo "=== $label / $mode / rep $r ==="
      timeout 180 python3 benchmark/edge_benchmark.py \
        --model "$slug" --ip "$IP" --label "${label}-r${r}" --mode "$mode" \
        --duration "$DURATION" --warmup "$WARMUP" --report-every 20 \
        --note "평균 기준선 반복측정 rep${r}" 2>&1 | grep -E "FPS|오류|Error" || echo "  (실패)"
      sleep 6
    done
  done
done

echo
echo "=== 평균 집계 ==="
python3 benchmark/aggregate.py
