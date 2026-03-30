from __future__ import annotations

from typing import Any


ALIGNMENT_SYSTEM_PROMPT = """
Bạn là reviewer alignment cho curriculum context.
Đánh giá theo ngữ cảnh môn học, lớp, chủ đề, bài học, YCCĐ.
Không chỉ bám keyword. Trả về JSON hợp lệ, không thêm văn bản ngoài JSON.

JSON:
- score
- matched_points
- missing_points
- off_topic_points
- confidence
- summary
- recommendations
""".strip()


def build_alignment_prompt(payload: dict[str, Any]) -> str:
    item = payload.get("yccd_item") or {}
    return f"""
Curriculum context:
- Môn học: {item.get("mon", payload.get("subject", ""))}
- Lớp: {item.get("lop", payload.get("lop", ""))}
- Chủ đề: {item.get("chu_de", payload.get("topic", ""))}
- Bài học: {item.get("bai", payload.get("lesson", ""))}
- YCCĐ: {item.get("yccd", payload.get("yccd", ""))}
- Mức độ: {payload.get("muc_do", "")}

Question:
{payload.get("question", "")}

Explanation:
{payload.get("explanation", "")}

Options:
{payload.get("options", [])}

Answer:
{payload.get("answer", "")}

Return JSON with:
- score
- matched_points
- missing_points
- off_topic_points
- confidence
- summary
- recommendations
""".strip()
