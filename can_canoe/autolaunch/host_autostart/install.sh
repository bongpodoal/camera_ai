#!/bin/bash
# 사용: sudo ./install.sh [--user 사용자] [--python /path/to/python3]   (제거: sudo ./install.sh --remove)
# Kvaser Leaf v3 처럼 can0 가 없는 PC: sudo env CAN_INTERFACE=kvaser CAN_IF=0 ./install.sh --python ~/venvs/camera_ai/bin/python
# 이 PC 에 서비스를 등록해 부팅할 때 자동 실행되게 한다. 시스템 설정을 바꾸므로 사용자가 직접 승인하고 실행한다.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
USER_NAME="${SUDO_USER:-$(id -un)}"
PY="$(command -v python3)"
if [ "${1:-}" = "--remove" ]; then
  systemctl disable --now oakd-autostart.service || true
  rm -f /etc/systemd/system/oakd-autostart.service
  systemctl daemon-reload
  echo "제거 완료"; exit 0
fi
while [ $# -gt 0 ]; do
  case "$1" in --user) USER_NAME="$2"; shift 2;; --python) PY="$2"; shift 2;; *) echo "알 수 없는 옵션 $1"; exit 1;; esac
done
OUT_BASE="$(getent passwd "$USER_NAME" | cut -d: -f6)/oakd_auto_runs"
chmod +x "$HERE/run_oakd.sh"
[ -f /etc/default/oakd-autostart ] || cat >/etc/default/oakd-autostart <<CFG
# 필요하면 바꾼다
CAMERA_IP=169.254.1.222
CAN_INTERFACE=${CAN_INTERFACE:-socketcan}
CAN_IF=${CAN_IF:-can0}
CAN_BITRATE=500000
MODEL=traffic_light_v8n
RAW=off
CFG
sed -e "s|@USER@|$USER_NAME|g" -e "s|@REPO@|$REPO|g" -e "s|@PY@|$PY|g" -e "s|@OUT_BASE@|$OUT_BASE|g" \
  "$HERE/oakd-autostart.service" > /etc/systemd/system/oakd-autostart.service
systemctl daemon-reload
systemctl enable oakd-autostart.service
echo "등록 완료. 지금 바로 시작: sudo systemctl start oakd-autostart  / 로그: journalctl -u oakd-autostart -f"
