"""Tính MD5 cho asset Scratch (.sb3 dùng MD5 làm tên file)."""
from __future__ import annotations

import hashlib
from pathlib import Path


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
