"""Chuẩn hoá text không cần AI: Unicode NFC, khoảng trắng, dấu tiếng Việt.

Phần này chạy trước/sau bước AI, đảm bảo output luôn sạch dù AI có sửa hay không.
"""
from __future__ import annotations

import re
import unicodedata


# Bảng chuyển dấu tiếng Việt cũ → kiểu dựng sẵn (đã có NFC nhưng đôi khi vẫn lệch).
_VN_PAIRS = [
    ("òa", "oà"), ("óa", "oá"), ("ỏa", "oả"), ("õa", "oã"), ("ọa", "oạ"),
    ("òe", "oè"), ("óe", "oé"), ("ỏe", "oẻ"), ("õe", "oẽ"), ("ọe", "oẹ"),
    ("ùy", "uỳ"), ("úy", "uý"), ("ủy", "uỷ"), ("ũy", "uỹ"), ("ụy", "uỵ"),
]


def normalize_text(s: str) -> str:
    if not s:
        return s
    # 1. NFC
    s = unicodedata.normalize("NFC", s)
    # 2. chuẩn dấu tiếng Việt (đảo chiều: ưu tiên kiểu mới hợp lý hơn cho VN)
    for old, new in _VN_PAIRS:
        s = s.replace(old, new)
    # 3. khoảng trắng thừa
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()
    return s


def smart_capitalize(s: str) -> str:
    """Viết hoa chữ cái đầu câu (không phá tên riêng đã viết hoa)."""
    s = normalize_text(s)
    if not s:
        return s
    # chỉ viết hoa nếu chữ đầu là chữ thường
    if s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def normalize_list_items(items: list[str], *, capitalize: bool = False) -> list[str]:
    out = []
    for it in items:
        t = normalize_text(str(it))
        if capitalize:
            t = smart_capitalize(t)
        out.append(t)
    return out


def diff_lists(old: list[str], new: list[str]) -> list[tuple[int, str, str]]:
    """Trả về danh sách (index, cũ, mới) chỉ những dòng khác nhau."""
    n = max(len(old), len(new))
    out = []
    for i in range(n):
        a = old[i] if i < len(old) else ""
        b = new[i] if i < len(new) else ""
        if a != b:
            out.append((i, a, b))
    return out
