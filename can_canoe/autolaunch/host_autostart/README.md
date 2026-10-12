# host_autostart — 카메라에 전원이 들어오면 호스트(Ubuntu PC)가 자동으로 시작하는 방식

카메라 단독(v2 플래시 standalone)은 이 카메라에서 앱이 시작되지 않아 확인하지 못했다(autolaunch/README.md, RESULT.md).
대체: 호스트 PC 가 부팅하면 systemd 가 `can_demo.py`(실차 모드)를 자동 실행한다. 카메라가 늦게 켜져도 응답할 때까지 기다린다.

| 파일 | 역할 |
|---|---|
| `run_oakd.sh` | 카메라 ping 대기 → CAN 올림 → can_demo.py 실행. 기록은 `~/oakd_auto_runs/<시각>/` |
| `oakd-autostart.service` | systemd 서비스 틀(`@USER@`, `@REPO@` 등을 install.sh 가 채운다). 죽으면 5초 뒤 다시 시작 |
| `install.sh` | 서비스 등록(`sudo ./install.sh`) / 제거(`sudo ./install.sh --remove`) |

시험: 설치 → `sudo reboot` → 로그인 없이 `journalctl -u oakd-autostart` 와 CAN 로거에서 FRAME_STATUS 가 오는지 → 카메라만 껐다 켜서 자동 복귀하는지.
설정은 `/etc/default/oakd-autostart`(모델, raw, 카메라 IP, CAN 인터페이스).
