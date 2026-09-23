"""예제 모델의 NNArchive를 모델 주에서 받아 풀고, 안에 남은 흔적으로 ①~⑤단계를 거꾸로 읽는다.

예제(DetectionNetwork/detection_network.py)는 ①~⑤를 Luxonis가 미리 끝낸 파일을 받아 쓴다.
그 파일 하나에 각 단계의 흔적이 남아 있다:

    ⑤ NNArchive   .tar.xz 자체, config.json (입력·전처리·후처리)
    ④ blob        *.superblob (SHAVE 개수별 블롭 묶음) — 헤더를 해석
    ③ OpenVINO IR buildinfo.json 의 model_optimizer 명령 (IR은 파일로 들어 있지 않음)
    ② ONNX        buildinfo.json 에 적힌 입력 ONNX 경로·입출력 이름 (ONNX는 들어 있지 않음)
    ① .pt         config.json 의 모델 이름 (원본 가중치는 들어 있지 않음)

    python3 05_nnarchive/fetch_example.py                       # 두 예제 모두
    python3 05_nnarchive/fetch_example.py --model yolov6-nano   # 예제 기본값만

결과: 05_nnarchive/example/<모델>/ 에 압축을 풀고 report.md 를 쓴다.
"""
import argparse
import json
import shutil
import struct
import tarfile
from pathlib import Path

import depthai as dai

HERE = Path(__file__).resolve().parent
EXAMPLES = [
    "yolov6-nano",                              # 예제 코드의 기본값 (파일명은 512x288이지만 실제 512x384)
    "luxonis/yolov6-nano:r2-coco-512x288",      # 이름과 실제가 일치하는 512x288
]


def superblob_header(path):
    """앞 136바이트 = 빅엔디언 u64 17개: [기본 블롭 크기, SHAVE 1..16 패치 크기]."""
    raw = path.read_bytes()
    vals = struct.unpack_from(">17Q", raw, 0)
    base, patches = vals[0], vals[1:]
    return dict(file_bytes=len(raw), header_bytes=17 * 8, base_blob_bytes=base,
                patch_bytes={i + 1: p for i, p in enumerate(patches)},
                base_shaves=[i + 1 for i, p in enumerate(patches) if p == 0],
                consistent=17 * 8 + base + sum(patches) == len(raw))


def analyze(slug, out_root):
    archive = Path(dai.getModelFromZoo(dai.NNModelDescription(slug, platform="RVC2")))
    name = slug.replace("/", "_").replace(":", "_")
    out = out_root / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with tarfile.open(archive) as t:
        t.extractall(out, filter="data")
        members = [(m.name, m.size) for m in t.getmembers()]

    cfg = json.loads((out / "config.json").read_text())
    build = json.loads((out / "buildinfo.json").read_text()) if (out / "buildinfo.json").exists() else {}
    m = cfg["model"]
    inp = m["inputs"][0]
    head = m["heads"][0]
    hm = head["metadata"]
    nna = dai.NNArchive(str(archive))

    blob_file = out / m["metadata"]["path"]
    sb = superblob_header(blob_file) if blob_file.suffix == ".superblob" else None
    mo = build.get("cmd_info", {}).get("model_optimizer", [])
    ct = build.get("cmd_info", {}).get("compile_tool", [])

    def arg(cmd, key):
        return cmd[cmd.index(key) + 1] if key in cmd else ""

    onnx_in = arg(mo, "--input_model")
    lines = [
        f"# {slug}", "",
        f"원본 아카이브: `{archive}`", "",
        "## ⑤ NNArchive", "",
        "| 항목 | 값 |", "| --- | --- |",
        f"| 파일 구성 | {', '.join(f'`{n}` ({s:,} B)' for n, s in members)} |",
        f"| 모델 이름 (config) | `{m['metadata']['name']}` |",
        f"| 실제 입력 (getInputWidth/Height) | **{nna.getInputWidth()}×{nna.getInputHeight()}** |",
        f"| 입력 shape / layout | {inp['shape']} {inp['layout']} |",
        f"| 전처리 (config) | mean={inp['preprocessing']['mean']} scale={inp['preprocessing']['scale']} "
        f"reverse_channels={inp['preprocessing'].get('reverse_channels')} |",
        f"| 후처리 | parser=`{head['parser']}` subtype=`{hm.get('subtype')}` |",
        f"| 출력 텐서 | {', '.join(o['name'] for o in m['outputs'])} |",
        f"| 클래스 / 문턱 | {hm.get('n_classes')}개 · conf {hm.get('conf_threshold')} · IoU {hm.get('iou_threshold')} · 최대 {hm.get('max_det')} |",
        "", "## ④ blob", "",
    ]
    if sb:
        lines += ["| 항목 | 값 |", "| --- | --- |",
                  f"| 파일 크기 | {sb['file_bytes']:,} B |",
                  f"| 헤더 | {sb['header_bytes']} B (u64 × 17, 빅엔디언) |",
                  f"| 기본 블롭 | {sb['base_blob_bytes']:,} B · SHAVE {sb['base_shaves']}개로 컴파일 |",
                  f"| SHAVE별 패치 | " + ", ".join(f"{k}:{v:,}" for k, v in sb['patch_bytes'].items()) + " B |",
                  f"| 크기 합 일치 | {'예' if sb['consistent'] else '아니오'} |",
                  f"| 컴파일 도구 | `{build.get('compile_tool_version', '')}` · 장치 `{arg(ct, '-d')}` · 입력 정밀도 `{arg(ct, '-ip')}` |",
                  f"| CMX 슬라이스 | {build.get('number_of_cmx_slices', '')} |"]
    else:
        lines += [f"블롭 파일: `{blob_file.name}` (superblob 아님)"]
    lines += ["", "## ③ OpenVINO IR", "",
              f"IR 파일은 아카이브에 없다. 만든 명령만 남아 있다 (Model Optimizer `{build.get('model_optimizer_version', '')}`):", "",
              "```", " ".join(mo) if mo else "(buildinfo 없음)", "```", "",
              "## ② ONNX", "",
              "| 항목 | 값 |", "| --- | --- |",
              f"| 입력 ONNX (아카이브에 없음) | `{Path(onnx_in).name}` |",
              f"| 입력 | `{arg(mo, '--input')}` |",
              f"| 출력 | `{arg(mo, '--output')}` |",
              f"| 변환 도구 | modelconverter `{build.get('modelconverter_version', '')}` |",
              "", "## ① PyTorch .pt", "",
              f"원본 가중치는 아카이브에 없다. 이름만 남아 있다: `{m['metadata']['name']}`", ""]
    (out / "report.md").write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"→ {out / 'report.md'}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", action="append", help="모델 주 이름 (여러 번 가능). 기본: 두 예제")
    ap.add_argument("--out", default=str(HERE / "example"))
    args = ap.parse_args()
    for slug in args.model or EXAMPLES:
        analyze(slug, Path(args.out))


if __name__ == "__main__":
    main()
