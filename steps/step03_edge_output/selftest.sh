#!/usr/bin/env bash
# 카메라 없이 Step 03 전체 흐름을 검증한다: 기록 → 검토 → CAN 왕복.
#   ./selftest.sh            # 가짜 데이터 300초 (5분 분량, 실제 속도 아님)
#   ./selftest.sh 20         # 20초 분량
set -euo pipefail
cd "$(dirname "$0")"
DUR="${1:-300}"
RUN="runs/selftest_mock"
rm -rf "$RUN"

echo "=== 1. 파라미터 카탈로그 ==="
python3 params.py

echo; echo "=== 2. 가짜 소스로 ${DUR}s 기록 ==="
python3 edge_logger.py --source mock --duration "$DUR" --out "$RUN"

echo; echo "=== 3. 검토 ==="
python3 review.py summary  "$RUN"
python3 review.py frame    "$RUN" --t 12.5
python3 review.py sheet    "$RUN" --every "$(python3 -c "print(max(1, $DUR/30))")"
python3 review.py timeline "$RUN"

echo; echo "=== 4. CAN 왕복 (가상 버스) ==="
python3 can_bridge.py selftest --run "$RUN"
