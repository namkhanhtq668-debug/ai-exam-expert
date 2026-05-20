# -*- coding: utf-8 -*-
"""
Validator — kiểm tra JSON từ AI khớp schema và không chứa phrase cấm.

Trả về `ValidationResult`:
- `ok`: True/False
- `errors`: lỗi nghiêm trọng phải fix trước khi render (thiếu trường BẮT BUỘC, JSON sai loại)
- `warnings`: cảnh báo có thể bỏ qua (tổng thời gian lệch, hoạt động dài...)
- `banned_phrases_found`: danh sách cụ thể phrase cấm tìm thấy (để normalizer xử lý)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .schema import (
    BANNED_PHRASES,
    MAX_ACTIVITIES,
    MIN_ACTIVITIES,
    REQUIRED_DOCUMENT_INFO,
    REQUIRED_LESSON_INFO,
    REQUIRED_TOP_LEVEL_KEYS,
)


@dataclass
class ValidationResult:
    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    banned_phrases_found: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"❌ {len(self.errors)} lỗi: " + "; ".join(self.errors[:3]))
        if self.warnings:
            parts.append(f"⚠️ {len(self.warnings)} cảnh báo")
        if self.banned_phrases_found:
            parts.append(f"🚫 Phrase cấm: {', '.join(self.banned_phrases_found[:5])}")
        if not parts:
            parts.append("✅ Hợp lệ, sạch sẽ")
        return " | ".join(parts)


# ============================================================================
# Helper: duyệt tất cả string trong dict/list lồng nhau
# ============================================================================

def _iter_strings(node: Any):
    """Generator duyệt mọi string nằm sâu trong cấu trúc dict/list."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_strings(v)


def find_banned_phrases(data: Dict[str, Any]) -> List[str]:
    """Quét toàn bộ JSON, trả về danh sách phrase cấm xuất hiện (đã dedupe)."""
    found: List[str] = []
    blob = "\n".join(_iter_strings(data))
    blob_lower = blob.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in blob_lower and phrase not in found:
            found.append(phrase)
    return found


# ============================================================================
# Parse duration "X phút" → int
# ============================================================================

def _parse_minutes(text: str) -> Optional[int]:
    """Lấy số phút từ chuỗi như '5 phút', '10 phut', '01 tiết (35 phút)'."""
    if not text:
        return None
    # Ưu tiên số ngay trước "phút"
    m = re.search(r"(\d+)\s*ph[úu]t", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: số đầu tiên
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


# ============================================================================
# Validate từng phần
# ============================================================================

def _validate_top_level(data: Any, r: ValidationResult) -> bool:
    if not isinstance(data, dict):
        r.add_error("JSON gốc phải là object (dict), không phải list/string.")
        return False
    missing = [k for k in REQUIRED_TOP_LEVEL_KEYS if k not in data]
    if missing:
        r.add_error(f"Thiếu trường cấp 1 BẮT BUỘC: {', '.join(missing)}")
        return False
    return True


def _validate_document_info(info: Any, r: ValidationResult) -> None:
    if not isinstance(info, dict):
        r.add_error("documentInfo phải là object.")
        return
    for k in REQUIRED_DOCUMENT_INFO:
        v = info.get(k)
        if not (isinstance(v, str) and v.strip()):
            r.add_error(f"documentInfo.{k} bị thiếu hoặc rỗng.")


def _validate_lesson_info(info: Any, r: ValidationResult) -> None:
    if not isinstance(info, dict):
        r.add_error("lessonInfo phải là object.")
        return
    for k in REQUIRED_LESSON_INFO:
        v = info.get(k)
        if not (isinstance(v, str) and v.strip()):
            r.add_error(f"lessonInfo.{k} bị thiếu hoặc rỗng.")


def _validate_objectives(obj: Any, r: ValidationResult) -> None:
    if not isinstance(obj, dict):
        r.add_error("objectives phải là object.")
        return
    for k in ("specificCompetencies", "generalCompetencies", "qualities"):
        v = obj.get(k)
        if not isinstance(v, list) or not v:
            r.add_error(f"objectives.{k} phải là list không rỗng.")
        elif any(not (isinstance(x, str) and x.strip()) for x in v):
            r.add_warning(f"objectives.{k} có phần tử rỗng/không phải string.")


def _validate_teaching_materials(mat: Any, r: ValidationResult) -> None:
    if not isinstance(mat, dict):
        r.add_error("teachingMaterials phải là object.")
        return
    for k in ("teacher", "students"):
        v = mat.get(k)
        if not isinstance(v, list) or not v:
            r.add_error(f"teachingMaterials.{k} phải là list không rỗng.")


def _validate_teaching_process(
    process: Any, r: ValidationResult, expected_duration: Optional[int]
) -> None:
    if not isinstance(process, list):
        r.add_error("teachingProcess phải là list.")
        return
    n = len(process)
    if n < MIN_ACTIVITIES:
        r.add_error(f"teachingProcess có {n} hoạt động, tối thiểu {MIN_ACTIVITIES}.")
        return
    if n > MAX_ACTIVITIES:
        r.add_error(f"teachingProcess có {n} hoạt động, tối đa {MAX_ACTIVITIES}.")
        return

    total_minutes = 0
    has_unparsed_duration = False
    for i, act in enumerate(process, 1):
        prefix = f"teachingProcess[{i}]"
        if not isinstance(act, dict):
            r.add_error(f"{prefix} phải là object.")
            continue
        for k in ("title", "duration", "objective"):
            v = act.get(k)
            if not (isinstance(v, str) and v.strip()):
                r.add_error(f"{prefix}.{k} thiếu hoặc rỗng.")

        # Parse duration
        mins = _parse_minutes(str(act.get("duration", "")))
        if mins is None:
            has_unparsed_duration = True
        else:
            total_minutes += mins

        # rows
        rows = act.get("rows")
        if not isinstance(rows, list) or not rows:
            r.add_error(f"{prefix}.rows phải là list không rỗng.")
        else:
            for j, row in enumerate(rows, 1):
                if not isinstance(row, dict):
                    r.add_error(f"{prefix}.rows[{j}] phải là object.")
                    continue
                for k in ("teacherActivities", "studentActivities", "productAndAssessment"):
                    v = row.get(k)
                    if not (isinstance(v, str) and v.strip()):
                        r.add_error(f"{prefix}.rows[{j}].{k} thiếu hoặc rỗng.")

    if expected_duration is not None and not has_unparsed_duration:
        diff = abs(total_minutes - expected_duration)
        if diff > 2:
            r.add_warning(
                f"Tổng thời gian {total_minutes} phút lệch {diff} phút so với {expected_duration} phút yêu cầu."
            )


def _validate_differentiation(diff: Any, r: ValidationResult) -> None:
    if not isinstance(diff, dict):
        r.add_error("differentiation phải là object.")
        return
    for k in ("weakerStudents", "advancedStudents", "limitedResources"):
        v = diff.get(k)
        if not (isinstance(v, str) and v.strip()):
            r.add_warning(f"differentiation.{k} thiếu/rỗng — sẽ in placeholder.")


def _validate_assessment(assess: Any, r: ValidationResult) -> None:
    if not isinstance(assess, list):
        r.add_error("assessment phải là list.")
        return
    if not assess:
        r.add_warning("assessment rỗng — sẽ bỏ qua mục V hoặc dùng placeholder.")
        return
    for i, row in enumerate(assess, 1):
        prefix = f"assessment[{i}]"
        if not isinstance(row, dict):
            r.add_error(f"{prefix} phải là object.")
            continue
        for k in ("content", "criteria", "method", "tool"):
            v = row.get(k)
            if not (isinstance(v, str) and v.strip()):
                r.add_error(f"{prefix}.{k} thiếu/rỗng.")


def _validate_worksheet(ws: Any, r: ValidationResult) -> None:
    if not isinstance(ws, list):
        r.add_warning("worksheet không phải list — sẽ bỏ qua mục VI.")
        return
    for i, item in enumerate(ws, 1):
        if not isinstance(item, dict):
            r.add_warning(f"worksheet[{i}] không phải object — bỏ qua.")
            continue
        for k in ("title", "body"):
            v = item.get(k)
            if not (isinstance(v, str) and v.strip()):
                r.add_warning(f"worksheet[{i}].{k} thiếu — sẽ bỏ qua bài tập này.")


# ============================================================================
# Public API
# ============================================================================

def validate_lesson_plan(
    data: Dict[str, Any],
    expected_duration_minutes: Optional[int] = None,
) -> ValidationResult:
    """Validate toàn bộ JSON giáo án.

    Args:
        data: dict JSON từ AI (đã parse).
        expected_duration_minutes: tổng thời lượng tiết học để check khớp (None = bỏ qua).

    Returns:
        ValidationResult với errors/warnings/banned_phrases_found.
    """
    r = ValidationResult()

    if not _validate_top_level(data, r):
        return r

    _validate_document_info(data.get("documentInfo"), r)
    _validate_lesson_info(data.get("lessonInfo"), r)
    _validate_objectives(data.get("objectives"), r)
    _validate_teaching_materials(data.get("teachingMaterials"), r)
    _validate_teaching_process(data.get("teachingProcess"), r, expected_duration_minutes)
    _validate_differentiation(data.get("differentiation"), r)
    _validate_assessment(data.get("assessment"), r)
    _validate_worksheet(data.get("worksheet", []), r)

    # Quét phrase cấm sau cùng — không khiến ok=False, chỉ để normalizer xử lý
    r.banned_phrases_found = find_banned_phrases(data)

    return r
