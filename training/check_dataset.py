"""YOLO 데이터셋을 학습 전에 검증한다.

3000장 규모에서는 눈으로 훑을 수 없으므로, 학습을 돌리기 전에 흔한 파손을 먼저 걸러낸다.
라벨 없는 이미지, 좌표 범위를 벗어난 박스, 폭/높이가 0인 박스, 클래스 불균형 등.

사용법:
    python3 training/check_dataset.py <데이터셋_루트>

기대 구조 (Ultralytics YOLO 표준):
    <루트>/
      data.yaml            # names, nc, train/val 경로
      images/train/*.jpg   labels/train/*.txt
      images/val/*.jpg     labels/val/*.txt

라벨 한 줄 = "<class_id> <cx> <cy> <w> <h>" (모두 0~1로 정규화된 값).
"""
import sys
from collections import Counter
from pathlib import Path

IMG_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def find_pairs(root, split):
    """(이미지, 라벨) 경로 쌍을 찾는다. images/labels 구조와 평면 구조 모두 받아준다."""
    img_dir = root / 'images' / split
    lbl_dir = root / 'labels' / split
    if not img_dir.is_dir():
        img_dir, lbl_dir = root / split / 'images', root / split / 'labels'
    if not img_dir.is_dir():
        return None, None, []
    pairs = []
    for img in sorted(img_dir.iterdir()):
        if img.suffix.lower() in IMG_EXT:
            pairs.append((img, lbl_dir / (img.stem + '.txt')))
    return img_dir, lbl_dir, pairs


def check_split(root, split):
    img_dir, lbl_dir, pairs = find_pairs(root, split)
    if img_dir is None:
        print(f'  [{split}] 디렉터리 없음 - 건너뜀')
        return None

    missing, empty, bad = [], [], []
    boxes = 0
    cls = Counter()
    tiny = 0

    for img, lbl in pairs:
        if not lbl.exists():
            missing.append(img.name)
            continue
        lines = [l.strip() for l in lbl.read_text().splitlines() if l.strip()]
        if not lines:
            empty.append(img.name)
            continue
        for ln, line in enumerate(lines, 1):
            parts = line.split()
            if len(parts) != 5:
                bad.append(f'{lbl.name}:{ln} 필드 {len(parts)}개(5개여야 함)')
                continue
            try:
                c = int(float(parts[0]))
                cx, cy, w, h = (float(x) for x in parts[1:])
            except ValueError:
                bad.append(f'{lbl.name}:{ln} 숫자 파싱 실패')
                continue
            if not all(0.0 <= v <= 1.0 for v in (cx, cy, w, h)):
                bad.append(f'{lbl.name}:{ln} 정규화 범위 벗어남 ({cx:.3f},{cy:.3f},{w:.3f},{h:.3f})')
            if w <= 0 or h <= 0:
                bad.append(f'{lbl.name}:{ln} 폭/높이가 0 이하')
            elif w * h < 1e-5:
                tiny += 1
            cls[c] += 1
            boxes += 1

    print(f'  [{split}] 이미지 {len(pairs)}장 | 박스 {boxes}개 | 클래스 분포 {dict(sorted(cls.items()))}')
    if missing:
        print(f'    ! 라벨 파일 없음 {len(missing)}장: {", ".join(missing[:5])}'
              + (' ...' if len(missing) > 5 else ''))
    if empty:
        print(f'    ! 라벨이 빈 파일 {len(empty)}장 (배경 이미지면 정상): '
              f'{", ".join(empty[:5])}' + (' ...' if len(empty) > 5 else ''))
    if tiny:
        print(f'    ! 면적이 극히 작은 박스 {tiny}개 (전체의 1e-5 미만) - 학습에 해로울 수 있음')
    if bad:
        print(f'    !! 손상된 라벨 {len(bad)}건:')
        for b in bad[:10]:
            print(f'       {b}')
        if len(bad) > 10:
            print(f'       ... 외 {len(bad)-10}건')
    return {'images': len(pairs), 'boxes': boxes, 'classes': cls,
            'missing': len(missing), 'bad': len(bad)}


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    root = Path(sys.argv[1]).expanduser().resolve()
    if not root.is_dir():
        print(f'경로가 없습니다: {root}')
        return 1

    print(f'데이터셋: {root}\n')

    yml = root / 'data.yaml'
    if yml.exists():
        print('data.yaml:')
        for line in yml.read_text().splitlines():
            if line.strip():
                print(f'  {line}')
        print()
    else:
        print('! data.yaml 없음 - Ultralytics 학습에 필요하다\n')

    stats = {s: check_split(root, s) for s in ('train', 'val', 'test')}
    stats = {k: v for k, v in stats.items() if v}

    print()
    tr, va = stats.get('train'), stats.get('val')
    if tr and va:
        total = tr['images'] + va['images']
        print(f'train/val = {tr["images"]}/{va["images"]} '
              f'({va["images"]/total*100:.0f}% val)')
        if va['images'] / total < 0.1:
            print('  ! val 비중이 10% 미만이다 - 성능 추정이 불안정해진다')
    if tr:
        all_cls = tr['classes']
        if len(all_cls) > 1:
            lo, hi = min(all_cls.values()), max(all_cls.values())
            if hi > lo * 10:
                print(f'  ! 클래스 불균형이 크다 (최소 {lo} vs 최대 {hi})')

    broken = sum(v['bad'] + v['missing'] for v in stats.values())
    print()
    print('검증 통과 - 학습 가능' if broken == 0 else f'문제 {broken}건 - 위 내용 확인 필요')
    return 0 if broken == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
