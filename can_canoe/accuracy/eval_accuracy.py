#!/usr/bin/env python3
"""예측 CSV(chip_infer.py 또는 pt_infer.py 가 만듦)와 정답 라벨을 비교해 인식률 표를 만든다.

예) python3 eval_accuracy.py --images ~/camera_eval_data/images/val --labels ~/camera_eval_data/labels/val \
        --preds out/yolov6n_chip.csv out/traffic_light_v8n_chip.csv out/traffic_light_chip.csv --out out/
기준(RG): 채점 정답은 red·green 만. yellow·off 정답에 맞은 예측은 오검출로 세지 않는다. 박스 겹침(IoU) 0.5 이상이면 위치가 맞은 것.
운영 문턱값: yolov6n 0.5, 신호등 모델 0.35 (카메라가 실제로 쓰는 값). --op-conf 로 바꿀 수 있다.
"""
import argparse
import csv
from pathlib import Path

import eval_core as E

COLS = [("model", "모델"), ("source", "실행 방식"), ("conf_thr", "문턱값"), ("gt_boxes", "정답 박스(red+green)"),
        ("tp", "맞춘 수(TP)"), ("fp", "오검출(FP)"), ("fn", "놓침(FN)"), ("precision", "정밀도"), ("recall", "재현율"),
        ("f1", "F1"), ("ap50_detection", "AP50(위치만)"), ("color_accuracy", "색 정확도"),
        ("red_green_swapped", "red↔green 뒤바뀜"), ("end_to_end_recall", "색까지 맞춘 재현율"),
        ("ap50_red", "AP50 red"), ("ap50_green", "AP50 green")]


def read_preds(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    model = rows[0]["model"] if rows else Path(path).stem
    source = rows[0].get("source", "") if rows else ""
    preds = [(r["image"], r["cls"], float(r["conf"]), *(float(r[k]) for k in ("x1", "y1", "x2", "y2"))) for r in rows]
    return model, source, preds


def fmt(v):
    return f"{v:.3f}" if isinstance(v, float) else ("" if v is None else str(v))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, help="검증 이미지 폴더 (이름 목록만 사용)")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--preds", nargs="+", required=True)
    ap.add_argument("--op-conf", type=float, help="운영 문턱값을 모든 모델에 이 값으로 통일 (기본: 모델별 실제 값)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    stems = sorted(p.stem for p in Path(a.images).expanduser().glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    gt = E.load_gt(Path(a.labels).expanduser(), stems)
    results = []
    for path in a.preds:
        model, source, preds = read_preds(path)
        # 예측이 한 장도 없는 이미지가 있어도 정답은 그대로 센다 (놓침으로)
        thr = a.op_conf if a.op_conf is not None else (0.5 if model.startswith("yolov6n") else 0.35)
        r = E.evaluate(preds, gt, thr)
        r.update(model=model, source=source)
        results.append(r)
        print(f"{model} [{source}] 문턱값 {thr}: TP {r['tp']} FP {r['fp']} FN {r['fn']}  "
              f"정밀도 {fmt(r['precision'])} 재현율 {fmt(r['recall'])} F1 {fmt(r['f1'])}"
              + (f"  색 {fmt(r['color_accuracy'])} 뒤바뀜 {r['red_green_swapped']}" if "color_accuracy" in r else ""))
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "accuracy_summary.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([k for _, k in COLS])
        for r in results:
            w.writerow([fmt(r.get(c, "")) for c, _ in COLS])
    with open(out / "accuracy_summary.md", "w", encoding="utf-8") as fh:
        fh.write("| " + " | ".join(k for _, k in COLS) + " |\n|" + "---|" * len(COLS) + "\n")
        for r in results:
            fh.write("| " + " | ".join(fmt(r.get(c, "")) for c, _ in COLS) + " |\n")
        fh.write(f"\n정답 이미지 {len(stems)}장, 채점 정답 red+green {results[0]['gt_boxes'] if results else 0}개, IoU 0.5 이상이 맞음. "
                 "색 없는 모델(COCO)은 색 지표가 비어 있다.\n")
        for r in results:
            if "confusion" in r:
                fh.write(f"\n혼동(정답→예측) {r['model']}: {r['confusion']}\n")
    print(f"→ {out / 'accuracy_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
