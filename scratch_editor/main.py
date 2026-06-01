"""Scratch Editor – công cụ chỉnh sửa dự án Scratch (.sb3) cho giáo viên.

Chạy: python main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.app import ScratchEditorApp  # noqa: E402


def main() -> int:
    app = ScratchEditorApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
