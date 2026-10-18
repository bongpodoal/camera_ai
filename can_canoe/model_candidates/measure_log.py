"""측정 로그 공통 도우미: 모든 시험이 시작 시각·링크 속도·장비·블롭 정보를 한 줄 CSV(영구 파일)로 남긴다."""
import csv
import datetime
import hashlib
import subprocess
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "runs"          # can_canoe/runs (git 제외)


def link_mbps(nic="enp6s0"):
    try:
        return int(Path(f"/sys/class/net/{nic}/speed").read_text())
    except (OSError, ValueError):
        return ""


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def git_state():
    try:
        root = Path(__file__).resolve().parents[2]
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True).stdout.strip())
        return rev + ("+local" if dirty else "")
    except Exception:
        return ""


def sha256_short(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


def append_row(csv_path, row):
    """row = dict. 새 열이 생기면 같은 이름의 새 파일(_v2)로 넘어가지 않고, 헤더가 다르면 기존 파일을 .old 로 두고 새로 시작한다."""
    p = Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with open(p, newline="") as fh:
            head = next(csv.reader(fh), [])
        if head != list(row):
            p.rename(p.with_suffix(f".{datetime.datetime.now():%Y%m%d%H%M%S}.old.csv"))
    new = not p.exists()
    with open(p, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
