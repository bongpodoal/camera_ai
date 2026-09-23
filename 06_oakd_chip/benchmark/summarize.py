"""results/*.json을 읽어 비교용 마크다운 표로 만든다.

문서화가 목적이므로 출력은 그대로 문서에 붙여넣을 수 있는 형태다.

사용법:
    python3 benchmark/summarize.py                    # 전체
    python3 benchmark/summarize.py --mode throughput  # 모드별
    python3 benchmark/summarize.py --out benchmark/RESULTS.md
"""
import argparse
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / 'results'


def load(mode=None):
    rows = []
    for f in sorted(RESULTS_DIR.glob('*.json')):
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            print(f'건너뜀(파싱 실패): {f.name}')
            continue
        if mode and d.get('mode') != mode:
            continue
        rows.append(d)
    return rows


def fmt_table(rows, mode):
    lat = mode != 'throughput'
    head = ['라벨', '모델', '입력', 'FPS']
    if lat:
        head += ['지연 평균(ms)', 'p95(ms)']
    head += ['메시지', '측정(s)', '시각']

    lines = ['| ' + ' | '.join(head) + ' |',
             '|' + '|'.join(['---'] * len(head)) + '|']
    for d in rows:
        m, mo = d['metrics'], d['model']
        cells = [
            d['label'],
            mo['source'].replace('zoo:', '').replace('local:', ''),
            f"{mo['input_width']}x{mo['input_height']}",
            str(m['fps']),
        ]
        if lat:
            L = m.get('latency_ms')
            cells += [str(L['mean']) if L else '-', str(L['p95']) if L else '-']
        cells += [str(m['messages']), str(m['measured_seconds']), d['timestamp'][:19]]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=('throughput', 'camera', 'host-cpu'))
    ap.add_argument('--out', help='마크다운 파일로 저장 (생략하면 표준출력)')
    args = ap.parse_args()

    chunks = []
    modes = [args.mode] if args.mode else ['throughput', 'camera', 'host-cpu']
    for mo in modes:
        rows = load(mo)
        if not rows:
            continue
        title = {
            'throughput': '엣지 처리 용량 (throughput - NN 포화, 모델 A/B 비교용)',
            'camera': '엣지 실제 경로 (camera - 카메라→NN, 차량 체감 성능)',
            'host-cpu': '호스트 CPU 기준선 (onnxruntime - 엣지 이득 판단용)',
        }[mo]
        chunks.append(f'### {title}\n\n{fmt_table(rows, mo)}')

    if not chunks:
        print('결과 파일이 없습니다. 먼저 edge_benchmark.py를 실행하세요.')
        return

    text = '\n\n'.join(chunks)
    if args.out:
        Path(args.out).write_text(text + '\n')
        print(f'저장: {args.out}')
    else:
        print(text)


if __name__ == '__main__':
    main()
