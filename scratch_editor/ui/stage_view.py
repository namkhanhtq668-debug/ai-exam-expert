"""Canvas hiển thị Stage 480x360 với sprite ở đúng tọa độ Scratch."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from core.project_model import ProjectModel, STAGE_W, STAGE_H

SCALE = 1.25  # canvas to hơn cho dễ nhìn
CANVAS_W = int(STAGE_W * SCALE)
CANVAS_H = int(STAGE_H * SCALE)


def scratch_to_canvas(x: float, y: float) -> tuple[float, float]:
    cx = (x + STAGE_W / 2) * SCALE
    cy = (STAGE_H / 2 - y) * SCALE
    return cx, cy


def canvas_to_scratch(cx: float, cy: float) -> tuple[float, float]:
    x = cx / SCALE - STAGE_W / 2
    y = STAGE_H / 2 - cy / SCALE
    return x, y


class StageView(tk.Frame):
    def __init__(self, master, on_sprite_moved=None, **kw):
        super().__init__(master, **kw)
        self.on_sprite_moved = on_sprite_moved
        self.model: ProjectModel | None = None
        self.workdir: Path | None = None

        self.canvas = tk.Canvas(self, width=CANVAS_W, height=CANVAS_H,
                                bg="#ffffff", highlightthickness=1,
                                highlightbackground="#888")
        self.canvas.pack(padx=4, pady=4)

        self._photo_refs: dict[str, ImageTk.PhotoImage] = {}
        self._sprite_items: dict[str, int] = {}  # name -> canvas item id
        self._backdrop_item: int | None = None
        self._drag = {"name": None, "dx": 0, "dy": 0}

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # khung viền stage
        self.canvas.create_rectangle(1, 1, CANVAS_W - 1, CANVAS_H - 1,
                                     outline="#444")

    # ---------- public ----------
    def set_project(self, model: ProjectModel, workdir: Path):
        self.model = model
        self.workdir = workdir
        self.refresh()

    def refresh(self):
        self.canvas.delete("all")
        self._photo_refs.clear()
        self._sprite_items.clear()
        self.canvas.create_rectangle(1, 1, CANVAS_W - 1, CANVAS_H - 1,
                                     outline="#444")
        if not self.model or not self.workdir:
            return

        # backdrop hiện tại
        stage = self.model.stage()
        if stage:
            idx = int(stage.get("currentCostume", 0))
            costumes = stage.get("costumes", [])
            if 0 <= idx < len(costumes):
                self._draw_image(costumes[idx], 0, 0, is_backdrop=True)

        # sprites theo layerOrder
        sprites = sorted(self.model.sprites(),
                         key=lambda t: t.get("layerOrder", 0))
        for sp in sprites:
            if not sp.get("visible", True):
                continue
            idx = int(sp.get("currentCostume", 0))
            costumes = sp.get("costumes", [])
            if not (0 <= idx < len(costumes)):
                continue
            x = float(sp.get("x", 0))
            y = float(sp.get("y", 0))
            size = float(sp.get("size", 100))
            self._draw_image(costumes[idx], x, y, is_backdrop=False,
                             sprite_name=sp.get("name", ""), size_pct=size)

    # ---------- internal draw ----------
    def _draw_image(self, costume: dict, x: float, y: float, *,
                    is_backdrop: bool, sprite_name: str = "",
                    size_pct: float = 100.0):
        md5ext = costume.get("md5ext", "")
        if not md5ext or not self.workdir:
            return
        path = self.workdir / md5ext
        if not path.exists():
            return
        ext = path.suffix.lower()
        if ext == ".svg":
            # Tkinter không vẽ SVG – hiển thị placeholder
            cx, cy = scratch_to_canvas(x, y)
            if is_backdrop:
                self.canvas.create_text(CANVAS_W / 2, CANVAS_H / 2,
                                        text="(backdrop SVG)", fill="#888")
            else:
                item = self.canvas.create_rectangle(
                    cx - 20, cy - 20, cx + 20, cy + 20,
                    outline="#3366cc", width=2, fill="#cfe2ff")
                self.canvas.create_text(cx, cy, text=sprite_name,
                                        fill="#003366", font=("Arial", 9))
                self._sprite_items[sprite_name] = item
            return

        try:
            with Image.open(path) as im:
                im = im.convert("RGBA")
                br = max(1, int(costume.get("bitmapResolution", 1)))
                # kích thước hiển thị trên Scratch: pixel / bitmapResolution
                disp_w = im.width / br
                disp_h = im.height / br
                if is_backdrop:
                    target_w = int(CANVAS_W)
                    target_h = int(CANVAS_H)
                else:
                    factor = (size_pct / 100.0) * SCALE
                    target_w = max(1, int(disp_w * factor))
                    target_h = max(1, int(disp_h * factor))
                im = im.resize((target_w, target_h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(im)
        except Exception:
            return

        key = f"{sprite_name or 'stage'}_{md5ext}"
        self._photo_refs[key] = photo

        if is_backdrop:
            self._backdrop_item = self.canvas.create_image(
                CANVAS_W / 2, CANVAS_H / 2, image=photo)
        else:
            cx, cy = scratch_to_canvas(x, y)
            item = self.canvas.create_image(cx, cy, image=photo,
                                            tags=("sprite", sprite_name))
            self._sprite_items[sprite_name] = item

    # ---------- drag ----------
    def _hit_sprite(self, cx: float, cy: float) -> str | None:
        items = self.canvas.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            if "sprite" in tags:
                for t in tags:
                    if t != "sprite":
                        return t
        return None

    def _on_press(self, evt):
        name = self._hit_sprite(evt.x, evt.y)
        if not name or not self.model:
            self._drag["name"] = None
            return
        sp = self.model.target_by_name(name)
        if not sp:
            return
        sx = float(sp.get("x", 0))
        sy = float(sp.get("y", 0))
        scx, scy = scratch_to_canvas(sx, sy)
        self._drag = {"name": name, "dx": evt.x - scx, "dy": evt.y - scy}

    def _on_drag(self, evt):
        if not self._drag["name"] or not self.model:
            return
        new_cx = evt.x - self._drag["dx"]
        new_cy = evt.y - self._drag["dy"]
        item = self._sprite_items.get(self._drag["name"])
        if item is not None:
            self.canvas.coords(item, new_cx, new_cy)

    def _on_release(self, evt):
        if not self._drag["name"] or not self.model:
            return
        new_cx = evt.x - self._drag["dx"]
        new_cy = evt.y - self._drag["dy"]
        x, y = canvas_to_scratch(new_cx, new_cy)
        x = round(max(-1000, min(1000, x)), 1)
        y = round(max(-1000, min(1000, y)), 1)
        name = self._drag["name"]
        self.model.set_sprite_xy(name, x, y)
        self._drag["name"] = None
        if self.on_sprite_moved:
            self.on_sprite_moved(name, x, y)
