"""YOLO 데이터셋을 MATLAB이 읽을 수 있는 형태로 변환한다.

YOLO는 정규화된 중심 좌표(cx, cy, w, h)를, MATLAB의 boxLabelDatastore는 픽셀 단위
좌상단 좌표 [x y width height]를 쓴다. 이 차이를 메우고, MATLAB에서 한 줄로 읽히는
long-format CSV를 만든다.

    imageFilename, className, x, y, width, height     # 박스 하나가 한 줄

MATLAB 쪽 로딩은 같은 디렉터리의 load_dataset.m 참고.

사용법:
    python3 training/yolo_to_matlab.py <데이터셋_루트> [--out training/matlab]
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

IMG_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def read_class_names(root):
    """data.yaml에서 클래스 이름을 읽는다. 없으면 인덱스를 이름으로 쓴다."""
    y = root / 'data.yaml'
    if not y.exists():
        return None
    names = {}
    text = y.read_text()
    # names가 dict({0: person, ...})든 list(- person)든 둘 다 받아준다.
    in_names = False
    idx = 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('names:'):
            in_names = True
            rest = s.split(':', 1)[1].strip()
            if rest.startswith('['):                       # names: [a, b, c]
                for i, n in enumerate(x.strip().strip('\'"')
                                      for x in rest.strip('[]').split(',')):
                    if n:
                        names[i] = n
                return names or None
            continue
        if in_names:
            if s.startswith('-'):                           # - person
                names[idx] = s[1:].strip().strip('\'"')
                idx += 1
            elif ':' in s and s.split(':', 1)[0].strip().isdigit():
                k, v = s.split(':', 1)                      # 0: person
                names[int(k.strip())] = v.strip().strip('\'"')
            elif s and not s.startswith('#'):
                break
    return names or None


def find_split(root, split):
    img_dir = root / 'images' / split
    lbl_dir = root / 'labels' / split
    if not img_dir.is_dir():
        img_dir, lbl_dir = root / split / 'images', root / split / 'labels'
    return (img_dir, lbl_dir) if img_dir.is_dir() else (None, None)


def convert(root, split, names, out_dir):
    img_dir, lbl_dir = find_split(root, split)
    if img_dir is None:
        return None

    rows = []
    cls_count = Counter()
    skipped = 0

    for img in sorted(img_dir.iterdir()):
        if img.suffix.lower() not in IMG_EXT:
            continue
        lbl = lbl_dir / (img.stem + '.txt')
        if not lbl.exists():
            continue
        try:
            W, H = Image.open(img).size
        except Exception:
            skipped += 1
            continue

        for line in lbl.read_text().splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            c = int(float(parts[0]))
            cx, cy, w, h = (float(v) for v in parts[1:])

            # 정규화 중심 -> 픽셀 좌상단. MATLAB은 1-기반 인덱싱이라 +1 한다.
            px_w, px_h = w * W, h * H
            x = (cx * W) - px_w / 2 + 1
            y = (cy * H) - px_h / 2 + 1

            # 이미지 경계로 클립 (라벨이 살짝 넘치는 경우가 흔하다)
            x, y = max(1.0, x), max(1.0, y)
            px_w = min(px_w, W - x + 1)
            px_h = min(px_h, H - y + 1)
            if px_w <= 0 or px_h <= 0:
                continue

            cname = (names or {}).get(c, f'class_{c}')
            rows.append([str(img.resolve()), cname,
                         round(x, 2), round(y, 2), round(px_w, 2), round(px_h, 2)])
            cls_count[cname] += 1

    out = out_dir / f'{split}.csv'
    with out.open('w', newline='') as f:
        wtr = csv.writer(f)
        wtr.writerow(['imageFilename', 'className', 'x', 'y', 'width', 'height'])
        wtr.writerows(rows)

    imgs = len({r[0] for r in rows})
    print(f'  [{split}] 이미지 {imgs}장 · 박스 {len(rows)}개 -> {out.name}')
    if skipped:
        print(f'    ! 열지 못한 이미지 {skipped}장 건너뜀')
    for c, n in cls_count.most_common():
        print(f'      {c}: {n}')
    return {'images': imgs, 'boxes': len(rows), 'classes': cls_count}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', help='YOLO 데이터셋 루트')
    ap.add_argument('--out', default='training/matlab', help='CSV 출력 디렉터리')
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f'경로가 없습니다: {root}')
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    names = read_class_names(root)
    print(f'데이터셋: {root}')
    print(f'클래스: {len(names)}개' if names else '클래스: data.yaml 없음 - 인덱스를 이름으로 사용')
    if names and len(names) <= 20:
        print(f'  {names}')
    print()

    stats = {s: convert(root, s, names, out_dir) for s in ('train', 'val', 'test')}
    stats = {k: v for k, v in stats.items() if v}
    if not stats:
        print('변환할 split을 찾지 못했습니다.')
        return 1

    print()
    print(f'완료 - {out_dir}/ 에 CSV {len(stats)}개. MATLAB에서 load_dataset.m으로 읽으세요.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
