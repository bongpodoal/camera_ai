#!/usr/bin/env bash
# 과제 측정 한 번에: 모델 3개 × Raw 끔/켬 = 6번 (카메라 PC 에서 실행)
#
# 시작 전: CANoe 쪽에서 측정(Measurement)을 시작하고 Logging 을 켜 둔다 (README 의 CANoe 설정).
#          CANoe 는 6번을 한 로그에 이어서 찍어도 된다. 끝나면 로그를 이 PC 로 옮겨 analyze.py 를 돌린다.
#
# 환경변수:  PYTHON(기본 python3)  INTERFACE(기본 socketcan)  CHANNEL(기본 can0)  NIC(이더넷 이름, 예 enp5s0)
#            FD(기본 0 = 클래식 CAN, FD 는 FD=1)  DATA_BITRATE(기본 2000000)  FD_FRAMES(기본 0, FD=1 일 때 메시지도 FD 프레임으로: FD_FRAMES=1)
#            DURATION(초, 기본 300)  FPS(기본 5)
#            MODELS(기본 "yolov6n traffic_light_v8n traffic_light")  RAWS(기본 "off on")  — 일부만 돌릴 때: MODELS=traffic_light RAWS=on DURATION=60
#
# Raw 켬 = 카메라로 받을 수 있는 모든 데이터 (깊이·텔레메트리·보정·장치 정보 + RGB·깊이 프레임). can_canoe/MEASURE.md 참고.
set -u
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}; INTERFACE=${INTERFACE:-socketcan}; CHANNEL=${CHANNEL:-can0}
DURATION=${DURATION:-300}; FPS=${FPS:-5}; NIC=${NIC:-}
OUT=runs/$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
MODELS=${MODELS:-"yolov6n traffic_light_v8n traffic_light"}; RAWS=${RAWS:-"off on"}
total=$(( $(echo $MODELS | wc -w) * $(echo $RAWS | wc -w) ))
i=0
for model in $MODELS; do
  for raw in $RAWS; do
    i=$((i+1))
    extra=()
    [ "${FD:-0}" = 1 ] && extra+=(--fd --data-bitrate "${DATA_BITRATE:-2000000}")
    [ "${FD_FRAMES:-0}" = 1 ] && extra+=(--fd-frames)
    [ -n "$NIC" ] && extra+=(--nic "$NIC")
    echo "=== $i/$total  $model  raw $raw  (${DURATION}s) ==="
    "$PYTHON" can_demo.py --model "$model" --raw "$raw" --fps "$FPS" --duration "$DURATION" \
        --interface "$INTERFACE" --channel "$CHANNEL" "${extra[@]}" --out-dir "$OUT/${i}_${model}_${raw}"
    echo "  → 확인: fps_avg 5.0 근처 · dropped 0 · can_tx_errors 0 (위 summary 줄)"
    if [ "$i" -lt "$total" ]; then echo "카메라 재부팅 대기 20초 (링크가 끊겼다 돌아온다)"; sleep 20; fi
  done
done
echo "끝. Windows 로그를 가져온 뒤:  $PYTHON analyze.py --log <canoe.asc> --runs-root $OUT   (Raw 켬 추가 메시지: $PYTHON extra_messages.py --log <canoe.asc> --out $OUT/추가메시지)"
