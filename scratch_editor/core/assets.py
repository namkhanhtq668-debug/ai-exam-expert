"""Xử lý ảnh nền / costume sprite chất lượng cao bằng Pillow.

- Hỗ trợ PNG / JPG / BMP / GIF / WEBP (raster) và SVG (giữ nguyên).
- Khi nhập ảnh nền: scale về 480x360 (giữ tỉ lệ, có thể chọn fit/cover).
- Khi nhập costume sprite: scale theo max_dim, tâm xoay đặt giữa ảnh.
- Tính MD5 đúng cách để Scratch nhận diện asset.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

from utils.hashing import md5_bytes

STAGE_W = 480
STAGE_H = 360

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"}
SVG_EXTS = {".svg"}


@dataclass
class PreparedAsset:
    md5ext: str        # ví dụ "abcd1234.png" – tên file đặt vào sb3
    asset_id: str      # MD5 không có đuôi
    data: bytes        # nội dung file
    data_format: str   # "png" / "svg" / "jpg" ...
    width: int
    height: int
    rotation_center_x: float
    rotation_center_y: float
    bitmap_resolution: int


def _pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def prepare_backdrop(src: Path,
                     mode: Literal["fit", "cover", "stretch"] = "fit") -> PreparedAsset:
    """Chuẩn bị ảnh nền 480x360. Mặc định fit (giữ tỉ lệ, viền trong suốt)."""
    ext = src.suffix.lower()
    if ext in SVG_EXTS:
        data = src.read_bytes()
        asset_id = md5_bytes(data)
        return PreparedAsset(
            md5ext=f"{asset_id}.svg",
            asset_id=asset_id,
            data=data,
            data_format="svg",
            width=STAGE_W, height=STAGE_H,
            rotation_center_x=STAGE_W / 2,
            rotation_center_y=STAGE_H / 2,
            bitmap_resolution=1,
        )
    if ext not in RASTER_EXTS:
        raise ValueError(f"Định dạng ảnh chưa hỗ trợ: {ext}")

    with Image.open(src) as im:
        im = im.convert("RGBA")
        canvas = Image.new("RGBA", (STAGE_W * 2, STAGE_H * 2), (0, 0, 0, 0))
        target_w, target_h = STAGE_W * 2, STAGE_H * 2  # bitmapResolution=2 cho nét

        if mode == "stretch":
            scaled = im.resize((target_w, target_h), Image.LANCZOS)
            canvas.paste(scaled, (0, 0))
        else:
            iw, ih = im.size
            if mode == "fit":
                scale = min(target_w / iw, target_h / ih)
            else:  # cover
                scale = max(target_w / iw, target_h / ih)
            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))
            scaled = im.resize((new_w, new_h), Image.LANCZOS)
            ox = (target_w - new_w) // 2
            oy = (target_h - new_h) // 2
            if mode == "cover":
                # cắt phần thừa
                crop_box = (max(0, -ox), max(0, -oy),
                            max(0, -ox) + target_w, max(0, -oy) + target_h)
                scaled = scaled.crop(crop_box)
                canvas.paste(scaled, (0, 0))
            else:
                canvas.paste(scaled, (ox, oy), scaled)

        data = _pil_to_png_bytes(canvas)
        asset_id = md5_bytes(data)
        return PreparedAsset(
            md5ext=f"{asset_id}.png",
            asset_id=asset_id,
            data=data,
            data_format="png",
            width=target_w, height=target_h,
            rotation_center_x=target_w / 2,
            rotation_center_y=target_h / 2,
            bitmap_resolution=2,
        )


def prepare_sprite_costume(src: Path, max_dim: int = 480) -> PreparedAsset:
    """Chuẩn bị costume cho sprite. Scale xuống nếu vượt max_dim, tâm xoay = giữa."""
    ext = src.suffix.lower()
    if ext in SVG_EXTS:
        data = src.read_bytes()
        asset_id = md5_bytes(data)
        return PreparedAsset(
            md5ext=f"{asset_id}.svg",
            asset_id=asset_id,
            data=data,
            data_format="svg",
            width=0, height=0,
            rotation_center_x=0, rotation_center_y=0,
            bitmap_resolution=1,
        )
    if ext not in RASTER_EXTS:
        raise ValueError(f"Định dạng ảnh chưa hỗ trợ: {ext}")

    with Image.open(src) as im:
        im = im.convert("RGBA")
        iw, ih = im.size
        scale = min(1.0, max_dim / max(iw, ih))
        if scale < 1.0:
            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))
            im = im.resize((new_w, new_h), Image.LANCZOS)
        # bitmapResolution=2 -> tâm theo pixel = w (vì Scratch chia cho 2)
        bitmap_resolution = 2
        # nhân đôi để giữ nét khi hiển thị
        im2 = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        data = _pil_to_png_bytes(im2)
        asset_id = md5_bytes(data)
        return PreparedAsset(
            md5ext=f"{asset_id}.png",
            asset_id=asset_id,
            data=data,
            data_format="png",
            width=im2.width, height=im2.height,
            rotation_center_x=im2.width / 2,
            rotation_center_y=im2.height / 2,
            bitmap_resolution=bitmap_resolution,
        )


def load_preview_image(path: Path, target_size: tuple[int, int]) -> Image.Image | None:
    """Đọc costume đã có trong sb3 để xem trước (None nếu là SVG / không đọc được)."""
    try:
        ext = path.suffix.lower()
        if ext in SVG_EXTS:
            return None
        with Image.open(path) as im:
            im = im.convert("RGBA")
            im.thumbnail(target_size, Image.LANCZOS)
            return im.copy()
    except Exception:
        return None
