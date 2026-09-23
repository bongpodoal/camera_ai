"""호스트 CPU(onnxruntime) 추론 성능 계측.

엣지(RVC2)로 옮겼을 때 실제로 이득인지 판단하려면 비교 대상이 필요하다. 같은 모델을
호스트 CPU에서 onnxruntime으로 재어 엣지 수치와 나란히 놓는다.

edge_benchmark.py와 같은 JSON 스키마로 저장해 summarize.py가 함께 집계할 수 있게 한다.

사용법:
    python3 benchmark/host_benchmark.py --model benchmark/models/yolov8n_traffic_288x512.onnx \
        --label yolov8n-traffic-host
"""
import argparse
import json
import platform
import socket
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnxruntime as ort

RESULTS_DIR = Path(__file__).resolve().parent / 'results'


def pct(vals, q):
    if not vals:
        return None
    k = (len(vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser(description='호스트 CPU(onnxruntime) 추론 성능 계측')
    ap.add_argument('--model', required=True, help='ONNX 파일 경로')
    ap.add_argument('--label', required=True)
    ap.add_argument('--duration', type=float, default=30.0)
    ap.add_argument('--warmup', type=float, default=5.0)
    ap.add_argument('--threads', type=int, help='onnxruntime 스레드 수(기본: 자동)')
    ap.add_argument('--note', default='')
    args = ap.parse_args()

    opts = ort.SessionOptions()
    if args.threads:
        opts.intra_op_num_threads = args.threads
    sess = ort.InferenceSession(args.model, opts, providers=['CPUExecutionProvider'])

    inp = sess.get_inputs()[0]
    shape = [d if isinstance(d, int) else 1 for d in inp.shape]
    blob = np.random.rand(*shape).astype(np.float32)
    name = inp.name
    _, _, h, w = shape

    # 워밍업 (첫 추론은 메모리 할당/최적화가 섞여 느리다)
    t_end = time.monotonic() + args.warmup
    while time.monotonic() < t_end:
        sess.run(None, {name: blob})

    lat = []
    t_end = time.monotonic() + args.duration
    t0 = time.monotonic()
    while time.monotonic() < t_end:
        s = time.perf_counter()
        sess.run(None, {name: blob})
        lat.append((time.perf_counter() - s) * 1000.0)
    span = time.monotonic() - t0

    lat.sort()
    result = {
        'label': args.label,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'mode': 'host-cpu',
        'note': args.note,
        'model': {
            'source': f'local:{args.model}',
            'input_width': w,
            'input_height': h,
            'shaves_per_thread': None,
            'inference_threads': args.threads or opts.intra_op_num_threads or None,
            'queue_size': None,
        },
        'device': {
            'id': platform.processor() or platform.machine(),
            'platform': 'host-cpu',
            'connection': 'n/a',
            'ip': None,
        },
        'config': {
            'duration_s': args.duration,
            'warmup_s': args.warmup,
            'camera_fps': None,
            'report_every': None,
        },
        'metrics': {
            'reports': 1,
            'messages': len(lat),
            'measured_seconds': round(span, 3),
            'fps': round(len(lat) / span, 2),
            'latency_ms': {
                'mean': round(statistics.fmean(lat), 2),
                'p50': round(pct(lat, 0.50), 2),
                'p90': round(pct(lat, 0.90), 2),
                'p95': round(pct(lat, 0.95), 2),
                'p99': round(pct(lat, 0.99), 2),
                'min': round(lat[0], 2),
                'max': round(lat[-1], 2),
                'samples': len(lat),
            },
        },
        'env': {
            'onnxruntime': ort.__version__,
            'python': platform.python_version(),
            'host': socket.gethostname(),
            'os': platform.platform(),
            'cpu': platform.processor(),
        },
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out = RESULTS_DIR / f'{args.label}_host-cpu_{stamp}.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    m = result['metrics']
    print(f"[{args.label}] host-cpu | 입력 {w}x{h}")
    print(f"  FPS {m['fps']}  |  지연 평균 {m['latency_ms']['mean']}ms "
          f"p95 {m['latency_ms']['p95']}ms  |  {m['messages']}회 추론")
    print(f'  저장: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
