"""Bộ kiểm tra lỗi dự án Scratch trước khi xuất .sb3."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.project_model import (
    ProjectModel, STAGE_X_MIN, STAGE_X_MAX, STAGE_Y_MIN, STAGE_Y_MAX,
)

Severity = Literal["error", "warning", "info"]


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    target: str = ""  # tên sprite / stage / list / broadcast liên quan


class Linter:
    def __init__(self, model: ProjectModel, workdir: Path):
        self.model = model
        self.workdir = workdir

    def run(self) -> list[Issue]:
        issues: list[Issue] = []
        issues.extend(self._check_missing_assets())
        issues.extend(self._check_duplicate_names())
        issues.extend(self._check_off_stage_sprites())
        issues.extend(self._check_broadcasts())
        issues.extend(self._check_list_alignment())
        issues.extend(self._check_orphan_files())
        return issues

    # ---------- asset thiếu ----------
    def _check_missing_assets(self) -> list[Issue]:
        out: list[Issue] = []
        for t in self.model.targets:
            tname = t.get("name", "?")
            for c in t.get("costumes", []):
                md5ext = c.get("md5ext")
                if not md5ext:
                    out.append(Issue("error", "ASSET_NO_MD5",
                                     f"Costume '{c.get('name')}' không có md5ext",
                                     tname))
                    continue
                if not (self.workdir / md5ext).exists():
                    out.append(Issue("error", "ASSET_MISSING",
                                     f"Thiếu file asset {md5ext} cho costume '{c.get('name')}'",
                                     tname))
            for s in t.get("sounds", []):
                md5ext = s.get("md5ext")
                if md5ext and not (self.workdir / md5ext).exists():
                    out.append(Issue("warning", "SOUND_MISSING",
                                     f"Thiếu âm thanh {md5ext} ('{s.get('name')}')",
                                     tname))
        return out

    # ---------- trùng tên ----------
    def _check_duplicate_names(self) -> list[Issue]:
        out: list[Issue] = []
        sprite_names: dict[str, int] = {}
        for t in self.model.sprites():
            name = t.get("name", "")
            sprite_names[name] = sprite_names.get(name, 0) + 1
        for n, k in sprite_names.items():
            if k > 1:
                out.append(Issue("error", "DUP_SPRITE",
                                 f"Có {k} sprite cùng tên '{n}'"))

        stage = self.model.stage()
        if stage:
            bd_names: dict[str, int] = {}
            for c in stage.get("costumes", []):
                bd_names[c.get("name", "")] = bd_names.get(c.get("name", ""), 0) + 1
            for n, k in bd_names.items():
                if k > 1:
                    out.append(Issue("warning", "DUP_BACKDROP",
                                     f"Backdrop trùng tên '{n}' ({k} lần)",
                                     "Stage"))
        # variable/list trùng tên trong cùng target
        for t in self.model.targets:
            seen: dict[str, str] = {}
            for vid, payload in (t.get("variables") or {}).items():
                nm = payload[0]
                if nm in seen:
                    out.append(Issue("warning", "DUP_VAR",
                                     f"Biến '{nm}' xuất hiện nhiều lần", t.get("name", "")))
                seen[nm] = "var"
            for lid, payload in (t.get("lists") or {}).items():
                nm = payload[0]
                if nm in seen:
                    out.append(Issue("warning", "DUP_LIST_VAR",
                                     f"List '{nm}' trùng tên với biến/list khác",
                                     t.get("name", "")))
        return out

    # ---------- sprite ngoài sân khấu ----------
    def _check_off_stage_sprites(self) -> list[Issue]:
        out: list[Issue] = []
        for t in self.model.sprites():
            x = float(t.get("x", 0))
            y = float(t.get("y", 0))
            if not (STAGE_X_MIN <= x <= STAGE_X_MAX and STAGE_Y_MIN <= y <= STAGE_Y_MAX):
                out.append(Issue("warning", "SPRITE_OFFSTAGE",
                                 f"Sprite '{t.get('name')}' nằm ngoài sân khấu (x={x}, y={y})",
                                 t.get("name", "")))
            if not t.get("visible", True):
                out.append(Issue("info", "SPRITE_HIDDEN",
                                 f"Sprite '{t.get('name')}' đang ẩn", t.get("name", "")))
        return out

    # ---------- broadcast ----------
    def _check_broadcasts(self) -> list[Issue]:
        out: list[Issue] = []
        stage = self.model.stage()
        if not stage:
            out.append(Issue("error", "NO_STAGE", "Không tìm thấy Stage trong dự án"))
            return out

        defined_ids = set((stage.get("broadcasts") or {}).keys())
        defined_names = set((stage.get("broadcasts") or {}).values())

        # tìm broadcast được dùng trong block
        used_ids: set[str] = set()
        used_names: set[str] = set()
        for t in self.model.targets:
            for block in (t.get("blocks") or {}).values():
                if not isinstance(block, dict):
                    continue
                fields = block.get("fields") or {}
                for fname, fval in fields.items():
                    if fname == "BROADCAST_OPTION" and isinstance(fval, list) and len(fval) >= 2:
                        used_names.add(fval[0])
                        if fval[1]:
                            used_ids.add(fval[1])

        for bid in used_ids - defined_ids:
            out.append(Issue("error", "BROADCAST_MISSING_ID",
                             f"Block tham chiếu broadcast id '{bid}' không tồn tại"))
        for bname in used_names - defined_names:
            out.append(Issue("warning", "BROADCAST_NAME_MISMATCH",
                             f"Broadcast '{bname}' không có trong Stage.broadcasts"))
        for bid in defined_ids - used_ids:
            bname = (stage.get("broadcasts") or {}).get(bid, "")
            out.append(Issue("info", "BROADCAST_UNUSED",
                             f"Broadcast '{bname}' khai báo nhưng không dùng"))
        return out

    # ---------- list bị lệch dòng ----------
    def _check_list_alignment(self) -> list[Issue]:
        out: list[Issue] = []
        # Quy ước cho ngân hàng câu hỏi: nếu nhiều list cùng prefix (vd: cau_hoi, dap_an_a, ...)
        # số phần tử nên bằng nhau.
        groups: dict[str, list] = {}
        for le in self.model.iter_lists():
            base = le.name.lower()
            for sep in ("_", "-", " "):
                if sep in base:
                    base = base.rsplit(sep, 1)[0]
                    break
            groups.setdefault(base, []).append(le)

        for base, lst_group in groups.items():
            if len(lst_group) < 2:
                continue
            sizes = {le.name: len(le.items) for le in lst_group}
            uniq = set(sizes.values())
            if len(uniq) > 1:
                detail = ", ".join(f"{n}={s}" for n, s in sizes.items())
                out.append(Issue("warning", "LIST_MISALIGNED",
                                 f"Nhóm list '{base}*' lệch số dòng: {detail}"))
        return out

    # ---------- file thừa ----------
    def _check_orphan_files(self) -> list[Issue]:
        out: list[Issue] = []
        referenced: set[str] = set()
        for t in self.model.targets:
            for c in t.get("costumes", []):
                if c.get("md5ext"):
                    referenced.add(c["md5ext"])
            for s in t.get("sounds", []):
                if s.get("md5ext"):
                    referenced.add(s["md5ext"])
        for p in self.workdir.iterdir():
            if p.is_file() and p.name != "project.json" and p.name not in referenced:
                out.append(Issue("info", "ORPHAN_ASSET",
                                 f"File '{p.name}' không được dùng (sẽ tự bỏ khi export)"))
        return out


def format_issues(issues: list[Issue]) -> str:
    if not issues:
        return "✅ Không phát hiện vấn đề."
    lines = []
    icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
    for it in issues:
        prefix = icons.get(it.severity, "•")
        tgt = f" [{it.target}]" if it.target else ""
        lines.append(f"{prefix} [{it.code}]{tgt} {it.message}")
    return "\n".join(lines)
