from __future__ import annotations

from typing import Any


CRITIC_SYSTEM_PROMPT = """
Bạn là chuyên gia phản biện câu hỏi theo rubric.
Chấm 5 tiêu chí: alignment, clarity, accuracy, distractor_quality, explanation_quality.
Không chỉ bám keyword. Trả về JSON hợp lệ, không thêm văn bản ngoài JSON.

JSON:
- scores
- issues
- confidence
- recommended_action
- summary
- recommendations
- revision_focus
""".strip()


def build_critic_prompt(payload: dict[str, Any]) -> str:
    item = payload.get("yccd_item") or {}
    return f"""
Curriculum context:
- Môn học: {item.get("mon", payload.get("subject", ""))}
- Lớp: {item.get("lop", payload.get("lop", ""))}
- Chủ đề: {item.get("chu_de", payload.get("topic", ""))}
- Bài học: {item.get("bai", payload.get("lesson", ""))}
- YCCĐ: {item.get("yccd", payload.get("yccd", ""))}
- Mức độ: {payload.get("muc_do", "")}

PLAN:
{payload.get("plan", {})}

Question:
{payload.get("question", "")}

Options:
{payload.get("options", [])}

Answer:
{payload.get("answer", "")}

Explanation:
{payload.get("explanation", "")}

PREVIOUS CRITIQUE:
{payload.get("critic_report", {})}

ALIGNMENT:
{payload.get("alignment_report", {})}

Return JSON with:
- scores
- issues
- confidence
- recommended_action
- summary
- recommendations
- revision_focus
""".strip()
