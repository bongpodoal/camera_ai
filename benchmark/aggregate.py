"""반복 측정 결과를 모델별로 묶어 평균과 편차를 낸다.

단발 측정은 우연한 값일 수 있으므로, MATLAB/Simulink 모델과 비교할 기준선은 반복 측정의
평균으로 둔다. 같은 (모델, 모드, 입력크기, 측정길이) 조합을 하나의 그룹으로 본다.

사용법:
    python3 benchmark/aggregate.py
    python3 benchmark/aggregate.py --out benchmark/BASELINE.md
"""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / 'results'

MODE_TITLE = {
    'throughput': '엣지 처리 용량 (throughput — NN 포화 상태의 모델 순수 성능)',
    'camera': '엣지 실제 경로 (camera — 카메라→NN, 차량 체감 성능)',
    'host-cpu': '호스트 CPU 기준선 (onnxruntime)',
}


def short_name(source):
    """긴 경로/슬러그를 표에 들어갈 이름으로 줄인다."""
    s = source.split(':', 1)[-1]
    return Path(s).name if '/' in s and not s.startswith('luxonis/') else s


def load():
    groups = defaultdict(list)
    for f in sorted(RESULTS_DIR.glob('*.json')):
        d = json.loads(f.read_text())
        m, mo = d['metrics'], d['model']
        # 변환/디코딩 경로가 다르면 다른 조건이므로 그룹을 나눈다.
        if d['mode'] == 'host-cpu':
            decode = '—'
        elif mo.get('on_chip_decode'):
            decode = '칩 위'
        else:
            decode = '호스트'
        key = (d['mode'], short_name(mo['source']),
               f"{mo['input_width']}x{mo['input_height']}",
               d['config']['duration_s'], decode)
        groups[key].append(d)
    return groups


def stat(vals):
    """(평균, 표준편차, 최소, 최대). n=1이면 편차는 None."""
    mean = statistics.fmean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else None
    return mean, sd, min(vals), max(vals)


def render(groups):
    out = []
    for mode in ('throughput', 'camera', 'host-cpu'):
        keys = [k for k in groups if k[0] == mode]
        if not keys:
            continue
        rows = []
        for k in keys:
            runs = groups[k]
            fps = [r['metrics']['fps'] for r in runs]
            f_mean, f_sd, f_lo, f_hi = stat(fps)
            lats = [r['metrics']['latency_ms']['mean'] for r in runs
                    if r['metrics'].get('latency_ms')]
            row = {
                'model': k[1], 'input': k[2], 'n': len(runs), 'dur': k[3],
                'decode': k[4],
                'fps_mean': f_mean, 'fps_sd': f_sd, 'fps_lo': f_lo, 'fps_hi': f_hi,
                'lat_mean': statistics.fmean(lats) if lats else None,
                'lat_sd': statistics.stdev(lats) if len(lats) > 1 else None,
            }
            rows.append(row)
        rows.sort(key=lambda r: -r['fps_mean'])

        has_lat = any(r['lat_mean'] is not None for r in rows)
        head = ['모델', '입력', '디코딩', 'n', '**평균 FPS**', '표준편차', '최소~최대']
        if has_lat:
            head += ['평균 지연(ms)']
        out.append(f'### {MODE_TITLE[mode]}\n')
        out.append('| ' + ' | '.join(head) + ' |')
        out.append('|' + '|'.join(['---'] * len(head)) + '|')
        for r in rows:
            sd = f"±{r['fps_sd']:.2f}" if r['fps_sd'] is not None else '—'
            cells = [r['model'], r['input'], r['decode'], str(r['n']),
                     f"**{r['fps_mean']:.2f}**", sd,
                     f"{r['fps_lo']:.2f} ~ {r['fps_hi']:.2f}"]
            if has_lat:
                if r['lat_mean'] is None:
                    cells.append('—')
                else:
                    ls = f" ±{r['lat_sd']:.2f}" if r['lat_sd'] is not None else ''
                    cells.append(f"{r['lat_mean']:.2f}{ls}")
            out.append('| ' + ' | '.join(cells) + ' |')
        out.append('')
        durs = {r['dur'] for r in rows}
        out.append(f"측정 길이 {'/'.join(f'{d:g}초' for d in sorted(durs))}, "
                   f"워밍업 구간 제외.\n")
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    args = ap.parse_args()
    groups = load()
    if not groups:
        print('결과가 없습니다.')
        return
    text = render(groups)
    if args.out:
        Path(args.out).write_text(text)
        print(f'저장: {args.out}')
    else:
        print(text)


if __name__ == '__main__':
    main()
