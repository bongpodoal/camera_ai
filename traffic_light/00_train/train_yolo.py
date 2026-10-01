#!/usr/bin/env python3
# ============================================================================
# ⓪ 학습 — 신호등 검출 모델을 공개 데이터셋으로 학습한다 (GPU PC 용, 예: RTX 4080).
#
# 기존 traffic_light.pt (YOLO11s) 는 ~/camera/train_yolo.py 로 RTX 3070 에서 학습했다 (2026-07-28).
# 같은 데이터·같은 설정으로 모델 크기만 바꿔(YOLO11n) 칩 속도와 정확도를 비교하려고 이 폴더로 옮겼다.
#
# 데이터셋: HuggingFace lincolnn2026/traffic_light_dataset (블랙박스 1280×720, train 3,997 / val 567장)
#   클래스 0 red · 1 yellow · 2 green · 3 off. yellow(val 20개)·off(val 14개)는 표본이 적어 수치를 믿기 어렵다.
#
# 실행:  python3 00_train/train_yolo.py [train|val|resume] [기본모델] [학습크기] [이름]
#        기본값 = train yolo11n.pt 960 traffic_light_11n   (960 = 기존 11s 와 같은 조건)
# 결과:  00_train/runs/<이름>/weights/best.pt → 01_pytorch_pt/<이름>.pt 로 복사
#        → 다음 단계: python3 02_onnx/export_onnx.py 416x416 <이름>  (③④⑤ 도 같은 인자)
# ============================================================================

import shutil                       # best.pt 를 ① 폴더로 복사하려고
import sys                          # 실행 인자 읽기
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                      # traffic_light 폴더

MODE = sys.argv[1] if len(sys.argv) > 1 else "train"
BASE_MODEL = sys.argv[2] if len(sys.argv) > 2 else "yolo11n.pt"   # COCO 사전학습에서 시작 (신호등을 이미 앎)
IMGSZ = int(sys.argv[3]) if len(sys.argv) > 3 else 960            # 신호등은 작아서 기본 640 보다 크게
NAME = sys.argv[4] if len(sys.argv) > 4 else "traffic_light_11n"

DATA_DIR = HERE / "datasets" / "traffic_light"          # git 제외 (1.1 GB)
DATA_YAML = DATA_DIR / "data.yaml"
RUN_DIR = HERE / "runs"


def prepare_dataset():
    """데이터셋이 없으면 내려받고 data.yaml 을 만든다. 이미 있으면 그대로 쓴다."""
    if not (DATA_DIR / "labels" / "val").exists():
        from huggingface_hub import snapshot_download   # 내려받을 때만 필요 (pip install huggingface_hub)
        print("데이터셋 내려받는 중 (약 1.1 GB) ...")
        # images/·labels/ 만 받는다 (xml/ 은 원본 VOC 라벨, zip 은 같은 내용의 묶음이라 필요 없음)
        snapshot_download("lincolnn2026/traffic_light_dataset", repo_type="dataset",
                          allow_patterns=["images/*", "labels/*"], local_dir=str(DATA_DIR))
    DATA_YAML.write_text(f"path: {DATA_DIR}\ntrain: images/train\nval: images/val\n"
                         "names: ['red', 'yellow', 'green', 'off']\n")
    for split in ("train", "val"):
        print(f"  {split}: 이미지 {len(list((DATA_DIR / 'images' / split).glob('*.jpg')))}장")


def train():
    model = YOLO(BASE_MODEL)
    model.train(
        data=str(DATA_YAML), epochs=60, imgsz=IMGSZ,
        batch=16,          # RTX 4080 16 GB 기준. 메모리 부족(OOM)이면 8 로
        patience=15,       # 15 epoch 동안 나아지지 않으면 조기 종료
        device=0, project=str(RUN_DIR), name=NAME, exist_ok=True,
        cache=False, workers=8,
        # --- 증강: 기존 11s 와 같게 (신호등 특성) ---
        fliplr=0.0,        # 좌우반전 금지: 가로형 신호등에서 빨강/초록 위치가 뒤바뀐다
        flipud=0.0,
        degrees=0.0,       # 신호등은 항상 수평
        hsv_h=0.005,       # 색상 증강 최소: 색이 곧 정답
        hsv_s=0.5, hsv_v=0.5,   # 채도·밝기는 날씨·노출 변화 흉내
        scale=0.5, mosaic=1.0,
        close_mosaic=10,   # 마지막 10 epoch 은 mosaic 끄고 실제 분포로 미세조정
    )


def resume():
    YOLO(str(RUN_DIR / NAME / "weights" / "last.pt")).train(resume=True)


def validate():
    """학습 크기와 칩 입력 크기(416) 두 가지로 평가한다. 기존 11s 와 비교하려면 이름만 바꿔 val 실행."""
    best = RUN_DIR / NAME / "weights" / "best.pt"
    pt_copy = ROOT / "01_pytorch_pt" / f"{NAME}.pt"
    if best.exists() and not pt_copy.exists():
        shutil.copy2(best, pt_copy)                     # ②~⑤ 가 읽는 위치 (git 제외)
        print(f"복사: {pt_copy}")
    model = YOLO(str(pt_copy if pt_copy.exists() else best))
    for size in (IMGSZ, 416):
        metrics = model.val(data=str(DATA_YAML), imgsz=size, device=0, plots=False, verbose=False)
        print(f"\n=== {NAME} · 평가 크기 {size} ===")
        for i, name in model.names.items():
            p, r, ap50, ap = metrics.class_result(i)
            print(f"  {name:8s} precision={p:.3f} recall={r:.3f} mAP50={ap50:.3f} mAP50-95={ap:.3f}")
        print(f"  전체 mAP50={metrics.box.map50:.3f}  mAP50-95={metrics.box.map:.3f}")


if __name__ == "__main__":
    prepare_dataset()
    if MODE == "train":
        train()
    elif MODE == "resume":
        resume()
    validate()
