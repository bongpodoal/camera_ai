#!/usr/bin/env python3
"""학습용 PC 점검 (읽기만 한다, 아무것도 바꾸지 않는다). 결과 전체를 복사해서 알려 주면 학습 계획의 배치 크기·해상도를 정한다.

실행: python3 check_training_pc.py
"""
import os
import platform
import shutil
import subprocess
import sys


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:
        return f"(실행 실패: {e})"


print("== 운영체제 / 파이썬 ==")
print(platform.platform(), "| python", sys.version.split()[0])
print("\n== 그래픽카드 (nvidia-smi) ==")
print(run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv"]) or "nvidia-smi 없음 (NVIDIA 드라이버 미설치?)")
print("\n== torch / CUDA ==")
try:
    import torch
    print("torch", torch.__version__, "| CUDA 사용 가능:", torch.cuda.is_available(), "| CUDA 버전:", torch.version.cuda,
          "| GPU 수:", torch.cuda.device_count())
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f"  GPU{i}: {p.name}, VRAM {p.total_memory / 1e9:.1f} GB")
except ImportError:
    print("torch 미설치")
print("\n== 디스크 (현재 폴더) ==")
t = shutil.disk_usage(os.getcwd())
print(f"전체 {t.total / 1e9:.0f} GB, 사용 {t.used / 1e9:.0f} GB, 여유 {t.free / 1e9:.0f} GB")
print("\n== 메모리 ==")
try:
    import psutil
    m = psutil.virtual_memory()
    print(f"RAM 전체 {m.total / 1e9:.1f} GB, 사용 가능 {m.available / 1e9:.1f} GB | CPU 코어 {psutil.cpu_count(logical=False)} (논리 {psutil.cpu_count()})")
except ImportError:
    print(run(["free", "-h"]) or "psutil 없음 (pip install psutil 하면 표시)")
print("\n== 인터넷 / git ==")
print("git:", run(["git", "--version"]) or "없음")
for host in ("https://github.com", "https://huggingface.co", "https://bdd-data.berkeley.edu"):
    try:
        import ssl
        import urllib.request
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
        urllib.request.urlopen(host, timeout=8, context=ctx)
        print("접속 가능:", host)
    except Exception as e:
        print("접속 실패:", host, str(e)[:60])
