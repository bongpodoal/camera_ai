# MATLAB 정리 스크립트 (교수님 과제 3·4·5번째 줄)

| 스크립트 | 줄 | 입력 | 출력 |
|---|---|---|---|
| `object_threshold_compare.m` | 3 객체 인식률 임계값 비교 | 노트북+카메라 1분 30초 촬영 폴더(`raw_ai_candidates.csv`, `raw_rgb/`) | 임계값 0.05~0.95(0.1 간격) 박스 색 비교 이미지, 클래스별 개수 표·그래프 |
| `object_depth_check.m` | 4 객체 + depth | `run_line45.sh STAGE=objdepth` 폴더 | 프레임별 이미지(객체명·신뢰도·거리·depth 박스), mp4, 병합 CSV, 거리 요약 |
| `rgb_onoff_delay.m` | 5 RGB ON/OFF 지연 | `run_line45.sh STAGE=rgbonoff` 폴더들 | 지연 비교 그림·표(차이의 95% 신뢰구간) |

실행: MATLAB 명령창에서 `runDir = '<폴더>'; object_depth_check` (지연 비교는 `baseDir = '<runs 폴더>'; rgb_onoff_delay`).
터미널 일괄 실행은 `matlab -batch "runDir='<폴더>'; object_depth_check"` (화면 없는 모드는 끝나면 MATLAB 을 종료한다).

- 촬영(`../run_line45.sh`)은 사용자가 "시작" 한 뒤 카메라 PC 에서만 한다. 가짜 입력 점검은 `FAKE=1`.
- `object_threshold_compare.m` 는 후보 파일(NMS 전, 프레임당 점수 상위 200개)로 NMS 를 다시 해서 임계값을 바꿔 본다. 후보가 잘린 프레임이 있으면 경고하고, 낮은 임계값 개수는 하한이다.
- 노트북 촬영 명령 예: `can_demo.py --model a_yolom_n --raw on --video on --mode debug --save-every 0 --depth-check on --log-files all --raw-tensors-every 0 --duration 90 ...`
- 정답 거리가 있으면 실행 폴더에 `ground_truth.csv`(`t_start_s,t_end_s,z_true_mm`) 를 두면 `object_depth_check.m` 이 오차를 계산한다.
- 가짜 데이터로만 시험했다(실제 촬영 폴더로는 미검증).
