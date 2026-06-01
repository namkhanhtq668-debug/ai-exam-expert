"""Chuẩn hoá / sửa lỗi dự án .sb3 để Scratch Desktop mở được.

Mọi hàm ở đây nhận và sửa trực tiếp `project` (dict) + thư mục workdir
(chứa các file asset). Trả về danh sách `RepairFix` để hiển thị cho người dùng.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from utils.hashing import md5_file, md5_bytes


# ---------- Helpers ----------

REQUIRED_META = {
    "semver": "3.0.0",
    "vm": "0.2.0",
    "agent": "ScratchEditor/1.0 (https://example.com)",
}

# Trường bắt buộc cho mọi target
DEFAULT_TARGET = {
    "isStage": False,
    "name": "",
    "variables": {},
    "lists": {},
    "broadcasts": {},
    "blocks": {},
    "comments": {},
    "currentCostume": 0,
    "costumes": [],
    "sounds": [],
    "volume": 100,
    "layerOrder": 1,
    "visible": True,
    "x": 0,
    "y": 0,
    "size": 100,
    "direction": 90,
    "draggable": False,
    "rotationStyle": "all around",
}

DEFAULT_STAGE_EXTRA = {
    "tempo": 60,
    "videoTransparency": 50,
    "videoState": "on",
    "textToSpeechLanguage": None,
}

# Costume bắt buộc
DEFAULT_COSTUME = {
    "name": "costume",
    "bitmapResolution": 1,
    "rotationCenterX": 0,
    "rotationCenterY": 0,
    "dataFormat": "png",
}

DEFAULT_SOUND = {
    "name": "sound",
    "rate": 48000,
    "sampleCount": 0,
    "format": "",
    "dataFormat": "wav",
}


@dataclass
class RepairFix:
    code: str
    message: str
    target: str = ""


@dataclass
class RepairReport:
    fixes: list[RepairFix] = field(default_factory=list)
    fatal_errors: list[str] = field(default_factory=list)

    def add(self, code: str, msg: str, target: str = ""):
        self.fixes.append(RepairFix(code, msg, target))

    @property
    def ok(self) -> bool:
        return not self.fatal_errors


# 1x1 PNG trong suốt (dùng làm placeholder khi thiếu costume)
_TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def _make_placeholder_costume(workdir: Path, label: str) -> tuple[str, str, int, int]:
    """Sinh 1 file PNG 64x64 với chữ 'MISSING' để thay costume mất.

    Trả về (md5ext, asset_id, w, h).
    """
    img = Image.new("RGBA", (64, 64), (255, 240, 200, 255))
    try:
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 63, 63], outline=(200, 60, 60, 255), width=2)
        d.text((6, 20), "MISSING", fill=(150, 0, 0, 255))
        d.text((6, 36), label[:10], fill=(80, 0, 0, 255))
    except Exception:
        pass
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    asset_id = md5_bytes(data)
    md5ext = f"{asset_id}.png"
    (workdir / md5ext).write_bytes(data)
    return md5ext, asset_id, 64, 64


# ---------- Public entry points ----------

def repair_project_dict(project: dict, workdir: Path) -> RepairReport:
    """Sửa trực tiếp dict project + workdir. Trả về báo cáo."""
    rpt = RepairReport()

    _fix_meta(project, rpt)
    _fix_extensions(project, rpt)
    _fix_monitors_basic(project, rpt)
    _fix_targets(project, workdir, rpt)
    _fix_broadcasts_location(project, rpt)
    _fix_block_references(project, rpt)
    _fix_monitors_against_vars(project, rpt)
    _normalize_asset_filenames(project, workdir, rpt)
    _recompute_asset_md5(project, workdir, rpt)
    _remove_orphan_assets(project, workdir, rpt)

    return rpt


def repair_sb3_from_disk(src: Path, out_dir: Path) -> tuple[Path, RepairReport]:
    """Mở 1 file .sb3 (kể cả lỗi nhẹ), sửa, xuất ra file mới.

    Dùng khi file gốc thậm chí không mở được bằng editor – muốn 'fix-and-go'.
    """
    src = Path(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = out_dir / f"_repair_{src.stem}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    rpt = RepairReport()
    try:
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(workdir)
    except zipfile.BadZipFile as e:
        rpt.fatal_errors.append(f"File không phải zip hợp lệ: {e}")
        return src, rpt

    proj_file = workdir / "project.json"
    if not proj_file.exists():
        # tìm bằng case-insensitive
        for p in workdir.iterdir():
            if p.name.lower() == "project.json":
                p.rename(proj_file)
                rpt.add("PROJECT_JSON_CASE",
                        f"Đổi tên '{p.name}' → 'project.json'")
                break
    if not proj_file.exists():
        rpt.fatal_errors.append("Không tìm thấy project.json trong .sb3")
        return src, rpt

    try:
        project = json.loads(proj_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # thử strip BOM / chuẩn hoá
        raw = proj_file.read_text(encoding="utf-8-sig", errors="replace")
        try:
            project = json.loads(raw)
            rpt.add("PROJECT_JSON_BOM", "project.json có BOM hoặc ký tự lạ – đã xử lý.")
        except json.JSONDecodeError:
            rpt.fatal_errors.append(f"project.json hỏng cú pháp: {e}")
            return src, rpt

    rpt2 = repair_project_dict(project, workdir)
    rpt.fixes.extend(rpt2.fixes)

    proj_file.write_text(json.dumps(project, ensure_ascii=False,
                                    separators=(",", ":")),
                         encoding="utf-8")

    out_path = out_dir / (src.stem + "_repaired.sb3")
    referenced = _collect_referenced(project)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(proj_file, "project.json")
        for name in sorted(referenced):
            fp = workdir / name
            if fp.exists():
                zf.write(fp, name)
    return out_path, rpt


# ---------- Internals ----------

def _fix_meta(project: dict, rpt: RepairReport):
    meta = project.setdefault("meta", {})
    for k, v in REQUIRED_META.items():
        if not meta.get(k):
            meta[k] = v
            rpt.add("META_FIELD", f"Thêm meta.{k}={v}")
    sv = str(meta.get("semver", ""))
    if not sv.startswith("3."):
        meta["semver"] = "3.0.0"
        rpt.add("META_SEMVER", "Đặt lại meta.semver='3.0.0' (Scratch 3)")


def _fix_extensions(project: dict, rpt: RepairReport):
    ext = project.get("extensions")
    if not isinstance(ext, list):
        project["extensions"] = []
        rpt.add("EXT_INIT", "Khởi tạo extensions=[]")


def _fix_monitors_basic(project: dict, rpt: RepairReport):
    m = project.get("monitors")
    if not isinstance(m, list):
        project["monitors"] = []
        rpt.add("MONITORS_INIT", "Khởi tạo monitors=[]")


def _fix_targets(project: dict, workdir: Path, rpt: RepairReport):
    targets = project.get("targets")
    if not isinstance(targets, list) or not targets:
        # tạo Stage trống
        project["targets"] = [{**DEFAULT_TARGET, **DEFAULT_STAGE_EXTRA,
                               "isStage": True, "name": "Stage",
                               "layerOrder": 0}]
        targets = project["targets"]
        rpt.add("TARGETS_EMPTY", "Dự án không có target – tạo Stage trống.")

    has_stage = any(t.get("isStage") for t in targets)
    if not has_stage:
        targets.insert(0, {**DEFAULT_TARGET, **DEFAULT_STAGE_EXTRA,
                           "isStage": True, "name": "Stage",
                           "layerOrder": 0})
        rpt.add("STAGE_MISSING", "Thiếu Stage – đã thêm Stage mặc định.")

    seen_names: dict[str, int] = {}
    for t in targets:
        tname = t.get("name") or ("Stage" if t.get("isStage") else "Sprite")
        # ép kiểu / điền mặc định
        for k, v in DEFAULT_TARGET.items():
            if k not in t:
                t[k] = v if not isinstance(v, (dict, list)) else type(v)()
                rpt.add("TARGET_FIELD", f"Thêm {k} mặc định", tname)
        if t.get("isStage"):
            for k, v in DEFAULT_STAGE_EXTRA.items():
                if k not in t:
                    t[k] = v
                    rpt.add("STAGE_FIELD", f"Thêm {k} mặc định", tname)
            t["name"] = "Stage"
            t["layerOrder"] = 0
            t["x"] = 0; t["y"] = 0
            t["visible"] = True

        # đổi trùng tên sprite
        base = t.get("name", "Sprite")
        seen_names[base] = seen_names.get(base, 0) + 1
        if seen_names[base] > 1 and not t.get("isStage"):
            new_name = f"{base}_{seen_names[base]}"
            t["name"] = new_name
            rpt.add("DUP_SPRITE_FIX", f"Đổi tên sprite trùng: {base} → {new_name}")

        # costume
        costumes = t.get("costumes") or []
        if not isinstance(costumes, list):
            costumes = []
        if not costumes:
            md5ext, aid, w, h = _make_placeholder_costume(
                workdir, "Stage" if t.get("isStage") else tname)
            costumes.append({
                **DEFAULT_COSTUME,
                "name": "backdrop1" if t.get("isStage") else "costume1",
                "assetId": aid, "md5ext": md5ext,
                "rotationCenterX": w / 2, "rotationCenterY": h / 2,
                "dataFormat": "png",
                "bitmapResolution": 1,
            })
            rpt.add("COSTUME_PLACEHOLDER",
                    "Target không có costume – thêm placeholder.", tname)
        for c in costumes:
            for k, v in DEFAULT_COSTUME.items():
                if k not in c:
                    c[k] = v
            # md5ext bắt buộc
            md5ext = c.get("md5ext", "")
            aid = c.get("assetId", "")
            if not md5ext and aid and c.get("dataFormat"):
                md5ext = f"{aid}.{c['dataFormat']}"
                c["md5ext"] = md5ext
                rpt.add("COSTUME_MD5EXT",
                        f"Costume '{c.get('name')}' suy ra md5ext={md5ext}", tname)
            if md5ext and not (workdir / md5ext).exists():
                # thay placeholder thay vì để mất
                m2, aid2, w, h = _make_placeholder_costume(workdir, c.get("name", "?"))
                c["md5ext"] = m2; c["assetId"] = aid2; c["dataFormat"] = "png"
                c["bitmapResolution"] = 1
                c["rotationCenterX"] = w / 2
                c["rotationCenterY"] = h / 2
                rpt.add("COSTUME_MISSING_REPLACED",
                        f"Asset {md5ext} thiếu – thay placeholder", tname)
        t["costumes"] = costumes
        cc = int(t.get("currentCostume", 0) or 0)
        if cc < 0 or cc >= len(costumes):
            t["currentCostume"] = 0
            rpt.add("CC_OOR",
                    f"currentCostume vượt biên – đặt về 0", tname)

        # sound: chỉ thêm field thiếu, không sinh placeholder
        sounds = t.get("sounds") or []
        if not isinstance(sounds, list):
            sounds = []
        valid_sounds = []
        for s in sounds:
            md5ext = s.get("md5ext")
            if md5ext and not (workdir / md5ext).exists():
                rpt.add("SOUND_MISSING_REMOVED",
                        f"Bỏ sound '{s.get('name')}' do thiếu file {md5ext}", tname)
                continue
            for k, v in DEFAULT_SOUND.items():
                if k not in s:
                    s[k] = v
            valid_sounds.append(s)
        t["sounds"] = valid_sounds


def _fix_broadcasts_location(project: dict, rpt: RepairReport):
    stage = next((t for t in project["targets"] if t.get("isStage")), None)
    if not stage:
        return
    stage_bcasts = stage.setdefault("broadcasts", {})
    for t in project["targets"]:
        if t.get("isStage"):
            continue
        bc = t.get("broadcasts")
        if isinstance(bc, dict) and bc:
            for k, v in bc.items():
                if k not in stage_bcasts:
                    stage_bcasts[k] = v
            t["broadcasts"] = {}
            rpt.add("BROADCAST_MOVE",
                    f"Dồn broadcasts từ '{t.get('name')}' về Stage", t.get("name", ""))


def _fix_block_references(project: dict, rpt: RepairReport):
    for t in project["targets"]:
        blocks = t.get("blocks") or {}
        if not isinstance(blocks, dict):
            t["blocks"] = {}
            continue
        all_ids = set(blocks.keys())
        for bid, b in blocks.items():
            if not isinstance(b, dict):
                continue
            parent = b.get("parent")
            if parent and parent not in all_ids:
                b["parent"] = None
                rpt.add("BLOCK_PARENT",
                        f"Block {bid[:6]}… có parent lạ – đã xoá", t.get("name", ""))
            nxt = b.get("next")
            if nxt and nxt not in all_ids:
                b["next"] = None
                rpt.add("BLOCK_NEXT",
                        f"Block {bid[:6]}… có next lạ – đã xoá", t.get("name", ""))


def _fix_monitors_against_vars(project: dict, rpt: RepairReport):
    var_ids: set[str] = set()
    for t in project["targets"]:
        var_ids.update((t.get("variables") or {}).keys())
        var_ids.update((t.get("lists") or {}).keys())
    monitors = project.get("monitors", [])
    kept = []
    for m in monitors:
        mid = m.get("id")
        if mid and mid not in var_ids and m.get("opcode", "").startswith(
                ("data_variable", "data_listcontents")):
            rpt.add("MONITOR_ORPHAN",
                    f"Bỏ monitor trỏ biến không tồn tại: id={mid}")
            continue
        kept.append(m)
    project["monitors"] = kept


_BAD_NAME = re.compile(r"[^a-zA-Z0-9._-]")


def _normalize_asset_filenames(project: dict, workdir: Path, rpt: RepairReport):
    """Tên file đặt theo md5ext của project.json (lowercase, ASCII). Đổi file
    trên đĩa cho khớp."""
    for t in project["targets"]:
        tname = t.get("name", "")
        for c in t.get("costumes", []) + t.get("sounds", []):
            md5ext = c.get("md5ext", "")
            if not md5ext:
                continue
            # tìm file với tên gần đúng
            target_lower = md5ext.lower()
            real_path = workdir / md5ext
            if real_path.exists():
                continue
            found = None
            for p in workdir.iterdir():
                if p.is_file() and p.name.lower() == target_lower:
                    found = p
                    break
            if found:
                found.rename(workdir / md5ext)
                rpt.add("ASSET_RENAME",
                        f"Đổi tên file asset '{found.name}' → '{md5ext}'", tname)


def _recompute_asset_md5(project: dict, workdir: Path, rpt: RepairReport):
    """Nếu MD5 thật khác với md5ext trong project.json → đổi tên file +
    cập nhật assetId/md5ext (Scratch chấp nhận miễn trùng nhau)."""
    seen: dict[str, str] = {}  # md5ext mới -> tên file mới
    for t in project["targets"]:
        tname = t.get("name", "")
        for c in t.get("costumes", []) + t.get("sounds", []):
            md5ext = c.get("md5ext", "")
            if not md5ext:
                continue
            p = workdir / md5ext
            if not p.exists():
                continue
            real_md5 = md5_file(p)
            existing_md5 = md5ext.split(".")[0].lower()
            if real_md5 == existing_md5:
                continue
            ext = md5ext.split(".")[-1]
            new_name = f"{real_md5}.{ext}"
            new_path = workdir / new_name
            if not new_path.exists():
                p.rename(new_path)
            c["md5ext"] = new_name
            c["assetId"] = real_md5
            rpt.add("ASSET_MD5_FIX",
                    f"MD5 lệch – đổi {md5ext} → {new_name}", tname)


def _collect_referenced(project: dict) -> set[str]:
    refs: set[str] = set()
    for t in project.get("targets", []):
        for c in t.get("costumes", []):
            if c.get("md5ext"):
                refs.add(c["md5ext"])
        for s in t.get("sounds", []):
            if s.get("md5ext"):
                refs.add(s["md5ext"])
    return refs


def _remove_orphan_assets(project: dict, workdir: Path, rpt: RepairReport):
    """Không xoá file trên đĩa (vì có thể sẽ cần) nhưng báo cáo."""
    refs = _collect_referenced(project)
    n = 0
    for p in workdir.iterdir():
        if p.is_file() and p.name != "project.json" and p.name not in refs:
            n += 1
    if n:
        rpt.add("ASSET_ORPHAN",
                f"{n} file asset không dùng – sẽ tự loại khi xuất .sb3.")


def format_report(rpt: RepairReport) -> str:
    if rpt.fatal_errors:
        return "❌ LỖI NGHIÊM TRỌNG:\n" + "\n".join(f"  • {e}" for e in rpt.fatal_errors)
    if not rpt.fixes:
        return "✅ Không phát hiện vấn đề – dự án đã chuẩn."
    by_code: dict[str, list[RepairFix]] = {}
    for f in rpt.fixes:
        by_code.setdefault(f.code, []).append(f)
    lines = [f"✅ Đã thực hiện {len(rpt.fixes)} sửa đổi:"]
    for code, items in by_code.items():
        lines.append(f"\n— {code} ({len(items)}):")
        for it in items[:20]:
            tgt = f" [{it.target}]" if it.target else ""
            lines.append(f"   • {it.message}{tgt}")
        if len(items) > 20:
            lines.append(f"   … và {len(items)-20} mục nữa")
    return "\n".join(lines)
