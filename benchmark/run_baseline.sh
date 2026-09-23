#!/usr/bin/env bash
# 스톡 모델 베이스라인 일괄 측정. MATLAB 최적화 모델과 비교할 기준선을 만든다.
#
#   ./benchmark/run_baseline.sh [장치IP]
#
# 모델을 추가하려면 MODELS 배열에 "슬러그|라벨" 형식으로 넣으면 된다.
set -uo pipefail   # -e 없음: 한 모델이 실패해도 나머지는 계속 잰다
cd "$(dirname "$0")/.."

IP="${1:-169.254.1.222}"
DURATION="${DURATION:-30}"
WARMUP="${WARMUP:-5}"

MODELS=(
  "luxonis/yolov6-nano:r2-coco-512x288|yolov6n-stock"
  "luxonis/yolov10-nano:coco-512x288|yolov10n-stock"
  "luxonis/yolo26-nano:coco-512x288|yolo26n-stock"
)

for entry in "${MODELS[@]}"; do
  slug="${entry%%|*}"; label="${entry##*|}"
  for mode in throughput camera; do
    echo "=== $label / $mode ==="
    python3 benchmark/edge_benchmark.py \
      --model "$slug" --ip "$IP" --label "$label" --mode "$mode" \
      --duration "$DURATION" --warmup "$WARMUP" \
      --note "스톡 베이스라인" 2>&1 | grep -v "bootloader update"
    sleep 3   # 장치 재부팅/정리 여유
  done
done

echo
echo "=== 집계 ==="
python3 benchmark/summarize.py
