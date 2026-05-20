# -*- coding: utf-8 -*-
"""
Normalizer — chuẩn hoá JSON từ AI trước khi đưa vào renderer.

Chức năng:
1. Thay phrase cấm bằng placeholder lịch sự "..."
2. Chuẩn hoá khoảng trắng (collapse multiple, trim)
3. Chuẩn hoá dấu gạch ngang (em-dash —, en-dash – → "–"; hyphen "-" giữ nguyên)
4. Viết hoa lessonTitle (đảm bảo in hoa theo mẫu PDF)
5. Bỏ phần tử rỗng/None trong list
6. Điền placeholder "..." cho field text rỗng
7. Trả về NormalizationResult kèm danh sách thay đổi để báo cho user

Nguyên tắc: KHÔNG mutate input. Trả về dict mới.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .schema import BANNED_PHRASES, SAFE_PLACEHOLDER


@dataclass
class NormalizationResult:
    data: Dict[str, Any]                            # JSON đã chuẩn hoá
    replaced_phrases: List[str] = field(default_factory=list)  # phrase cấm đã thay
    changes_count: int = 0                          # số trường đã chỉnh

    def summary(self) -> str:
        parts = []
        if self.replaced_phrases:
            parts.append(f"🧹 Thay {len(self.replaced_phrases)} phrase cấm: {', '.join(self.replaced_phrases[:5])}")
        if self.changes_count:
            parts.append(f"✏️ {self.changes_count} chỉnh sửa nhỏ")
        return " | ".join(parts) if parts else "✅ Không cần chuẩn hoá"


# ============================================================================
# Helpers
# ============================================================================

# Phrase cấm sắp xếp theo độ dài giảm dần — quan trọng vì replace tham lam,
# không thì "GV bổ sung" sẽ bị "bổ sung sau" match nhầm.
_BANNED_SORTED = sorted(BANNED_PHRASES, key=len, reverse=True)


def _normalize_dashes(s: str) -> str:
    """Chuẩn hoá em-dash/en-dash về một dạng nhất quán cho header trang.

    Trong file giáo án mẫu, "Độc lập - Tự do - Hạnh phúc" dùng hyphen "-".
    Code không can thiệp hyphen thông thường — chỉ chuyển em-dash "—" thành " - ".
    """
    s = s.replace("—", " - ")  # em-dash
    s = s.replace("–", " - ")  # en-dash
    s = re.sub(r"\s+-\s+", " - ", s)  # chuẩn hoá space xung quanh hyphen
    return s


def _collapse_whitespace(s: str) -> str:
    """Trim + giảm khoảng trắng liên tiếp về 1 space (giữ \\n nguyên cho body bài tập)."""
    # Giữ \n vì worksheet.body có thể có dòng mới
    lines = s.split("\n")
    cleaned = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in lines]
    # Bỏ dòng rỗng liên tiếp ở giữa
    result: List[str] = []
    prev_empty = False
    for line in cleaned:
        if not line:
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False
    # Trim dòng rỗng ở đầu/cuối
    while result and not result[0]:
        result.pop(0)
    while result and not result[-1]:
        result.pop()
    return "\n".join(result)


def _replace_banned(s: str, found_acc: List[str]) -> str:
    """Thay tất cả phrase cấm trong s thành SAFE_PLACEHOLDER. Ghi nhận vào found_acc."""
    out = s
    for phrase in _BANNED_SORTED:
        # Case-insensitive nhưng giữ thay bằng SAFE_PLACEHOLDER
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(out):
            if phrase not in found_acc:
                found_acc.append(phrase)
            out = pattern.sub(SAFE_PLACEHOLDER, out)
    return out


def _clean_string(s: Any, found_acc: List[str], counter: List[int]) -> str:
    """Chuẩn hoá 1 string. Counter là list[int] dùng làm reference để đếm thay đổi."""
    if not isinstance(s, str):
        return ""
    original = s
    s = _replace_banned(s, found_acc)
    s = _normalize_dashes(s)
    s = _collapse_whitespace(s)
    if s != original:
        counter[0] += 1
    return s


def _clean_string_list(items: Any, found_acc: List[str], counter: List[int]) -> List[str]:
    """Chuẩn hoá list of string, bỏ phần tử rỗng sau khi clean."""
    if not isinstance(items, list):
        return []
    result: List[str] = []
    for item in items:
        cleaned = _clean_string(item, found_acc, counter)
        if cleaned:
            result.append(cleaned)
    return result


def _fill_placeholder(s: str) -> str:
    """Field text BẮT BUỘC nhưng rỗng → trả SAFE_PLACEHOLDER."""
    return s if s.strip() else SAFE_PLACEHOLDER


# ============================================================================
# Normalize từng nhóm
# ============================================================================

def _normalize_document_info(info: Any, found: List[str], counter: List[int]) -> Dict[str, str]:
    if not isinstance(info, dict):
        info = {}
    return {
        "department": _fill_placeholder(_clean_string(info.get("department", ""), found, counter)),
        "school": _clean_string(info.get("school", ""), found, counter),
        "schoolYear": _clean_string(info.get("schoolYear", ""), found, counter),
    }


def _normalize_lesson_info(info: Any, found: List[str], counter: List[int]) -> Dict[str, str]:
    if not isinstance(info, dict):
        info = {}
    cleaned = {
        "subject": _clean_string(info.get("subject", ""), found, counter),
        "grade": _clean_string(info.get("grade", ""), found, counter),
        "lessonNumber": _clean_string(info.get("lessonNumber", ""), found, counter),
        "lessonTitle": _clean_string(info.get("lessonTitle", ""), found, counter),
        "textbookSeries": _clean_string(info.get("textbookSeries", ""), found, counter),
        "duration": _clean_string(info.get("duration", ""), found, counter),
        "week": _fill_placeholder(_clean_string(info.get("week", ""), found, counter)),
        "period": _fill_placeholder(_clean_string(info.get("period", ""), found, counter)),
        "teachingDate": _clean_string(info.get("teachingDate", ""), found, counter),
        "teacherName": _fill_placeholder(_clean_string(info.get("teacherName", ""), found, counter)),
        "sgkPages": _fill_placeholder(_clean_string(info.get("sgkPages", ""), found, counter)),
    }
    # Tên bài học PHẢI in hoa theo mẫu PDF
    if cleaned["lessonTitle"]:
        upper = cleaned["lessonTitle"].upper()
        if upper != cleaned["lessonTitle"]:
            counter[0] += 1
            cleaned["lessonTitle"] = upper
    return cleaned


def _normalize_objectives(obj: Any, found: List[str], counter: List[int]) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        obj = {}
    intro = _clean_string(obj.get("intro", ""), found, counter)
    if not intro:
        intro = "Sau bài học, học sinh đạt được các yêu cầu sau:"
    return {
        "intro": intro,
        "specificCompetencies": _clean_string_list(obj.get("specificCompetencies"), found, counter),
        "generalCompetencies": _clean_string_list(obj.get("generalCompetencies"), found, counter),
        "qualities": _clean_string_list(obj.get("qualities"), found, counter),
    }


def _normalize_teaching_materials(mat: Any, found: List[str], counter: List[int]) -> Dict[str, List[str]]:
    if not isinstance(mat, dict):
        mat = {}
    return {
        "teacher": _clean_string_list(mat.get("teacher"), found, counter),
        "students": _clean_string_list(mat.get("students"), found, counter),
    }


def _normalize_activity(act: Any, found: List[str], counter: List[int]) -> Dict[str, Any]:
    if not isinstance(act, dict):
        return {"title": "", "duration": "", "objective": "", "rows": []}
    rows_in = act.get("rows", [])
    rows_out: List[Dict[str, str]] = []
    if isinstance(rows_in, list):
        for row in rows_in:
            if not isinstance(row, dict):
                continue
            r = {
                "teacherActivities": _clean_string(row.get("teacherActivities", ""), found, counter),
                "studentActivities": _clean_string(row.get("studentActivities", ""), found, counter),
                "productAndAssessment": _clean_string(row.get("productAndAssessment", ""), found, counter),
            }
            # Bỏ row hoàn toàn rỗng
            if any(r.values()):
                rows_out.append(r)
    return {
        "title": _clean_string(act.get("title", ""), found, counter),
        "duration": _clean_string(act.get("duration", ""), found, counter),
        "objective": _clean_string(act.get("objective", ""), found, counter),
        "rows": rows_out,
    }


def _normalize_differentiation(diff: Any, found: List[str], counter: List[int]) -> Dict[str, str]:
    if not isinstance(diff, dict):
        diff = {}
    return {
        "weakerStudents": _fill_placeholder(_clean_string(diff.get("weakerStudents", ""), found, counter)),
        "advancedStudents": _fill_placeholder(_clean_string(diff.get("advancedStudents", ""), found, counter)),
        "limitedResources": _fill_placeholder(_clean_string(diff.get("limitedResources", ""), found, counter)),
    }


def _normalize_assessment(assess: Any, found: List[str], counter: List[int]) -> List[Dict[str, str]]:
    if not isinstance(assess, list):
        return []
    result: List[Dict[str, str]] = []
    for row in assess:
        if not isinstance(row, dict):
            continue
        r = {
            "content": _clean_string(row.get("content", ""), found, counter),
            "criteria": _clean_string(row.get("criteria", ""), found, counter),
            "method": _clean_string(row.get("method", ""), found, counter),
            "tool": _clean_string(row.get("tool", ""), found, counter),
        }
        if any(r.values()):
            result.append(r)
    return result


def _normalize_worksheet(ws: Any, found: List[str], counter: List[int]) -> List[Dict[str, str]]:
    if not isinstance(ws, list):
        return []
    result: List[Dict[str, str]] = []
    for item in ws:
        if not isinstance(item, dict):
            continue
        title = _clean_string(item.get("title", ""), found, counter)
        body = _clean_string(item.get("body", ""), found, counter)
        if title or body:
            result.append({"title": title, "body": body})
    return result


# ============================================================================
# Public API
# ============================================================================

def normalize_lesson_plan(data: Dict[str, Any]) -> NormalizationResult:
    """Chuẩn hoá toàn bộ JSON giáo án. KHÔNG mutate input.

    Args:
        data: dict đã parse từ AI (hoặc dữ liệu nhập tay).

    Returns:
        NormalizationResult chứa `data` (đã sạch) + `replaced_phrases` + `changes_count`.
    """
    if not isinstance(data, dict):
        return NormalizationResult(data={}, replaced_phrases=[], changes_count=0)

    src = copy.deepcopy(data)
    found: List[str] = []
    counter: List[int] = [0]  # dùng list để truyền tham chiếu qua các helper

    cleaned = {
        "documentInfo": _normalize_document_info(src.get("documentInfo"), found, counter),
        "lessonInfo": _normalize_lesson_info(src.get("lessonInfo"), found, counter),
        "objectives": _normalize_objectives(src.get("objectives"), found, counter),
        "teachingMaterials": _normalize_teaching_materials(src.get("teachingMaterials"), found, counter),
        "teachingProcess": [
            _normalize_activity(a, found, counter)
            for a in (src.get("teachingProcess") or [])
            if isinstance(a, dict)
        ],
        "differentiation": _normalize_differentiation(src.get("differentiation"), found, counter),
        "assessment": _normalize_assessment(src.get("assessment"), found, counter),
        "worksheet": _normalize_worksheet(src.get("worksheet"), found, counter),
    }

    return NormalizationResult(data=cleaned, replaced_phrases=found, changes_count=counter[0])
