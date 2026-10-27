#!/usr/bin/env bash
# 교수님 과제 4·5번째 줄 촬영·측정 (카메라 PC + OAK-D, a_yolom_n L0 6 SHAVE). 사용자가 "시작" 한 뒤에만 실행한다.
#   STAGE=objdepth  : 객체 + depth 확인 영상 1분 (프레임별 RGB·깊이 PNG, 객체별 칩·호스트 거리, 박스 그린 영상)
#   STAGE=rgbonoff  : RGB 송출 off / RGB 송출 on(RGB 프레임만) 지연 비교, 각 1분 x REPEAT 회 (깊이는 둘 다 칩에서 계산)
#   STAGE=all       : objdepth 다음 rgbonoff
# 사용 예: ARCHIVE=~/models/a_yolom_n_cam01_ft1_L0_lane_only_512x288_openvino_2022.1_6shave.blob NIC=enp5s0 STAGE=all ./run_line45.sh
set -u
cd "$(dirname "$0")"
STAGE=${STAGE:-all}
ARCHIVE=${ARCHIVE:?ARCHIVE=<L0 6 SHAVE .blob 또는 NNArchive 경로> 를 지정}
NIC=${NIC:?NIC=<카메라가 꽂힌 이더넷 이름, 예 enp5s0> 를 지정}
IP=${IP:-169.254.1.222}
DURATION=${DURATION:-60}
REPEAT=${REPEAT:-2}                 # rgbonoff: off→rgb 를 몇 번 반복할지 (순서 효과를 줄이려고 번갈아 반복)
WAIT=${WAIT:-30}                    # 실행 사이 대기 초 (직전 run 직후 시작 실패 방지)
PY=${PY:-python3}
INTERFACE=${INTERFACE:-virtual}     # CAN 은 이 과제에서 필요 없어 가상 채널 (실제 CAN 측정이면 kvaser 등으로 바꾸고 Windows 로거를 먼저 켠다)
CHANNEL=${CHANNEL:-line45}
STAMP=${STAMP:-$(date +%Y%m%d_%H%M)}
OUTROOT=${OUTROOT:-runs}
WINDOW=${WINDOW:-0}                 # 1 이면 objdepth 에서 debug 창을 띄운다

FAKE=${FAKE:-0}                     # 1 이면 카메라 없이 가짜 입력 (코드 점검용)
FK=(); [ "$FAKE" = 1 ] && FK=(--fake)
if [ "$FAKE" != 1 ]; then
    [ -f "$ARCHIVE" ] || { echo "모델 파일이 없다: $ARCHIVE"; exit 1; }
    ping -c 2 -W 2 "$IP" >/dev/null 2>&1 || { echo "카메라($IP)가 ping 에 응답하지 않는다. 케이블·NIC 고정 IP(169.254.1.10/16)를 확인"; exit 1; }
fi
mkdir -p "$OUTROOT"

run() {   # run <이름> <can_demo 추가 인자...>
    local name=$1; shift
    local out="$OUTROOT/${STAMP}_$name"
    echo "=== $name  ($(date +%H:%M:%S), ${DURATION}s) → $out"
    $PY can_demo.py --model a_yolom_n --archive "$ARCHIVE" --ip "$IP" --fps 5 --duration "$DURATION" \
        --raw on --log-files all --raw-tensors-every 0 --nic "$NIC" \
        --interface "$INTERFACE" --channel "$CHANNEL" --out-dir "$out" "${FK[@]}" "$@" \
        | tee "$out.log" | tail -3
}

if [ "$STAGE" = objdepth ] || [ "$STAGE" = all ]; then
    # 4번째 줄: 객체 + depth 영상. 매 프레임 raw_rgb/·images/(깊이 PNG)·detections.csv·raw_spatial.csv(칩 X/Y/Z, ROI)·depth_boxes.csv(호스트 Z)
    nw=(--no-window); [ "$WINDOW" = 1 ] && nw=()
    run objdepth --video on --mode debug --save-every 0 --depth-check on "${nw[@]}"
    [ "$STAGE" = all ] && { echo "대기 ${WAIT}s"; sleep "$WAIT"; }
fi

if [ "$STAGE" = rgbonoff ] || [ "$STAGE" = all ]; then
    # 5번째 줄: RGB 송출 off 와 on(rgb) 의 지연. 두 조건 모두 vehicle 모드·Raw 켬(깊이·메타는 칩에서 계산)·같은 기록이라 차이는 RGB 프레임 송출뿐.
    for i in $(seq 1 "$REPEAT"); do
        run "rgbonoff_off_$i" --video off --mode vehicle
        echo "대기 ${WAIT}s"; sleep "$WAIT"
        run "rgbonoff_rgb_$i" --video rgb --mode vehicle
        [ "$i" -lt "$REPEAT" ] && { echo "대기 ${WAIT}s"; sleep "$WAIT"; }
    done
fi
echo "끝. 결과 폴더: $OUTROOT/${STAMP}_*  (MATLAB: can_canoe/matlab/ 의 스크립트로 정리)"
