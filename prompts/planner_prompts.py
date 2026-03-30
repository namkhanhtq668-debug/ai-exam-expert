from __future__ import annotations

from typing import Any


PLANNER_SYSTEM_PROMPT = """
Bạn là planner sinh câu hỏi.
Trả về JSON hợp lệ, không thêm văn bản ngoài JSON.

Bắt buộc:
- objectives
- topic_focus
- difficulty
- question_types
- constraints

Giữ thêm nếu cần:
- strategy
- generation_constraints
- quality_targets
- revision_priority
- plan_notes
- focus_terms
- risk_points
- planning_summary
""".strip()


def build_planner_prompt(payload: dict[str, Any], heuristic_plan: dict[str, Any]) -> str:
    item = payload.get("yccd_item") or {}
    return f"""
INPUT:
- Môn học: {item.get("mon", payload.get("subject", ""))}
- Lớp: {item.get("lop", payload.get("lop", ""))}
- Chủ đề: {item.get("chu_de", payload.get("topic", ""))}
- Bài học: {item.get("bai", payload.get("lesson", ""))}
- YCCĐ: {item.get("yccd", payload.get("yccd", ""))}
- Mức độ: {payload.get("muc_do", "")}
- Số câu: {payload.get("num_questions", 1)}
- Loại câu hỏi: {payload.get("question_types", [])}

CURRICULUM_CONTEXT:
{payload.get("curriculum_context", {})}

HEURISTIC PLAN:
{heuristic_plan}

JSON keys:
- objectives
- topic_focus
- difficulty
- question_types
- constraints

Giữ thêm nếu hữu ích:
- strategy
- generation_constraints
- quality_targets
- revision_priority
- plan_notes
- focus_terms
- risk_points
- planning_summary
""".strip()
