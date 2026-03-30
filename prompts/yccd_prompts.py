from __future__ import annotations

from typing import Any


YCCD_SAFE_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


def build_yccd_question_prompt(
    yccd_item: dict[str, Any],
    muc_do: str = "ThÃ´ng hiá»ƒu",
    *,
    context: dict[str, Any] | None = None,
) -> str:
    item = yccd_item or {}
    context = context or {}
    strategy = context.get("strategy", {})
    critique = context.get("critique", {})
    revision_focus = context.get("revision_focus", [])
    plan_notes = context.get("plan_notes", [])
    quality_targets = context.get("quality_targets", [])
    focus_terms = context.get("focus_terms", [])

    extra_prompt_sections: list[str] = []
    if strategy:
        extra_prompt_sections.append(f"- Chiến lược sinh: {strategy}")
    if plan_notes:
        extra_prompt_sections.append("- Ghi chú kế hoạch: " + "; ".join(str(note) for note in plan_notes))
    if quality_targets:
        extra_prompt_sections.append("- Mục tiêu chất lượng: " + "; ".join(str(target) for target in quality_targets))
    if focus_terms:
        extra_prompt_sections.append("- Từ khóa trọng tâm: " + ", ".join(str(term) for term in focus_terms))
    if critique:
        extra_prompt_sections.append("- Phản biện trước đó: " + str(critique))
    if revision_focus:
        extra_prompt_sections.append("- Điểm cần sửa: " + "; ".join(str(item) for item in revision_focus))
    extra_section = "\n".join(extra_prompt_sections)
    if extra_section:
        extra_section = f"\n\nBỐI CẢNH THÔNG MINH ĐỂ SINH/SỬA:\n{extra_section}"

    return f"""
VAI TRÒ: Giáo viên Toán Tiểu học (Chương trình GDPT 2018).
NHIỆM VỤ: Soạn 01 câu hỏi trắc nghiệm Toán.
THÔNG TIN BẮT BUỘC:
- Lớp: {item.get('lop', '')}
- Chủ đề: {item.get('chu_de', '')}
- Bài học: {item.get('bai', '')}
- YCCĐ: {item.get('yccd', '')}
- Mức độ: {muc_do}
{extra_section}

YÊU CẦU ĐẦU RA (JSON format):
{{
    "question": "Nội dung câu hỏi (ngắn gọn, dễ hiểu)",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "A, B, C hoặc D",
    "explanation": "Giải thích ngắn gọn, sư phạm"
}}
""".strip()
