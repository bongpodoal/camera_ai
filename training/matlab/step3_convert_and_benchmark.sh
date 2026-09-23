#!/usr/bin/env bash
# step3 - MATLAB이 내보낸 ONNX를 엣지에 올려 기준선과 같은 조건으로 측정한다.
#
#   ./training/matlab/step3_convert_and_benchmark.sh traffic_yolox.onnx [장치IP]
#
# 기준선과 맞추는 조건 (benchmark/README.md 참고):
#   입력 512x288 · SHAVE 6 · 10초 x 3회 · warmup 3초 · 호스트 디코딩 경로
set -uo pipefail
cd "$(dirname "$0")/../.."

ONNX="${1:?ONNX 파일 경로를 지정하세요}"
IP="${2:-169.254.1.222}"
LABEL="${LABEL:-matlab-yolox}"

[ -f "$ONNX" ] || { echo "파일 없음: $ONNX"; exit 1; }

echo "=== 1. ONNX -> RVC2 블롭 변환 ==="
echo "  주의: blobconverter는 모델을 Luxonis 서버로 업로드합니다."
python3 - "$ONNX" <<'PY'
import sys, blobconverter
src = sys.argv[1]
try:
    p = blobconverter.from_onnx(
        model=src, data_type="FP16", shaves=6, use_cache=False,
        output_dir="benchmark/models",
        optimizer_params=["--scale_values=[255,255,255]"],
    )
    print("변환 성공:", p)
except Exception as e:
    print("변환 실패:", type(e).__name__, str(e)[:600])
    print()
    print("Myriad X 플러그인이 지원하지 않는 연산자가 있을 가능성이 높습니다.")
    print("MATLAB에서 더 단순한 아키텍처(YOLOv4-tiny 등)로 바꿔 다시 시도하세요.")
    sys.exit(1)
PY
[ $? -eq 0 ] || exit 1

BLOB=$(ls -t benchmark/models/*.blob | head -1)
echo "  블롭: $BLOB"

echo
echo "=== 2. 벤치마크 (기준선과 동일 조건, 3회 반복) ==="
for mode in throughput camera; do
  for r in 1 2 3; do
    printf "  %-10s r%d  " "$mode" "$r"
    timeout 200 python3 benchmark/edge_benchmark.py \
      --model "$BLOB" --ip "$IP" --label "${LABEL}-r${r}" --mode "$mode" \
      --duration 10 --warmup 3 --report-every 20 \
      --note "MATLAB YOLOX, 호스트 디코딩 경로" 2>&1 \
      | grep -oE "FPS [0-9.]+.*" || echo "(실패)"
    sleep 8
  done
done

echo
echo "=== 3. 집계 ==="
python3 benchmark/aggregate.py --out benchmark/BASELINE.md
cat benchmark/BASELINE.md
