#!/bin/bash
# 부팅 후 자동 실행: 카메라가 응답할 때까지 기다린 뒤 CAN 을 올리고 can_demo.py 를 실차 모드로 돌린다.
# 설정은 /etc/default/oakd-autostart (install.sh 가 만든다). 실행 사용자는 서비스 파일의 User=.
set -u
CAMERA_IP="${CAMERA_IP:-169.254.1.222}"
CAN_IF="${CAN_IF:-can0}"
CAN_INTERFACE="${CAN_INTERFACE:-socketcan}"   # 이 PC(Kvaser Leaf v3)는 kvaser + CAN_IF=0 (can0 없음)
CAN_BITRATE="${CAN_BITRATE:-500000}"
MODEL="${MODEL:-traffic_light_v8n}"
RAW="${RAW:-off}"
REPO="${REPO:?REPO 가 필요하다}"
PY="${PY:-python3}"
OUT_BASE="${OUT_BASE:-$HOME/oakd_auto_runs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$OUT_BASE/$STAMP"
mkdir -p "$OUT"
log() { echo "$(date +%T.%3N) $*" | tee -a "$OUT/boot.log"; }
log "시작: 모델=$MODEL raw=$RAW 카메라=$CAMERA_IP CAN=$CAN_INTERFACE:$CAN_IF"
# 1) 카메라가 응답할 때까지 (PoE 부팅은 수십 초 걸린다)
until ping -c1 -W1 "$CAMERA_IP" >/dev/null 2>&1; do sleep 2; done
log "카메라 응답"
# 2) CAN 인터페이스 (이미 올라와 있으면 건너뜀)
if [ "$CAN_INTERFACE" = "socketcan" ] && ! ip link show "$CAN_IF" 2>/dev/null | grep -q "UP"; then
  ip link set "$CAN_IF" up type can bitrate "$CAN_BITRATE" && log "$CAN_IF 올림" || log "경고: $CAN_IF 를 올리지 못함"
fi
# 3) 실차 모드로 거의 무기한 실행 (끝나면 systemd 가 다시 시작)
exec "$PY" "$REPO/can_canoe/can_demo.py" --mode vehicle --model "$MODEL" --raw "$RAW" --ip "$CAMERA_IP" \
  --interface "$CAN_INTERFACE" --channel "$CAN_IF" --bitrate "$CAN_BITRATE" --duration 31536000 --out-dir "$OUT"
