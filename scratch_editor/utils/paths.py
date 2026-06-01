"""Quản lý đường dẫn workspace: temp / output / backup."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"
TEMP_DIR = WORKSPACE / "temp"
OUTPUT_DIR = WORKSPACE / "output"
BACKUP_DIR = WORKSPACE / "backup"


def ensure_workspace() -> None:
    for p in (TEMP_DIR, OUTPUT_DIR, BACKUP_DIR):
        p.mkdir(parents=True, exist_ok=True)


def new_temp_dir(prefix: str = "sb3_") -> Path:
    ensure_workspace()
    name = f"{prefix}{int(time.time() * 1000)}"
    p = TEMP_DIR / name
    p.mkdir(parents=True, exist_ok=False)
    return p


def backup_file(src: Path) -> Path:
    ensure_workspace()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"{src.stem}__{stamp}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


def cleanup_temp(keep_latest: int = 5) -> None:
    if not TEMP_DIR.exists():
        return
    dirs = sorted(
        (p for p in TEMP_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in dirs[keep_latest:]:
        shutil.rmtree(old, ignore_errors=True)
