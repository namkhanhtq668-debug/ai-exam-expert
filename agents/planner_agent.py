from __future__ import annotations

from os import getenv
from copy import deepcopy
from typing import Any

from agents.base_agent import BaseAgent
from clients.base_llm_client import BaseLLMClient
from services.llm_utils import call_with_timeout
from prompts.planner_prompts import PLANNER_SYSTEM_PROMPT, build_planner_prompt

_DEFAULT_QUESTION_TYPES = ["multiple_choice"]
_DEFAULT_LANGUAGE = "vi"


class PlannerAgent(BaseAgent):
    def __init__(self, llm_client: BaseLLMClient | None = None):
        super().__init__()
        self.llm_client = llm_client

    @staticmethod
    def _coerce_text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_focus_terms(cls, text: str, *, limit: int = 8) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for token in cls._coerce_text(text).replace(",", " ").split():
            normalized = token.strip().lower()
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(token.strip())
            if len(terms) >= limit:
                break
        return terms

    def _derive_topic_focus(self, payload: dict[str, Any]) -> dict[str, str]:
        yccd_item = dict(payload.get("yccd_item") or {})
        return {
            "subject": self._coerce_text(yccd_item.get("mon") or payload.get("subject")),
            "grade": self._coerce_text(yccd_item.get("lop") or payload.get("lop")),
            "topic": self._coerce_text(yccd_item.get("chu_de") or payload.get("topic")),
            "lesson": self._coerce_text(yccd_item.get("bai") or payload.get("lesson")),
            "yccd": self._coerce_text(yccd_item.get("yccd") or payload.get("yccd")),
        }

    def _derive_difficulty(self, payload: dict[str, Any], grade: int | None) -> dict[str, Any]:
        muc_do = self._coerce_text(payload.get("muc_do") or "Thông hiểu")
        grade_band = "tiểu học"
        if grade is not None:
            if grade >= 5:
                grade_band = "cuối tiểu học"
            elif grade >= 3:
                grade_band = "giữa tiểu học"
            else:
                grade_band = "đầu tiểu học"

        level_map = {
            "Nhận biết": {"level": "nhan_biet", "label": "Nhận biết", "intensity": "low"},
            "Thông hiểu": {"level": "thong_hieu", "label": "Thông hiểu", "intensity": "medium"},
            "Vận dụng": {"level": "van_dung", "label": "Vận dụng", "intensity": "medium_high"},
            "Vận dụng cao": {"level": "van_dung_cao", "label": "Vận dụng cao", "intensity": "high"},
        }
        mapped = level_map.get(muc_do, {"level": "thong_hieu", "label": muc_do or "Thông hiểu", "intensity": "medium"})

        return {
            "requested": muc_do,
            "level": mapped["level"],
            "label": mapped["label"],
            "intensity": mapped["intensity"],
            "grade_band": grade_band,
        }

    def _build_heuristic_plan(self, input_data: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
        payload = dict(input_data or {})
        yccd_item = dict(payload.get("yccd_item") or {})
        grade = self._coerce_int(yccd_item.get("lop") or payload.get("lop"))
        topic_focus = self._derive_topic_focus(payload)
        difficulty = self._derive_difficulty(payload, grade)

        issues: list[str] = []
        required_keys = ["lop", "chu_de", "bai", "yccd"]
        missing = [key for key in required_keys if not self._coerce_text(yccd_item.get(key))]
        if missing:
            issues.append(f"Thiếu trường bắt buộc: {', '.join(missing)}")

        num_questions = self._coerce_int(payload.get("num_questions")) or 1
        question_types = list(payload.get("question_types") or _DEFAULT_QUESTION_TYPES)
        if not question_types:
            question_types = list(_DEFAULT_QUESTION_TYPES)

        yccd_text = topic_focus["yccd"]
        focus_terms = self._extract_focus_terms(yccd_text, limit=8)

        grade_band = difficulty["grade_band"]
        heuristic_plan = {
            "objectives": [
                f"Sinh câu hỏi bám sát YCCĐ: {yccd_text}" if yccd_text else "Sinh câu hỏi bám sát YCCĐ",
                f"Phù hợp lớp {topic_focus['grade'] or grade if grade is not None else ''} và chủ đề {topic_focus['topic'] or ''}".strip(),
                f"Đảm bảo mức độ {difficulty['label'].lower()} và dùng được cho giáo viên",
            ],
            "topic_focus": {
                "subject": topic_focus["subject"],
                "grade": topic_focus["grade"],
                "topic": topic_focus["topic"],
                "lesson": topic_focus["lesson"],
                "yccd": topic_focus["yccd"],
                "focus_terms": focus_terms,
            },
            "difficulty": {
                "requested": difficulty["requested"],
                "level": difficulty["level"],
                "label": difficulty["label"],
                "intensity": difficulty["intensity"],
                "grade_band": grade_band,
            },
            "question_types": question_types,
            "constraints": {
                "language": payload.get("language", _DEFAULT_LANGUAGE),
                "num_questions": num_questions,
                "option_count": int(payload.get("option_count") or 4),
                "must_align_with_yccd": True,
                "must_match_curriculum_context": True,
                "must_match_difficulty": True,
                "must_include_answer": True,
                "must_include_explanation": True,
                "answer_format": "A/B/C/D",
                "teacher_input_priority": [
                    "yccd_item",
                    "muc_do",
                    "num_questions",
                    "question_types",
                ],
            },
            "curriculum_context": {
                "subject": topic_focus["subject"],
                "grade": topic_focus["grade"],
                "grade_band": grade_band,
                "topic": topic_focus["topic"],
                "lesson": topic_focus["lesson"],
                "yccd": topic_focus["yccd"],
            },
            "generation_constraints": {
                "question_type": question_types[0],
                "question_types": question_types,
                "option_count": int(payload.get("option_count") or 4),
                "language": payload.get("language", _DEFAULT_LANGUAGE),
                "difficulty_hint": difficulty["level"],
                "must_include_answer": True,
                "must_include_explanation": True,
                "num_questions": num_questions,
            },
            "strategy": {
                "target_skill": difficulty["label"],
                "question_style": "ngắn gọn, rõ ràng, bám yêu cầu cần đạt",
                "scaffold_level": "high" if difficulty["intensity"] in {"low", "medium"} else "medium",
            },
            "focus_terms": focus_terms,
            "quality_targets": [
                "Bám sát YCCĐ và ngữ cảnh curriculum",
                "Phương án/đáp án rõ ràng, dùng được ngay",
                "Lời giải ngắn gọn, sư phạm",
            ],
            "revision_priority": [
                "Nếu lệch chủ đề, kéo câu hỏi về đúng YCCĐ",
                "Nếu thiếu dữ liệu lớp/chủ đề/bài học, giữ plan tối thiểu nhưng ổn định",
                "Nếu số lượng câu thay đổi, giữ cấu trúc đầu ra không đổi",
            ],
            "risk_points": [
                "Dễ lệch lớp nếu nội dung quá khó hoặc quá dài",
                "Dễ thiếu bám YCCĐ nếu input giáo viên quá chung chung",
                "Dễ làm hỏng generation nếu plan đổi schema thất thường",
            ],
            "plan_notes": [
                f"Sinh {num_questions} câu hỏi theo yêu cầu giáo viên",
                "Giữ output ổn định để generation agent đọc tiếp",
            ],
            "checklist": [
                "Kiểm tra đủ ngữ cảnh curriculum",
                "Kiểm tra độ phù hợp mức độ nhận thức",
                "Kiểm tra output dùng được ngay cho sinh câu hỏi",
            ],
            "planning_summary": (
                f"Plan cho {topic_focus['subject'] or 'môn học'} - "
                f"lớp {topic_focus['grade'] or 'N/A'} - "
                f"{topic_focus['topic'] or 'chủ đề'}."
            ),
            "yccd_item": {
                "lop": yccd_item.get("lop", payload.get("lop", "")),
                "chu_de": yccd_item.get("chu_de", payload.get("topic", "")),
                "bai": yccd_item.get("bai", payload.get("lesson", "")),
                "yccd": yccd_item.get("yccd", payload.get("yccd", "")),
            },
        }

        metadata = {
            "grade_band": grade_band,
            "difficulty_hint": difficulty["level"],
            "mode": "heuristic",
            "num_questions": num_questions,
        }
        return heuristic_plan, issues, metadata

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = PlannerAgent._deep_merge(merged[key], value)
            elif isinstance(value, list) and value:
                merged[key] = list(value)
            elif value is not None:
                merged[key] = value
        return merged

    def _llm_enrich(self, payload: dict[str, Any], heuristic_plan: dict[str, Any]) -> dict[str, Any] | None:
        if not self.llm_client:
            return None
        timeout = self._timeout_seconds()
        try:
            llm_plan = call_with_timeout(
                lambda: self.llm_client.chat_json(
                    PLANNER_SYSTEM_PROMPT,
                    build_planner_prompt(payload, heuristic_plan),
                    model=getattr(self.llm_client, "planner_model_name", "gpt-4o"),
                    timeout=timeout,
                ),
                timeout=timeout,
                fallback=None,
            )
        except Exception:
            return None
        if not isinstance(llm_plan, dict):
            return None
        return llm_plan

    @staticmethod
    def _timeout_seconds() -> int:
        raw_timeout = getenv("AI_EXAM_LLM_TIMEOUT_SECONDS", "20").strip()
        try:
            return max(5, int(raw_timeout))
        except ValueError:
            return 20

    def _normalize_plan(self, payload: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(plan)

        topic_focus = dict(normalized.get("topic_focus") or {})
        curriculum_context = dict(normalized.get("curriculum_context") or {})
        if curriculum_context and not topic_focus:
            topic_focus = {
                "subject": curriculum_context.get("subject", ""),
                "grade": curriculum_context.get("grade", ""),
                "topic": curriculum_context.get("topic", ""),
                "lesson": curriculum_context.get("lesson", ""),
                "yccd": curriculum_context.get("yccd", ""),
                "focus_terms": normalized.get("focus_terms") or [],
            }
        normalized["topic_focus"] = topic_focus

        difficulty = dict(normalized.get("difficulty") or {})
        if not difficulty:
            difficulty = {
                "requested": normalized.get("muc_do", ""),
                "level": normalized.get("difficulty_hint", "thong_hieu"),
                "label": normalized.get("muc_do", "Thông hiểu"),
                "intensity": "medium",
                "grade_band": curriculum_context.get("grade_band", ""),
            }
        normalized["difficulty"] = difficulty

        question_types = list(normalized.get("question_types") or [])
        if not question_types:
            generation_constraints = dict(normalized.get("generation_constraints") or {})
            question_type = generation_constraints.get("question_type") or "multiple_choice"
            question_types = [question_type]
            normalized["question_types"] = question_types

        constraints = dict(normalized.get("constraints") or {})
        generation_constraints = dict(normalized.get("generation_constraints") or {})
        constraints.setdefault("language", generation_constraints.get("language", _DEFAULT_LANGUAGE))
        constraints.setdefault("num_questions", generation_constraints.get("num_questions", 1))
        constraints.setdefault("option_count", generation_constraints.get("option_count", 4))
        constraints.setdefault("must_align_with_yccd", True)
        constraints.setdefault("must_match_curriculum_context", True)
        constraints.setdefault("must_match_difficulty", True)
        constraints.setdefault("must_include_answer", True)
        constraints.setdefault("must_include_explanation", True)
        constraints.setdefault("answer_format", "A/B/C/D")
        normalized["constraints"] = constraints

        generation_constraints.setdefault("question_types", question_types)
        generation_constraints.setdefault("question_type", question_types[0])
        generation_constraints.setdefault("option_count", constraints.get("option_count", 4))
        generation_constraints.setdefault("language", constraints.get("language", _DEFAULT_LANGUAGE))
        generation_constraints.setdefault("difficulty_hint", difficulty.get("level", "thong_hieu"))
        generation_constraints.setdefault("must_include_answer", True)
        generation_constraints.setdefault("must_include_explanation", True)
        generation_constraints.setdefault("num_questions", constraints.get("num_questions", 1))
        normalized["generation_constraints"] = generation_constraints

        strategy = dict(normalized.get("strategy") or {})
        strategy.setdefault("target_skill", difficulty.get("label", "Thông hiểu"))
        strategy.setdefault("question_style", "ngắn gọn, rõ ràng, bám yêu cầu cần đạt")
        strategy.setdefault("scaffold_level", "high" if difficulty.get("intensity") in {"low", "medium"} else "medium")
        normalized["strategy"] = strategy

        quality_targets = list(normalized.get("quality_targets") or [])
        if not quality_targets:
            quality_targets = [
                "Bám sát YCCĐ và ngữ cảnh curriculum",
                "Phương án/đáp án rõ ràng, dùng được ngay",
                "Lời giải ngắn gọn, sư phạm",
            ]
        normalized["quality_targets"] = quality_targets

        revision_priority = list(normalized.get("revision_priority") or [])
        if not revision_priority:
            revision_priority = [
                "Nếu lệch chủ đề, kéo câu hỏi về đúng YCCĐ",
                "Nếu thiếu dữ liệu lớp/chủ đề/bài học, giữ plan tối thiểu nhưng ổn định",
                "Nếu số lượng câu thay đổi, giữ cấu trúc đầu ra không đổi",
            ]
        normalized["revision_priority"] = revision_priority

        focus_terms = list(normalized.get("focus_terms") or [])
        if not focus_terms and topic_focus.get("yccd"):
            focus_terms = [term for term in topic_focus["yccd"].split() if len(term) >= 3][:8]
        normalized["focus_terms"] = focus_terms

        plan_notes = list(normalized.get("plan_notes") or [])
        if not plan_notes:
            plan_notes = ["Giữ output ổn định để generation agent đọc tiếp"]
        normalized["plan_notes"] = plan_notes

        risk_points = list(normalized.get("risk_points") or [])
        if not risk_points:
            risk_points = [
                "Dễ lệch lớp nếu nội dung quá khó hoặc quá dài",
                "Dễ thiếu bám YCCĐ nếu input giáo viên quá chung chung",
                "Dễ làm hỏng generation nếu plan đổi schema thất thường",
            ]
        normalized["risk_points"] = risk_points

        checklist = list(normalized.get("checklist") or [])
        if not checklist:
            checklist = [
                "Kiểm tra đủ ngữ cảnh curriculum",
                "Kiểm tra độ phù hợp mức độ nhận thức",
                "Kiểm tra output dùng được ngay cho sinh câu hỏi",
            ]
        normalized["checklist"] = checklist

        normalized.setdefault(
            "planning_summary",
            f"Plan cho {topic_focus.get('subject') or 'môn học'} - lớp {topic_focus.get('grade') or 'N/A'} - {topic_focus.get('topic') or 'chủ đề'}.",
        )
        normalized.setdefault(
            "input_snapshot",
            {
                "has_lop": bool(topic_focus.get("grade")),
                "has_chu_de": bool(topic_focus.get("topic")),
                "has_bai": bool(topic_focus.get("lesson")),
                "has_yccd": bool(topic_focus.get("yccd")),
            },
        )
        normalized.setdefault("muc_do", difficulty.get("requested", "Thông hiểu"))
        normalized.setdefault(
            "yccd_item",
            {
                "lop": plan.get("yccd_item", {}).get("lop", ""),
                "chu_de": plan.get("yccd_item", {}).get("chu_de", ""),
                "bai": plan.get("yccd_item", {}).get("bai", ""),
                "yccd": plan.get("yccd_item", {}).get("yccd", ""),
            },
        )
        return normalized

    def execute(self, input_data):
        """
        Build a normalized generation plan from the raw request.
        """
        payload = dict(input_data or {})
        heuristic_plan, issues, metadata = self._build_heuristic_plan(payload)
        llm_plan = self._llm_enrich(payload, heuristic_plan)
        plan = self._deep_merge(heuristic_plan, llm_plan or {})
        plan = self._normalize_plan(payload, plan)

        if llm_plan:
            plan["planning_report"] = {
                "mode": "llm+heuristic",
                "source": "LLM planner",
                "llm_keys": sorted(list(llm_plan.keys())),
            }
            metadata = {**metadata, "mode": "llm+heuristic", "llm_enabled": True}
        else:
            plan["planning_report"] = {
                "mode": "heuristic",
                "source": "heuristic planner",
                "llm_keys": [],
            }
            metadata = {**metadata, "llm_enabled": False}

        if issues:
            return self.fail(
                issues,
                output=plan,
                confidence=0.6,
                next_action="review_input",
                metadata={**metadata, "agent": self.name},
            )

        confidence = 1.0 if llm_plan else 0.95
        return self.ok(plan, confidence=confidence, metadata={**metadata, "agent": self.name})
