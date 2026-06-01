"""Đọc & ghi file .sb3 (zip chứa project.json + asset)."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from utils.paths import new_temp_dir, backup_file, OUTPUT_DIR, ensure_workspace


class Sb3LoadError(Exception):
    pass


class Sb3Bundle:
    """Đại diện một dự án .sb3 đã được giải nén ra thư mục tạm.

    KHÔNG bao giờ sửa file gốc – mọi thay đổi nằm trong `workdir`.
    """

    def __init__(self, source_path: Path, workdir: Path, project: dict):
        self.source_path = source_path
        self.workdir = workdir
        self.project = project  # dict đã parse từ project.json

    # ---------- load ----------
    @classmethod
    def open(cls, sb3_path: Path) -> "Sb3Bundle":
        sb3_path = Path(sb3_path)
        if not sb3_path.exists():
            raise Sb3LoadError(f"Không tìm thấy file: {sb3_path}")
        if sb3_path.suffix.lower() != ".sb3":
            raise Sb3LoadError("File không có đuôi .sb3")

        workdir = new_temp_dir(prefix="open_")
        try:
            with zipfile.ZipFile(sb3_path, "r") as zf:
                zf.extractall(workdir)
        except zipfile.BadZipFile as e:
            raise Sb3LoadError(f"File .sb3 hỏng hoặc không phải zip: {e}") from e

        proj_file = workdir / "project.json"
        if not proj_file.exists():
            raise Sb3LoadError("Thiếu project.json trong .sb3")
        try:
            project = json.loads(proj_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise Sb3LoadError(f"project.json lỗi cú pháp: {e}") from e

        return cls(sb3_path, workdir, project)

    # ---------- asset helpers ----------
    def asset_path(self, md5ext: str) -> Path:
        return self.workdir / md5ext

    def list_assets(self) -> list[Path]:
        return [
            p for p in self.workdir.iterdir()
            if p.is_file() and p.name != "project.json"
        ]

    def write_asset(self, md5ext: str, data: bytes) -> Path:
        p = self.workdir / md5ext
        p.write_bytes(data)
        return p

    # ---------- save ----------
    def save_project_json(self) -> None:
        proj_file = self.workdir / "project.json"
        proj_file.write_text(
            json.dumps(self.project, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    def export_sb3(self, out_name: Optional[str] = None,
                   make_backup: bool = True) -> Path:
        """Đóng gói thành .sb3 mới trong workspace/output/."""
        ensure_workspace()
        self.save_project_json()
        if out_name is None:
            out_name = self.source_path.stem + "_edited.sb3"
        if not out_name.lower().endswith(".sb3"):
            out_name += ".sb3"
        out_path = OUTPUT_DIR / out_name

        if make_backup and out_path.exists():
            backup_file(out_path)

        # Tập hợp file cần đóng gói: project.json + asset thực sự được tham chiếu
        referenced = self._collect_referenced_assets()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(self.workdir / "project.json", "project.json")
            for name in sorted(referenced):
                fp = self.workdir / name
                if fp.exists():
                    zf.write(fp, name)
        return out_path

    def _collect_referenced_assets(self) -> set[str]:
        refs: set[str] = set()
        for tgt in self.project.get("targets", []):
            for c in tgt.get("costumes", []):
                if c.get("md5ext"):
                    refs.add(c["md5ext"])
            for s in tgt.get("sounds", []):
                if s.get("md5ext"):
                    refs.add(s["md5ext"])
        return refs

    def cleanup(self) -> None:
        if self.workdir.exists():
            shutil.rmtree(self.workdir, ignore_errors=True)
