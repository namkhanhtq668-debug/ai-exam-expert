"""Lớp truy cập có ý nghĩa lên cấu trúc project.json của Scratch 3.

Chỉ thao tác trên `dict` trong bộ nhớ – không tự đọc/ghi file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# Sân khấu Scratch
STAGE_W = 480
STAGE_H = 360
STAGE_X_MIN, STAGE_X_MAX = -240, 240
STAGE_Y_MIN, STAGE_Y_MAX = -180, 180


@dataclass
class VarEntry:
    target_name: str
    var_id: str
    name: str
    value: Any
    is_cloud: bool = False


@dataclass
class ListEntry:
    target_name: str
    list_id: str
    name: str
    items: list


@dataclass
class BroadcastEntry:
    broadcast_id: str
    name: str


@dataclass
class CostumeRef:
    target_name: str
    index: int
    name: str
    md5ext: str
    asset_id: str
    rotation_center_x: float
    rotation_center_y: float
    bitmap_resolution: int


class ProjectModel:
    """Bao bọc dict project.json với các method trợ giúp."""

    def __init__(self, project: dict):
        self.project = project

    # ---------- targets ----------
    @property
    def targets(self) -> list[dict]:
        return self.project.setdefault("targets", [])

    def stage(self) -> dict | None:
        for t in self.targets:
            if t.get("isStage"):
                return t
        return None

    def sprites(self) -> list[dict]:
        return [t for t in self.targets if not t.get("isStage")]

    def target_by_name(self, name: str) -> dict | None:
        for t in self.targets:
            if t.get("name") == name:
                return t
        return None

    # ---------- variables / lists / broadcasts ----------
    def iter_variables(self) -> Iterable[VarEntry]:
        for t in self.targets:
            name = t.get("name", "?")
            for vid, payload in (t.get("variables") or {}).items():
                if isinstance(payload, list) and len(payload) >= 2:
                    yield VarEntry(
                        target_name=name,
                        var_id=vid,
                        name=payload[0],
                        value=payload[1],
                        is_cloud=len(payload) > 2 and bool(payload[2]),
                    )

    def iter_lists(self) -> Iterable[ListEntry]:
        for t in self.targets:
            name = t.get("name", "?")
            for lid, payload in (t.get("lists") or {}).items():
                if isinstance(payload, list) and len(payload) >= 2:
                    items = payload[1] if isinstance(payload[1], list) else []
                    yield ListEntry(
                        target_name=name,
                        list_id=lid,
                        name=payload[0],
                        items=list(items),
                    )

    def iter_broadcasts(self) -> Iterable[BroadcastEntry]:
        stage = self.stage()
        if not stage:
            return
        for bid, bname in (stage.get("broadcasts") or {}).items():
            yield BroadcastEntry(broadcast_id=bid, name=bname)

    def update_list_items(self, target_name: str, list_id: str,
                          new_items: list) -> bool:
        t = self.target_by_name(target_name)
        if not t:
            return False
        lst = (t.get("lists") or {}).get(list_id)
        if not lst:
            return False
        lst[1] = list(new_items)
        return True

    def update_variable_value(self, target_name: str, var_id: str,
                              new_value: Any) -> bool:
        t = self.target_by_name(target_name)
        if not t:
            return False
        v = (t.get("variables") or {}).get(var_id)
        if not v:
            return False
        v[1] = new_value
        return True

    def set_variable_visible(self, target_name: str, var_id: str,
                             visible: bool) -> int:
        """Bật/tắt monitor hiển thị biến trên sân khấu.

        Trả về số monitor đã thay đổi.
        """
        changed = 0
        for m in self.project.setdefault("monitors", []):
            if m.get("id") == var_id:
                m["visible"] = bool(visible)
                changed += 1
        return changed

    def hide_all_variable_monitors(self) -> int:
        n = 0
        for m in self.project.setdefault("monitors", []):
            if m.get("mode") in ("default", "large", "slider"):
                if m.get("visible"):
                    m["visible"] = False
                    n += 1
        return n

    # ---------- costumes ----------
    def iter_costumes(self) -> Iterable[CostumeRef]:
        for t in self.targets:
            name = t.get("name", "?")
            for i, c in enumerate(t.get("costumes", [])):
                yield CostumeRef(
                    target_name=name,
                    index=i,
                    name=c.get("name", ""),
                    md5ext=c.get("md5ext", ""),
                    asset_id=c.get("assetId", ""),
                    rotation_center_x=float(c.get("rotationCenterX", 0)),
                    rotation_center_y=float(c.get("rotationCenterY", 0)),
                    bitmap_resolution=int(c.get("bitmapResolution", 1)),
                )

    def replace_costume_asset(self, target_name: str, costume_index: int,
                              new_md5ext: str, new_asset_id: str,
                              data_format: str,
                              rotation_center_x: float | None = None,
                              rotation_center_y: float | None = None,
                              bitmap_resolution: int | None = None) -> bool:
        t = self.target_by_name(target_name)
        if not t:
            return False
        costumes = t.get("costumes", [])
        if costume_index < 0 or costume_index >= len(costumes):
            return False
        c = costumes[costume_index]
        c["md5ext"] = new_md5ext
        c["assetId"] = new_asset_id
        c["dataFormat"] = data_format
        if rotation_center_x is not None:
            c["rotationCenterX"] = rotation_center_x
        if rotation_center_y is not None:
            c["rotationCenterY"] = rotation_center_y
        if bitmap_resolution is not None:
            c["bitmapResolution"] = bitmap_resolution
        return True

    # ---------- sprite transform ----------
    def set_sprite_xy(self, sprite_name: str, x: float, y: float) -> bool:
        t = self.target_by_name(sprite_name)
        if not t or t.get("isStage"):
            return False
        t["x"] = float(x)
        t["y"] = float(y)
        return True

    def set_sprite_size(self, sprite_name: str, size: float) -> bool:
        t = self.target_by_name(sprite_name)
        if not t or t.get("isStage"):
            return False
        t["size"] = float(size)
        return True

    def set_sprite_direction(self, sprite_name: str, direction: float) -> bool:
        t = self.target_by_name(sprite_name)
        if not t or t.get("isStage"):
            return False
        t["direction"] = float(direction)
        return True

    def set_sprite_visible(self, sprite_name: str, visible: bool) -> bool:
        t = self.target_by_name(sprite_name)
        if not t or t.get("isStage"):
            return False
        t["visible"] = bool(visible)
        return True
