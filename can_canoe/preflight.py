#!/usr/bin/env python3
"""측정 전 점검 (카메라 PC 에서 실행). 빠진 것을 한 번에 알려 준다. 아무것도 바꾸지 않는다.

예) python3 preflight.py --interface kvaser --channel 0 --nic enp6s0
    python3 preflight.py --interface socketcan --channel can0 --nic enp5s0 --ip 169.254.1.222
"""
import argparse
import importlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARCHIVES = {
    "traffic_light_v8n": "traffic_light/05_nnarchive/traffic_light_v8n-416x416.tar.xz",
    "traffic_light": "traffic_light/05_nnarchive/traffic_light-416x416.tar.xz",
}
bad = []


def check(name, ok, hint=""):
    print(f"  {'OK  ' if ok else 'FAIL'} {name}" + (f"   → {hint}" if not ok and hint else ""))
    if not ok:
        bad.append(name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--nic", default="")
    ap.add_argument("--ip", default="169.254.1.222")
    a = ap.parse_args()

    print("1) 파이썬 패키지")
    for mod, hint in (("can", "pip install python-can"), ("cantools", "pip install cantools"), ("numpy", "pip install numpy"),
                      ("cv2", "pip install opencv-python"), ("depthai", "카메라용 venv 에서 실행 (예: ~/venvs/camera_ai/bin/python)")):
        try:
            importlib.import_module(mod)
            check(mod, True)
        except ImportError:
            check(mod, False, hint)

    print("2) DBC 와 메시지")
    try:
        sys.path.insert(0, str(HERE))
        import can_msgs
        names = {m.name for m in can_msgs.DB.messages}
        need = {"FRAME_STATUS", "DET_BOX", "PERF", "DET_POS", "DET_ROI", "FRAME_META_A", "DEV_TEMP", "CALIB_A", "DEV_INFO"}
        check(f"oakd_canoe.dbc 에 Raw 켬 메시지 포함 ({len(names)}개)", need <= names, "git pull 로 최신 DBC 받기")
    except Exception as e:
        check("oakd_canoe.dbc 읽기", False, str(e))

    print("3) 카메라")
    r = subprocess.run(["ping", "-c", "1", "-W", "1", a.ip], capture_output=True)
    check(f"{a.ip} 응답 (ping)", r.returncode == 0, "PoE 전원·이더넷 링크로컬 설정(169.254.1.10/16)·다른 연결 프로필이 가로채지 않는지 확인")
    try:
        import depthai as dai
        devs = dai.Device.getAllAvailableDevices()
        check(f"depthai 가 장치를 봄 ({len(devs)}개)", len(devs) > 0, "자동 탐색은 불안정함. ping 이 되면 무시해도 됨(IP 로 직접 연결)")
    except ImportError:
        pass

    print("4) 모델 파일 (이 PC 에만 있고 git 에는 없음)")
    check("yolov6n 은 공식 모델 이름으로 내려받음 (인터넷 또는 캐시)", True)
    for m, p in ARCHIVES.items():
        check(f"{m}: {p}", (ROOT / p).exists(), "② ~ ⑤ 변환 스크립트로 만들거나 다른 PC 에서 복사")

    print("5) CAN")
    if a.interface == "socketcan":
        r = subprocess.run(["ip", "-details", "link", "show", a.channel], capture_output=True, text=True)
        check(f"{a.channel} 인터페이스 존재", r.returncode == 0, "sudo ip link set can0 up type can bitrate 500000")
        check(f"{a.channel} 이 UP", "UP" in r.stdout and "state DOWN" not in r.stdout, "sudo ip link set can0 up type can bitrate 500000")
    elif a.interface == "kvaser":
        try:
            import can
            cfgs = can.detect_available_configs("kvaser")
            check(f"Kvaser 채널 보임 ({len(cfgs)}개)", len(cfgs) > 0, "Kvaser LinuxCAN 드라이버 설치·USB 연결 확인")
        except Exception as e:
            check("Kvaser 채널 확인", False, str(e))
    else:
        print(f"  (건너뜀) {a.interface} 는 직접 확인")

    print("6) 이더넷 이름")
    if a.nic:
        r = subprocess.run(["ip", "link", "show", a.nic], capture_output=True)
        check(f"{a.nic} 존재 (--nic 값, 실제 이더넷 수신량을 재려면 필요)", r.returncode == 0, "ip -br link 로 OAK-D 가 꽂힌 이름 확인")
    else:
        print("  (--nic 없음) 이더넷 수신량은 프레임 크기 합(하한)으로만 계산됨. 정확히 재려면 --nic 지정")

    print("\n결과:", "모두 통과" if not bad else f"점검 필요 {len(bad)}건: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
