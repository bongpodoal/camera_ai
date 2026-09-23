# ⑤ NNArchive (.tar.xz) — 블롭 + 사용 설명서

예제 코드가 실제로 받는 파일. `fetch_example.py`가 모델 주에서 받아 `example/`에 풀고 `report.md`를 쓴다.
이 파일 하나에 ①~④의 흔적이 모두 남아 있다.

```bash
python3 05_nnarchive/fetch_example.py                       # 두 예제 모두
python3 05_nnarchive/fetch_example.py --model yolov6-nano   # 예제 기본값만
```

| 파일 | 역할 |
|---|---|
| `fetch_example.py` | 받기 → 풀기 → ⑤④③②① 순으로 해석 → `example/<모델>/report.md` |
| `example/yolov6-nano/` | 예제 기본값. `config.json`, `buildinfo.json`, `report.md` (+ superblob) |
| `example/luxonis_yolov6-nano_r2-coco-512x288/` | 512×288 판. 같은 구성 |

## config.json 핵심 (실측)

| 항목 | yolov6-nano (기본값) | r2-coco-512x288 |
|---|---|---|
| 아카이브 파일명 | `YOLOv6_Nano-R2_COCO_512x288.rvc2.tar.xz` | `yolov6n-r2-288x512.rvc2.tar.xz` |
| **실제 입력** | **512×384** (파일명과 다름) | 512×288 |
| 전처리 scale | 1.0 (블롭이 처리) | 1.0 |
| 후처리 | `YOLO` / `yolov6r2` (칩 위 디코딩) | 동일 |
| 클래스 · conf · IoU · 최대 | 80 · 0.5 · 0.5 · 300 | 동일 |
| 변환 일자 | 2025-10-01 | 2024-07-24 |

**예제 기본값은 파일명이 512x288인데 실제 입력은 512×384다.** 성능을 적을 때는
`getInputWidth()/getInputHeight()`로 확인한 값을 쓴다.
