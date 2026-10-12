#!/usr/bin/env python3
"""BDD100K 를 받은 폴더가 학습 코드가 기대하는 모양인지 점검한다 (읽기만 한다). 학습 PC 에서 실행.

기대하는 구조 (HybridNets 이름 / YOLOP 이름, 둘 다 인식):
    <root>/imgs 또는 images       /train /val   *.jpg                      (100K 이미지: train 70,000 · val 10,000)
    <root>/det_annot 또는 det_annotations  /train /val   *.json            (이미지마다 BDD 형식 JSON: frames[0].objects[].box2d·category·attributes)
    <root>/da_seg_annot 또는 da_seg_annotations /train /val *.png          (주행 영역 마스크)
    <root>/ll_seg_annot 또는 ll_seg_annotations /train /val *.png          (차선 마스크)
점검: 폴더·장수, 이름(stem)이 서로 짝이 맞는지, JSON 샘플의 클래스 분포와 신호등 색 분포(yellow 가 얼마나 있는지).
예) python3 check_bdd_layout.py --root ~/datasets/bdd100k --sample 3000
"""
import argparse
import collections
import json
import random
from pathlib import Path

NAMES = {"images": ("imgs", "images"), "det": ("det_annot", "det_annotations"),
         "da": ("da_seg_annot", "da_seg_annotations"), "ll": ("ll_seg_annot", "ll_seg_annotations")}
EXPECT = {"train": 70000, "val": 10000}


def find(root, kinds):
    for k in kinds:
        if (root / k).is_dir():
            return root / k
    return None


def stems(folder, suffixes):
    return {p.stem for p in folder.iterdir() if p.suffix.lower() in suffixes} if folder and folder.is_dir() else set()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--sample", type=int, default=3000, help="클래스 분포를 볼 JSON 장수(train 에서 무작위)")
    a = ap.parse_args()
    root = Path(a.root).expanduser()
    bad = []
    found = {}
    for key, kinds in NAMES.items():
        found[key] = find(root, kinds)
        print(f"[{key}] 폴더: {found[key] if found[key] else '없음 (' + ' 또는 '.join(kinds) + ')'}")
        if not found[key]:
            bad.append(f"{key} 폴더 없음")
    for split in ("train", "val"):
        sets = {}
        for key, suf in (("images", {".jpg", ".jpeg"}), ("det", {".json"}), ("da", {".png"}), ("ll", {".png"})):
            sets[key] = stems(found[key] / split, suf) if found[key] else set()
        n = {k: len(v) for k, v in sets.items()}
        ok_n = n["images"] == EXPECT[split]
        print(f"{split}: 이미지 {n['images']} (기대 {EXPECT[split]}) {'OK' if ok_n else '확인'} · det JSON {n['det']} · 주행영역 PNG {n['da']} · 차선 PNG {n['ll']}")
        if not ok_n:
            bad.append(f"{split} 이미지 {n['images']}장 (기대 {EXPECT[split]})")
        for key in ("det", "da", "ll"):
            missing = sets["images"] - sets[key]
            extra = sets[key] - sets["images"]
            if missing or extra:
                print(f"  - {key}: 이미지에 짝이 없는 라벨 {len(extra)}개 / 라벨이 없는 이미지 {len(missing)}개")
                bad.append(f"{split} {key} 짝 불일치")
    det_train = found["det"] / "train" if found["det"] else None
    if det_train and det_train.is_dir():
        files = sorted(det_train.glob("*.json"))
        random.seed(0)
        sample = random.sample(files, min(a.sample, len(files)))
        cats, colors, bad_json = collections.Counter(), collections.Counter(), 0
        for f in sample:
            try:
                objs = json.load(open(f))["frames"][0]["objects"]
            except Exception:
                bad_json += 1
                continue
            for o in objs:
                if "box2d" not in o:
                    continue
                cats[o["category"]] += 1
                if o["category"] == "traffic light":
                    colors[o.get("attributes", {}).get("trafficLightColor", "속성 없음")] += 1
        print(f"\nJSON 샘플 {len(sample)}장 (읽기 실패 {bad_json}): 클래스별 박스 수 {dict(cats.most_common())}")
        print(f"신호등 색 속성 분포: {dict(colors)}")
        if bad_json:
            bad.append("JSON 읽기 실패")
        if not colors:
            bad.append("신호등 색 속성을 못 찾음 (라벨 형식 확인)")
    print("\n결과:", "이상 없음" if not bad else f"확인 필요 {len(bad)}건: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
