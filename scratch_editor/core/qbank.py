"""Ngân hàng câu hỏi: ánh xạ nhiều list Scratch thành bảng câu hỏi.

Quy ước cột phổ biến cho dự án thi:
  - cau_hoi        : nội dung câu hỏi
  - dap_an_a / b / c / d
  - dap_an_dung    : 'A' | 'B' | 'C' | 'D'  hoặc số 1..4
  - giai_thich     : (tùy chọn)
Người dùng có thể thêm/đổi cột tùy ý – module này chỉ cần map tên list <-> tên cột.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.project_model import ProjectModel, ListEntry


@dataclass
class QBankMapping:
    target_name: str             # sprite/stage chứa các list
    columns: dict[str, str]      # {column_name: list_id}


def discover_question_lists(model: ProjectModel) -> list[QBankMapping]:
    """Đoán tự động: gom các list theo target, mỗi target = 1 mapping."""
    mappings: dict[str, dict[str, str]] = {}
    for le in model.iter_lists():
        mappings.setdefault(le.target_name, {})[le.name] = le.list_id
    return [QBankMapping(target_name=t, columns=cols)
            for t, cols in mappings.items() if cols]


def export_to_csv(model: ProjectModel, mapping: QBankMapping,
                  out_path: Path) -> int:
    """Xuất các list được map thành CSV. Trả về số dòng đã ghi."""
    target = model.target_by_name(mapping.target_name)
    if not target:
        raise ValueError(f"Không có target '{mapping.target_name}'")

    cols = list(mapping.columns.keys())
    rows_data: dict[str, list] = {}
    max_len = 0
    for col, lid in mapping.columns.items():
        payload = (target.get("lists") or {}).get(lid)
        items = payload[1] if payload and isinstance(payload, list) else []
        rows_data[col] = [str(x) for x in items]
        max_len = max(max_len, len(items))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for i in range(max_len):
            row = []
            for c in cols:
                vals = rows_data[c]
                row.append(vals[i] if i < len(vals) else "")
            writer.writerow(row)
    return max_len


def import_from_csv(model: ProjectModel, mapping: QBankMapping,
                    csv_path: Path, create_missing_lists: bool = False) -> dict:
    """Đọc CSV và ghi đè các list tương ứng.

    Trả về dict {column: rows_written}.
    """
    target = model.target_by_name(mapping.target_name)
    if not target:
        raise ValueError(f"Không có target '{mapping.target_name}'")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []

    # Cho phép mapping mở rộng: dùng tên cột làm tên list nếu chưa có
    target_lists = target.setdefault("lists", {})
    result: dict[str, int] = {}

    for col in headers:
        lid = mapping.columns.get(col)
        if not lid:
            if not create_missing_lists:
                continue
            # tạo list mới với id giả định = col-name (Scratch chấp nhận id tùy ý)
            lid = f"qbank_{col}"
            target_lists[lid] = [col, []]
            mapping.columns[col] = lid
        payload = target_lists.get(lid)
        if not payload:
            target_lists[lid] = [col, []]
            payload = target_lists[lid]
        new_items = [r.get(col, "") for r in rows]
        payload[1] = new_items
        result[col] = len(new_items)
    return result


def render_preview(model: ProjectModel, mapping: QBankMapping,
                   max_rows: int = 20) -> list[list[str]]:
    """Trả về bảng [[header], row1, row2, ...] để hiển thị."""
    target = model.target_by_name(mapping.target_name)
    if not target:
        return []
    cols = list(mapping.columns.keys())
    data = []
    max_len = 0
    for lid in mapping.columns.values():
        p = (target.get("lists") or {}).get(lid)
        items = p[1] if p else []
        data.append([str(x) for x in items])
        max_len = max(max_len, len(items))
    table = [cols]
    for i in range(min(max_rows, max_len)):
        row = []
        for col_idx in range(len(cols)):
            vals = data[col_idx]
            row.append(vals[i] if i < len(vals) else "")
        table.append(row)
    return table
