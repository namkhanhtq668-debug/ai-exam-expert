# -*- coding: utf-8 -*-
"""
Reviewer — kiểm định và chỉnh sửa giáo án TRƯỚC khi xuất DOCX.

Chạy SAU normalizer, TRƯỚC renderer. Mục tiêu: file giáo viên mở Word
có thể chỉnh tên cá nhân và nộp tổ ngay.

8 rule heuristic (deterministic, không gọi AI):
    1. Quét sâu phrase cấm (regex pattern, bắt biến thể)
    2. Dedup dòng trùng trong list (case-insensitive)
    3. Dedup row trùng trong bảng hoạt động
    4. Fill "......" cho field cá nhân còn trống (tuần/tiết/ngày dạy/GV/...)
    5. Fix dấu câu: bỏ space thừa trước "., ;: !?", bỏ "..." dư
    6. Viết hoa chữ đầu của mỗi bullet/câu
    7. Đảm bảo bullet kết thúc bằng dấu câu (thêm "." nếu thiếu)
    8. Phát hiện tiêu đề hoạt động trùng lặp → đánh số phân biệt
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .schema import BANNED_PHRASES, SAFE_PLACEHOLDER


# Placeholder cho field cá nhân thiếu — GV tự điền tay sau khi mở Word
TEACHER_FILL_PLACEHOLDER = "......"


@dataclass
class ReviewResult:
    data: Dict[str, Any]
    fixes_applied: List[str] = field(default_factory=list)

    def summary(self) -> str:
        n = len(self.fixes_applied)
        if n == 0:
            return "✅ Giáo án sạch, không cần chỉnh"
        return f"🔧 Đã áp dụng {n} chỉnh sửa tự động"


# ============================================================================
# Rule 1 — Quét sâu phrase cấm (regex pattern)
# ============================================================================

# Patterns mở rộng so với BANNED_PHRASES — bắt biến thể câu rác AI hay sinh
_BANNED_PATTERNS: List[tuple[str, str]] = [
    # (regex, replacement)
    (r"\bAI\s*tạo\b", ""),
    (r"\bAIEXAM\b", ""),
    (r"\bGV\s+bổ\s+sung\s+sau\b", TEACHER_FILL_PLACEHOLDER),
    (r"\bGV\s+bổ\s+sung\b", TEACHER_FILL_PLACEHOLDER),
    (r"\bbổ\s+sung\s+sau\b", TEACHER_FILL_PLACEHOLDER),
    (r"\bChưa\s+nhập\b", TEACHER_FILL_PLACEHOLDER),
    (r"\bGV\s+kiểm\s+tra\s+SGK\b", ""),
    (r"\bGV\s+kiểm\s+tra\s+sau\b", ""),
    (r"\[GV\s+bổ\s+sung\]", TEACHER_FILL_PLACEHOLDER),
    (r"\[GV\s+kiểm\s+tra\s+SGK\]", ""),
    (r"\(theo\s+ảnh\s+SGK\)", ""),
    (r"\(theo\s+metadata\s+KNTT\)", ""),
    (r"\btheo\s+ảnh\s+SGK\b", ""),
    # Các cụm sáo rỗng AI hay dùng
    (r"\bnhư\s+đã\s+nói\s+ở\s+trên\b", ""),
    (r"\btôi\s+là\s+AI\b", ""),
]


def _strip_banned_patterns(text: str, fixes: List[str]) -> str:
    if not text:
        return text
    out = text
    for pattern, repl in _BANNED_PATTERNS:
        if re.search(pattern, out, flags=re.IGNORECASE):
            out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
            kw = pattern.replace(r"\b", "").replace(r"\s+", " ")
            fix_msg = f"Xoá cụm rác '{kw[:30]}'"
            if fix_msg not in fixes:
                fixes.append(fix_msg)
    return out


# ============================================================================
# Rule 5+6+7 — Fix dấu câu, viết hoa, kết thúc dấu câu
# ============================================================================

def _fix_punctuation_spacing(s: str) -> str:
    """Bỏ space thừa trước dấu câu, gộp space liên tiếp."""
    # Space trước dấu câu → bỏ
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    # Sau dấu câu nếu thiếu space (và ký tự sau là chữ) → thêm
    s = re.sub(r"([,.;:!?])(?=[A-Za-zÀ-ỹ])", r"\1 ", s)
    # Bỏ space liên tiếp
    s = re.sub(r"[ \t]{2,}", " ", s)
    # Bỏ "..." dư (3 dấu chấm liên tiếp với dấu chấm khác liền kề)
    s = re.sub(r"\.{4,}", "...", s)
    return s.strip()


def _capitalize_first_letter(s: str) -> str:
    """Viết hoa chữ cái đầu của chuỗi (bỏ qua khoảng trắng dẫn đầu)."""
    if not s:
        return s
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
        if not ch.isspace() and ch not in "•–-*":
            # Gặp ký tự lạ (số, dấu...) thì giữ nguyên
            return s
    return s


def _ensure_terminal_punctuation(s: str) -> str:
    """Đảm bảo câu kết thúc bằng dấu câu — thêm '.' nếu thiếu."""
    if not s:
        return s
    s = s.rstrip()
    if not s:
        return s
    # Bỏ qua nếu là placeholder dấu chấm
    if s in {"...", "......", SAFE_PLACEHOLDER}:
        return s
    if s.endswith(("...", "?", "!", ".", ":", ";")):
        return s
    return s + "."


def _polish_sentence(s: str, fixes: List[str]) -> str:
    """Áp dụng tất cả fix dạng sentence."""
    if not s or s == SAFE_PLACEHOLDER:
        return s
    original = s
    s = _strip_banned_patterns(s, fixes)
    s = _fix_punctuation_spacing(s)
    s = _capitalize_first_letter(s)
    s = _ensure_terminal_punctuation(s)
    # Sau khi xoá phrase cấm có thể còn space dư
    s = re.sub(r"\s+", " ", s).strip()
    if s != original and "Chuẩn hoá câu (dấu/viết hoa)" not in fixes:
        fixes.append("Chuẩn hoá câu (dấu/viết hoa)")
    return s


# ============================================================================
# Rule 2 — Dedup trong list
# ============================================================================

def _dedup_list(items: List[str], fixes: List[str], context: str = "") -> List[str]:
    """Bỏ phần tử trùng (sau khi lowercase + bỏ dấu câu cuối)."""
    seen: set[str] = set()
    result: List[str] = []
    removed = 0
    for x in items:
        if not isinstance(x, str) or not x.strip():
            continue
        key = re.sub(r"[.,;:!?\s]+$", "", x.lower()).strip()
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        result.append(x)
    if removed:
        fixes.append(f"Bỏ {removed} dòng trùng{(' ở ' + context) if context else ''}")
    return result


# ============================================================================
# Rule 4 — Fill placeholder cho field cá nhân thiếu
# ============================================================================

def _fill_personal(value: str, field_name: str, fixes: List[str]) -> str:
    """Field cá nhân (week, period, teachingDate, teacherName, sgkPages):
    1) Strip phrase cấm trước (GV bổ sung, Chưa nhập, ...)
    2) Nếu rỗng/SAFE_PLACEHOLDER → fill '......'
    """
    v = (value or "").strip()
    # Bước 1: xoá phrase cấm
    cleaned = _strip_banned_patterns(v, []).strip()
    # Bước 2: check rỗng/placeholder
    if cleaned in {"", ".", "...", SAFE_PLACEHOLDER, TEACHER_FILL_PLACEHOLDER}:
        if v != TEACHER_FILL_PLACEHOLDER:
            fixes.append(f"Điền '......' cho field cá nhân '{field_name}' (GV tự điền)")
        return TEACHER_FILL_PLACEHOLDER
    return cleaned


# ============================================================================
# Rule 3 + 8 — Dedup row + đánh số tiêu đề trùng trong teachingProcess
# ============================================================================

def _dedup_activity_rows(activity: Dict[str, Any], fixes: List[str]) -> Dict[str, Any]:
    """Bỏ row trùng (cùng GV + HS + Sản phẩm/đánh giá) trong 1 hoạt động."""
    rows = activity.get("rows", [])
    if not isinstance(rows, list):
        return activity
    seen: set[tuple] = set()
    new_rows: List[Dict[str, str]] = []
    removed = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (
            re.sub(r"\s+", " ", r.get("teacherActivities", "").lower()).strip(),
            re.sub(r"\s+", " ", r.get("studentActivities", "").lower()).strip(),
        )
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        new_rows.append(r)
    if removed:
        fixes.append(f"Bỏ {removed} dòng trùng trong bảng hoạt động '{activity.get('title', '?')[:30]}'")
    activity["rows"] = new_rows
    return activity


def _dedup_activity_titles(activities: List[Dict[str, Any]], fixes: List[str]) -> List[Dict[str, Any]]:
    """Nếu 2 hoạt động trùng tên (case-insensitive) → thêm hậu tố (2), (3)..."""
    title_counts: Dict[str, int] = {}
    for act in activities:
        title = (act.get("title", "") or "").strip()
        key = title.lower()
        if not key:
            continue
        title_counts[key] = title_counts.get(key, 0) + 1
        if title_counts[key] > 1:
            new_title = f"{title} ({title_counts[key]})"
            act["title"] = new_title
            fixes.append(f"Đánh số hoạt động trùng tên: '{title[:30]}'")
    return activities


# ============================================================================
# Apply polish trên toàn bộ JSON
# ============================================================================

def _polish_list(items: Any, fixes: List[str]) -> List[str]:
    if not isinstance(items, list):
        return []
    return [_polish_sentence(x, fixes) for x in items if isinstance(x, str) and x.strip()]


def _review_objectives(obj: Dict[str, Any], fixes: List[str]) -> Dict[str, Any]:
    obj = dict(obj) if isinstance(obj, dict) else {}
    for k in ("specificCompetencies", "generalCompetencies", "qualities"):
        polished = _polish_list(obj.get(k), fixes)
        obj[k] = _dedup_list(polished, fixes, context=f"objectives.{k}")
    intro = _polish_sentence(obj.get("intro", ""), fixes)
    if not intro:
        intro = "Sau bài học, học sinh đạt được các yêu cầu sau:"
    obj["intro"] = intro
    return obj


def _review_materials(mat: Dict[str, Any], fixes: List[str]) -> Dict[str, Any]:
    mat = dict(mat) if isinstance(mat, dict) else {}
    for k in ("teacher", "students"):
        polished = _polish_list(mat.get(k), fixes)
        mat[k] = _dedup_list(polished, fixes, context=f"teachingMaterials.{k}")
    return mat


def _review_process(activities: Any, fixes: List[str]) -> List[Dict[str, Any]]:
    if not isinstance(activities, list):
        return []
    out: List[Dict[str, Any]] = []
    for a in activities:
        if not isinstance(a, dict):
            continue
        a = dict(a)
        a["title"] = _polish_sentence(a.get("title", ""), fixes)
        a["duration"] = _polish_sentence(a.get("duration", ""), fixes)
        a["objective"] = _polish_sentence(a.get("objective", ""), fixes)
        # Polish từng row
        rows = a.get("rows", [])
        polished_rows: List[Dict[str, str]] = []
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                polished_rows.append({
                    "teacherActivities": _polish_sentence(r.get("teacherActivities", ""), fixes),
                    "studentActivities": _polish_sentence(r.get("studentActivities", ""), fixes),
                    "productAndAssessment": _polish_sentence(r.get("productAndAssessment", ""), fixes),
                })
        a["rows"] = polished_rows
        a = _dedup_activity_rows(a, fixes)
        out.append(a)
    out = _dedup_activity_titles(out, fixes)
    return out


def _review_differentiation(diff: Dict[str, Any], fixes: List[str]) -> Dict[str, Any]:
    diff = dict(diff) if isinstance(diff, dict) else {}
    for k in ("weakerStudents", "advancedStudents", "limitedResources"):
        diff[k] = _polish_sentence(diff.get(k, ""), fixes) or TEACHER_FILL_PLACEHOLDER
    return diff


def _review_assessment(rows: Any, fixes: List[str]) -> List[Dict[str, str]]:
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({
            "content": _polish_sentence(r.get("content", ""), fixes),
            "criteria": _polish_sentence(r.get("criteria", ""), fixes),
            "method": _polish_sentence(r.get("method", ""), fixes),
            "tool": _polish_sentence(r.get("tool", ""), fixes),
        })
    return out


def _review_worksheet(items: Any, fixes: List[str]) -> List[Dict[str, str]]:
    if not isinstance(items, list):
        return []
    out: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _polish_sentence(item.get("title", ""), fixes)
        body = _strip_banned_patterns(item.get("body", ""), fixes)
        # Body có thể nhiều dòng — chỉ trim space, không touch xuống dòng
        body = re.sub(r"[ \t]+", " ", body).strip()
        if title or body:
            out.append({"title": title, "body": body})
    return out


# ============================================================================
# Public API
# ============================================================================

def review_lesson_plan(data: Dict[str, Any]) -> ReviewResult:
    """Kiểm và chỉnh giáo án sau normalize. KHÔNG mutate input.

    Trả về ReviewResult với data mới + danh sách fix đã áp dụng.
    """
    if not isinstance(data, dict):
        return ReviewResult(data={}, fixes_applied=[])

    fixes: List[str] = []
    out: Dict[str, Any] = {}

    # documentInfo
    di = data.get("documentInfo", {}) or {}
    out["documentInfo"] = {
        "department": _polish_sentence(di.get("department", ""), fixes) or SAFE_PLACEHOLDER,
        "school": _polish_sentence(di.get("school", ""), fixes),
        "schoolYear": _polish_sentence(di.get("schoolYear", ""), fixes),
    }

    # lessonInfo — field cá nhân hay thiếu → '......'
    li = data.get("lessonInfo", {}) or {}
    out["lessonInfo"] = {
        "subject": _polish_sentence(li.get("subject", ""), fixes),
        "grade": (li.get("grade", "") or "").strip(),
        "lessonNumber": _polish_sentence(li.get("lessonNumber", ""), fixes),
        "lessonTitle": _polish_sentence(li.get("lessonTitle", ""), fixes),
        "textbookSeries": _polish_sentence(li.get("textbookSeries", ""), fixes),
        "duration": _polish_sentence(li.get("duration", ""), fixes),
        # 5 field cá nhân — fill '......' nếu rỗng
        "week": _fill_personal(li.get("week", ""), "Tuần", fixes),
        "period": _fill_personal(li.get("period", ""), "Tiết PPCT", fixes),
        "teachingDate": _fill_personal(li.get("teachingDate", ""), "Ngày dạy", fixes),
        "teacherName": _fill_personal(li.get("teacherName", ""), "Giáo viên", fixes),
        "sgkPages": _fill_personal(li.get("sgkPages", ""), "Trang SGK", fixes),
    }

    # 4 mục nội dung chính
    out["objectives"] = _review_objectives(data.get("objectives", {}) or {}, fixes)
    out["teachingMaterials"] = _review_materials(data.get("teachingMaterials", {}) or {}, fixes)
    out["teachingProcess"] = _review_process(data.get("teachingProcess", []), fixes)
    out["differentiation"] = _review_differentiation(data.get("differentiation", {}) or {}, fixes)
    out["assessment"] = _review_assessment(data.get("assessment", []), fixes)
    out["worksheet"] = _review_worksheet(data.get("worksheet", []), fixes)

    return ReviewResult(data=out, fixes_applied=fixes)
