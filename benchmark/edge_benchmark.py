"""OAK-D(RVC2) 엣지 추론 성능 계측 하니스.

같은 조건에서 서로 다른 모델을 재어 비교하기 위한 도구다. 스톡 YOLO 베이스라인과
MATLAB/Simulink로 최적화한 모델을 **같은 스크립트, 같은 조건**으로 재야 비교가 성립하므로,
모델은 인자로만 받고 스크립트 자체는 모델에 대해 아무것도 가정하지 않는다.

측정 모드가 두 가지다. 둘은 서로 다른 질문에 답하므로 보통 둘 다 재둔다:

  throughput (기본) - BenchmarkOut이 NN에 프레임을 **최대 속도로** 밀어넣는다. 카메라
      프레임레이트에 막히지 않는 순수 모델 처리 용량. 모델 A/B 비교는 이 값으로 한다.
  camera            - 카메라 -> NN 실제 경로. 차량에서 실제로 나오는 FPS. 카메라 FPS가
      상한이라 모델이 그보다 빠르면 카메라에 막힌 값이 나온다.

사용법:
    python3 benchmark/edge_benchmark.py --model luxonis/yolov6-nano:r2-coco-512x288 \
        --ip 169.254.1.222 --label yolov6n-stock
    python3 benchmark/edge_benchmark.py --model /path/to/matlab_model.tar.xz \
        --ip 169.254.1.222 --label matlab-opt --mode camera

결과는 results/<label>_<mode>_<timestamp>.json 으로 저장된다.
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

import depthai as dai

RESULTS_DIR = Path(__file__).resolve().parent / 'results'


def load_model(model):
    """모델 주 슬러그 / 로컬 NNArchive(.tar.xz) / raw .blob 중 무엇이든 받아 통일된 기술자를 준다.

    raw .blob은 depthai가 디코딩을 못 하므로 NeuralNetwork로 원시 텐서만 뽑는다. 계측
    목적(FPS/지연)에는 충분하지만, 검출 결과를 쓰려면 호스트에서 디코딩해야 한다.
    """
    p = Path(model)
    if p.exists() and p.suffix == '.blob':
        blob = dai.OpenVINO.Blob(str(p))
        dims = next(iter(blob.networkInputs.values())).dims   # [W, H, C, N]
        return {'kind': 'blob', 'obj': blob, 'width': dims[0], 'height': dims[1],
                'source': f'blob:{p}', 'shaves': blob.numShaves}
    if p.exists():
        ar = dai.NNArchive(str(p))
        return {'kind': 'archive', 'obj': ar, 'width': ar.getInputWidth(),
                'height': ar.getInputHeight(), 'source': f'local:{p}', 'shaves': None}
    path = dai.getModelFromZoo(
        dai.NNModelDescription(model=model, platform='RVC2'), progressFormat='none'
    )
    ar = dai.NNArchive(str(path))
    return {'kind': 'archive', 'obj': ar, 'width': ar.getInputWidth(),
            'height': ar.getInputHeight(), 'source': f'zoo:{model}', 'shaves': None}


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def build_pipeline(pipeline, desc, args):
    w, h = desc['width'], desc['height']

    cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    src = cam.requestOutput((w, h), dai.ImgFrame.Type.BGR888p, fps=args.camera_fps)

    if args.decode:
        # DetectionNetwork는 아카이브의 head 설정을 읽어 칩 위에서 디코딩(NMS 포함)까지 한다.
        # 호스트로는 검출 박스만 나가므로 원시 텐서를 보내는 NeuralNetwork 경로와 조건이 다르다.
        if desc['kind'] != 'archive':
            raise SystemExit('--decode는 head 설정이 있는 NNArchive에만 쓸 수 있습니다 '
                             '(raw .blob에는 디코딩 정보가 없음).')
        nn = pipeline.create(dai.node.DetectionNetwork)
        nn.setNNArchive(desc['obj'])
    else:
        nn = pipeline.create(dai.node.NeuralNetwork)
        if desc['kind'] == 'blob':
            nn.setBlob(desc['obj'])
        else:
            nn.setNNArchive(desc['obj'])
    # SHAVE/스레드를 명시하면 모델 간 비교 조건이 고정된다. 기본값은 depthai 자동 배분.
    if args.shaves:
        nn.setNumShavesPerInferenceThread(args.shaves)
    if args.threads:
        nn.setNumInferenceThreads(args.threads)

    if args.mode == 'throughput':
        # 카메라 프레임 하나를 받아 최대 속도로 복제해 NN을 포화시킨다.
        # 다만 fps=0으로 그냥 흘리면 PoE(TCP) 링크가 넘쳐서 호스트 keepalive ping을 놓치고
        # 장치 연결이 끊긴다(30초 실행에서 실제로 발생). 입력 큐를 작게 잡고 blocking으로
        # 두면 BenchmarkOut이 NN 속도에 맞춰 막히므로, 포화는 유지하면서 링크는 안 넘친다.
        bout = pipeline.create(dai.node.BenchmarkOut)
        bout.setFps(0)   # 0 = as fast as possible
        nn.input.setBlocking(True)
        nn.input.setMaxSize(args.queue_size)
        src.link(bout.input)
        bout.out.link(nn.input)
    else:
        nn.input.setBlocking(False)
        nn.input.setMaxSize(args.queue_size)
        src.link(nn.input)

    bin_ = pipeline.create(dai.node.BenchmarkIn)
    bin_.sendReportEveryNMessages(args.report_every)
    bin_.logReportsAsWarnings(False)
    # throughput 모드는 BenchmarkOut이 같은 프레임을 원래 타임스탬프 그대로 복제하므로
    # 측정된 "지연"이 프레임 나이로 계속 증가한다 - 물리적 의미가 없어서 아예 재지 않는다.
    bin_.measureIndividualLatencies(args.mode == 'camera')
    nn.out.link(bin_.input)

    return nn, bin_.report.createOutputQueue(maxSize=30, blocking=False), (w, h)


def collect(report_q, args, measure_latency):
    """워밍업을 버리고 duration 동안 리포트를 모아 집계한다."""
    t_start = time.monotonic()
    warm_until = t_start + args.warmup
    end = warm_until + args.duration

    msgs = 0
    span = 0.0
    latencies = []
    reports = 0

    while time.monotonic() < end:
        r = report_q.tryGet()
        if r is None:
            time.sleep(0.005)
            continue
        if time.monotonic() < warm_until:
            continue          # 워밍업 구간 리포트는 버린다
        reports += 1
        msgs += r.numMessagesReceived
        span += r.timeTotal
        latencies.extend(float(x) for x in r.latencies)

    if not reports:
        raise RuntimeError('리포트를 하나도 받지 못했습니다 - duration을 늘리거나 '
                           'report-every를 줄여보세요.')

    out = {
        'reports': reports,
        'messages': int(msgs),
        'measured_seconds': round(span, 3),
        'fps': round(msgs / span, 2) if span > 0 else None,
    }
    if not measure_latency:
        out['latency_ms'] = None
        out['latency_note'] = ('throughput 모드에서는 측정하지 않음 - BenchmarkOut이 같은 '
                               '프레임을 복제해 타임스탬프가 고정되므로 지연값이 무의미함. '
                               '지연은 --mode camera 로 잴 것.')
        return out

    lat_ms = sorted(x * 1000.0 for x in latencies)
    out['latency_ms'] = {
        'mean': round(statistics.fmean(lat_ms), 2) if lat_ms else None,
        'p50': round(pct(lat_ms, 0.50), 2) if lat_ms else None,
        'p90': round(pct(lat_ms, 0.90), 2) if lat_ms else None,
        'p95': round(pct(lat_ms, 0.95), 2) if lat_ms else None,
        'p99': round(pct(lat_ms, 0.99), 2) if lat_ms else None,
        'min': round(lat_ms[0], 2) if lat_ms else None,
        'max': round(lat_ms[-1], 2) if lat_ms else None,
        'samples': len(lat_ms),
    }
    return out


def main():
    ap = argparse.ArgumentParser(description='OAK-D(RVC2) 엣지 추론 성능 계측')
    ap.add_argument('--model', required=True,
                    help='모델 주 슬러그(예: luxonis/yolov6-nano:r2-coco-512x288) 또는 '
                         '로컬 NNArchive(.tar.xz) 또는 raw .blob 경로')
    ap.add_argument('--ip', help='PoE 장치 IP (예: 169.254.1.222). 생략하면 자동 탐색')
    ap.add_argument('--label', required=True, help='이 실행의 이름 (결과 파일명/표에 쓰임)')
    ap.add_argument('--mode', choices=('throughput', 'camera'), default='throughput')
    ap.add_argument('--duration', type=float, default=30.0, help='측정 구간(초)')
    ap.add_argument('--warmup', type=float, default=5.0, help='버릴 워밍업 구간(초)')
    ap.add_argument('--camera-fps', type=float, default=30.0)
    ap.add_argument('--report-every', type=int, default=50, help='N개 메시지마다 리포트')
    ap.add_argument('--decode', action='store_true',
                    help='DetectionNetwork로 칩 위 디코딩까지 수행 (NNArchive 전용). '
                         '생략하면 NeuralNetwork로 원시 텐서만 받는다')
    ap.add_argument('--drain', type=float, default=3.0,
                    help='측정 후 파이프라인을 닫기 전 대기(초). 장치 크래시 방지')
    ap.add_argument('--queue-size', type=int, default=2,
                    help='NN 입력 큐 크기. 작게 잡아야 링크 포화/지연 누적을 막는다')
    ap.add_argument('--shaves', type=int, help='추론 스레드당 SHAVE 코어 수(고정하고 싶을 때)')
    ap.add_argument('--threads', type=int, help='추론 스레드 수(고정하고 싶을 때)')
    ap.add_argument('--note', default='', help='결과에 남길 자유 메모')
    args = ap.parse_args()

    desc = load_model(args.model)
    device = dai.Device(dai.DeviceInfo(args.ip)) if args.ip else dai.Device()
    # 장치 정보는 파이프라인 블록을 벗어나면 장치가 닫혀 접근할 수 없다. 먼저 뽑아둔다.
    device_info = {
        'id': device.getDeviceId(),
        'platform': str(device.getPlatform()),
        'connection': 'PoE/TCP_IP' if args.ip else 'auto',
        'ip': args.ip,
    }

    with dai.Pipeline(device) as pipeline:
        nn, report_q, (w, h) = build_pipeline(pipeline, desc, args)
        pipeline.start()
        print(f'[{args.label}] {args.mode} 모드 | 입력 {w}x{h} | '
              f'워밍업 {args.warmup}s + 측정 {args.duration}s')
        metrics = collect(report_q, args, measure_latency=args.mode == 'camera')
        # 포화 상태에서 곧바로 파이프라인을 닫으면 장치가 크래시한다(30초 throughput 실행에서
        # 재현). 잠시 쉬어 장치가 밀린 작업을 비우게 한 뒤 닫는다.
        time.sleep(args.drain)

    result = {
        'label': args.label,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'mode': args.mode,
        'note': args.note,
        'model': {
            'source': desc['source'],
            'kind': desc['kind'],
            'blob_shaves': desc['shaves'],
            'input_width': w,
            'input_height': h,
            'shaves_per_thread': args.shaves,
            'inference_threads': args.threads,
            'queue_size': args.queue_size,
            'on_chip_decode': args.decode,
        },
        'device': device_info,
        'config': {
            'duration_s': args.duration,
            'warmup_s': args.warmup,
            'camera_fps': args.camera_fps,
            'report_every': args.report_every,
        },
        'metrics': metrics,
        'env': {
            'depthai': dai.__version__,
            'python': platform.python_version(),
            'host': socket.gethostname(),
            'os': platform.platform(),
        },
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out = RESULTS_DIR / f'{args.label}_{args.mode}_{stamp}.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    m = metrics
    if m['latency_ms']:
        print(f"  FPS {m['fps']}  |  지연 평균 {m['latency_ms']['mean']}ms "
              f"p95 {m['latency_ms']['p95']}ms  |  {m['messages']}개 메시지")
    else:
        print(f"  FPS {m['fps']}  |  지연: 미측정(throughput 모드)  |  "
              f"{m['messages']}개 메시지")
    print(f'  저장: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
