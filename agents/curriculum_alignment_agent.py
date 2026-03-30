from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv
from typing import Any
import re
import unicodedata

from agents.base_agent import BaseAgent
from clients.base_llm_client import BaseLLMClient
from orchestrator.agent_result import AgentResult
from services.llm_utils import call_with_timeout
from prompts.alignment_prompts import ALIGNMENT_SYSTEM_PROMPT, build_alignment_prompt

_STOPWORDS = {
    "va",
    "và",
    "la",
    "là",
    "cua",
    "của",
    "trong",
    "tren",
    "trên",
    "duoi",
    "dưới",
    "mot",
    "một",
    "cac",
    "các",
    "nhung",
    "những",
    "duoc",
    "được",
    "cho",
    "the",
    "this",
    "that",
    "voi",
    "với",
    "va",
    "ve",
    "về",
    "khi",
    "de",
    "để",
}

_REASONING_MARKERS = {
    "vi",
    "vì",
    "neu",
    "nếu",
    "suy",
    "luan",
    "luận",
    "phan",
    "phân",
    "tich",
    "tích",
    "giai",
    "giải",
    "tinh",
    "tính",
}

_QUESTION_TYPE_MULTIPLE_CHOICE = "multiple_choice"
_PASS_THRESHOLD = 0.7


@dataclass(slots=True)
class AlignmentAssessment:
    score: float
    aligned: bool = False
    matched_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    matched_points: list[str] = field(default_factory=list)
    missing_points: list[str] = field(default_factory=list)
    off_topic_points: list[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""
    matched_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    clarity_score: float = 0.0
    structure_score: float = 0.0
    difficulty_score: float = 0.0
    curriculum_context: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        report = {
            "score": round(self.score, 3),
            "aligned": bool(self.aligned),
            "matched_fields": list(self.matched_fields),
            "missing_fields": list(self.missing_fields),
            "matched_points": list(self.matched_points),
            "missing_points": list(self.missing_points),
            "off_topic_points": list(self.off_topic_points),
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
            "coverage_ratio": round(self.coverage_ratio, 3),
            "clarity_score": round(self.clarity_score, 3),
            "structure_score": round(self.structure_score, 3),
            "difficulty_score": round(self.difficulty_score, 3),
            "curriculum_context": dict(self.curriculum_context),
            "recommendations": list(self.recommendations),
            "quality_flags": list(self.quality_flags),
            "matched_terms": list(self.matched_terms),
            "missing_terms": list(self.missing_terms),
        }
        report["compliance_score"] = report["score"]
        return report


class CurriculumAlignmentAgent(BaseAgent):
    def __init__(self, schema, llm_client: BaseLLMClient | None = None):
        super().__init__()
        self.schema = schema
        self.llm_client = llm_client

    @staticmethod
    def _coerce_text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text or "")
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return re.sub(r"[^\w]+", " ", ascii_text.lower()).strip()

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        tokens = [token for token in cls._normalize_text(text).split() if token]
        return tokens

    @classmethod
    def _significant_terms(cls, text: str, *, limit: int = 8) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for token in cls._tokenize(text):
            if len(token) < 3 or token in _STOPWORDS or token in seen:
                continue
            seen.add(token)
            terms.append(token)
            if len(terms) >= limit:
                break
        return terms

    @staticmethod
    def _merge_unique(*groups: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for item in group:
                value = str(item).strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                merged.append(value)
        return merged

    @classmethod
    def _contains_normalized(cls, haystack: str, needle: str) -> bool:
        normalized_haystack = cls._normalize_text(haystack)
        normalized_needle = cls._normalize_text(needle)
        if not normalized_needle:
            return True
        if not normalized_haystack:
            return False
        return normalized_needle in normalized_haystack

    @classmethod
    def _contains_grade_reference(cls, haystack: str, grade: int | None) -> bool:
        if grade is None:
            return True
        normalized_haystack = cls._normalize_text(haystack)
        if not normalized_haystack:
            return False
        patterns = {
            f"lop {grade}",
            f"lop{grade}",
            f"lớp {grade}",
            f"lớp{grade}",
            f"grade {grade}",
            f"class {grade}",
            str(grade),
        }
        return any(pattern in normalized_haystack for pattern in patterns)

    @staticmethod
    def _subject_aliases(subject: str) -> tuple[str, ...]:
        normalized = subject.strip().lower()
        if not normalized:
            return ()
        aliases = {normalized, normalized.replace(" ", "")}
        if "toan" in aliases or "toan" in normalized:
            aliases.update({"mon toan", "toan", "montoan"})
        if "tin hoc" in normalized or "tinhoc" in normalized.replace(" ", ""):
            aliases.update({"mon tin hoc", "tin hoc", "tinhoc", "montinhoc"})
        if normalized in {"van", "ngu van", "nguvan"} or "ngu van" in normalized:
            aliases.update({"mon van", "ngu van", "van", "nguvan"})
        return tuple(alias for alias in aliases if alias)

    @staticmethod
    def _difficulty_keywords(difficulty: str) -> tuple[str, ...]:
        normalized = difficulty.strip().lower()
        if not normalized:
            return ()
        if "vận dụng cao" in normalized or "van dung cao" in normalized:
            return ("van dung cao", "advanced", "hard")
        if "vận dụng" in normalized or "van dung" in normalized:
            return ("van dung", "application", "applied")
        if "thông hiểu" in normalized or "thong hieu" in normalized:
            return ("thong hieu", "understanding", "hieu")
        if "nhận biết" in normalized or "nhan biet" in normalized:
            return ("nhan biet", "recall", "basic")
        return (normalized,)

    def _build_strict_assessment(self, payload: dict[str, Any]) -> AlignmentAssessment:
        item = dict(payload.get("yccd_item") or {})
        plan = dict(payload.get("plan") or {})
        curriculum_context = dict(payload.get("curriculum_context") or plan.get("curriculum_context") or {})

        expected_subject = self._coerce_text(curriculum_context.get("subject") or item.get("mon") or item.get("subject") or payload.get("subject"))
        expected_grade = self._coerce_int(curriculum_context.get("grade") or item.get("lop") or payload.get("lop"))
        expected_topic = self._coerce_text(curriculum_context.get("topic") or item.get("chu_de") or payload.get("topic"))
        expected_lesson = self._coerce_text(curriculum_context.get("lesson") or item.get("bai") or payload.get("lesson"))
        expected_yccd = self._coerce_text(curriculum_context.get("yccd") or item.get("yccd") or payload.get("yccd"))
        expected_difficulty = self._coerce_text(curriculum_context.get("difficulty") or plan.get("difficulty", {}).get("requested") or payload.get("muc_do"))
        expected_question_type = self._normalize_text(
            curriculum_context.get("question_type")
            or plan.get("generation_constraints", {}).get("question_type")
            or payload.get("question_type")
            or "multiple_choice"
        )

        question = self._coerce_text(payload.get("question"))
        explanation = self._coerce_text(payload.get("explanation"))
        answer = self._coerce_text(payload.get("answer")).upper()
        options = [self._coerce_text(option) for option in (payload.get("options") or []) if self._coerce_text(option)]
        response_text = self._normalize_text(" ".join([question, explanation, answer, " ".join(options)]))

        matched_fields: list[str] = []
        missing_fields: list[str] = []
        matched_points: list[str] = []
        missing_points: list[str] = []
        off_topic_points: list[str] = []
        recommendations: list[str] = []
        quality_flags: list[str] = []

        if expected_subject:
            subject_aliases = self._subject_aliases(expected_subject)
            if any(alias in response_text for alias in subject_aliases):
                matched_fields.append("subject")
                matched_points.append("Matched subject.")
            else:
                subject_signals = [alias for alias in ("mon toan", "mon van", "mon tin hoc", "ngu van", "tin hoc", "toan") if alias in response_text]
                if subject_signals:
                    missing_fields.append("subject")
                    missing_points.append("Missing subject.")
                    off_topic_points.append("Field mismatch: subject.")
                else:
                    matched_fields.append("subject")
                    matched_points.append("Matched subject by structured context.")

        for field_name, expected_value in {"topic": expected_topic, "lesson": expected_lesson, "yccd": expected_yccd}.items():
            if expected_value and self._contains_normalized(response_text, expected_value):
                matched_fields.append(field_name)
                matched_points.append(f"Matched {field_name}.")
            else:
                missing_fields.append(field_name)
                missing_points.append(f"Missing {field_name}.")
                off_topic_points.append(f"Field mismatch: {field_name}.")

        if expected_grade is not None:
            if self._grade_conflict(expected_grade, response_text):
                missing_fields.append("grade")
                missing_points.append("Missing grade.")
                off_topic_points.append(f"Wrong grade: {expected_grade}.")
            else:
                matched_fields.append("grade")
                matched_points.append("Matched grade by structured context.")

        if expected_difficulty:
            difficulty_target = self._difficulty_target(expected_difficulty)
            grade_limit = self._grade_length_limit(expected_grade)
            reasoning_markers = sum(1 for marker in _REASONING_MARKERS if marker in self._normalize_text(question + " " + explanation))
            difficulty_score = 0.5
            if difficulty_target == "recall":
                difficulty_score = 1.0 if len(question) <= grade_limit and len(explanation) >= 10 else 0.7
            elif difficulty_target == "understanding":
                difficulty_score = 1.0 if len(explanation) >= 12 and len(question) <= grade_limit + 20 else 0.75
            elif difficulty_target == "application":
                difficulty_score = 1.0 if reasoning_markers >= 1 else 0.7
            elif difficulty_target == "advanced":
                difficulty_score = 1.0 if reasoning_markers >= 2 and len(explanation) >= 20 else 0.6
            if difficulty_score >= 0.75:
                matched_fields.append("difficulty")
                matched_points.append("Matched difficulty.")
            else:
                missing_fields.append("difficulty")
                missing_points.append("Missing difficulty alignment.")
                off_topic_points.append(f"Wrong difficulty: {expected_difficulty}.")

        question_type_ok = expected_question_type != _QUESTION_TYPE_MULTIPLE_CHOICE or (len(options) == 4 and answer in {"A", "B", "C", "D"})
        if question_type_ok:
            matched_fields.append("question_type")
            matched_points.append("Matched question type.")
        else:
            missing_fields.append("question_type")
            missing_points.append("Missing question type alignment.")
            off_topic_points.append("Wrong question type.")

        hard_mismatch = bool(missing_fields)
        score = 1.0
        if "subject" in missing_fields:
            score -= 0.30
        if "grade" in missing_fields:
            score -= 0.20
        if "topic" in missing_fields:
            score -= 0.25
        if "lesson" in missing_fields:
            score -= 0.25
        if "yccd" in missing_fields:
            score -= 0.25
        if "difficulty" in missing_fields:
            score -= 0.20
        if "question_type" in missing_fields:
            score -= 0.20

        question_length = len(question)
        if expected_grade is not None:
            grade_limit = self._grade_length_limit(expected_grade)
            if question_length > grade_limit:
                score -= 0.05
                off_topic_points.append("Question too long for grade.")
            elif question_length <= max(12, grade_limit // 2):
                score += 0.05

        score = max(0.0, min(1.0, score))
        if hard_mismatch:
            aligned = False
            score = min(score, 0.79)
        else:
            aligned = score >= _PASS_THRESHOLD and not off_topic_points

        if not question:
            missing_points.append("Missing question.")
        if not explanation:
            missing_points.append("Missing explanation.")
        if not options:
            missing_points.append("Missing options.")

        if "difficulty" in missing_fields:
            recommendations.append("Adjust output to the requested difficulty level.")
        if "topic" in missing_fields or "lesson" in missing_fields:
            recommendations.append("Re-anchor the item to the requested topic and lesson.")
        if "subject" in missing_fields:
            recommendations.append("Restore the requested subject explicitly.")
        if "yccd" in missing_fields:
            recommendations.append("Bring the output back to the target YCCĐ.")
        if "question_type" in missing_fields:
            recommendations.append("Use the requested question type and 4 options.")

        quality_flags = self._merge_unique(off_topic_points, missing_points)
        summary = "Strict structured alignment check."

        confidence = max(0.3, min(1.0, score if aligned else score * 0.9))
        return AlignmentAssessment(
            score=round(score, 3),
            aligned=aligned,
            matched_fields=self._merge_unique(matched_fields),
            missing_fields=self._merge_unique(missing_fields),
            matched_points=self._merge_unique(matched_points),
            missing_points=self._merge_unique(missing_points),
            off_topic_points=self._merge_unique(off_topic_points),
            confidence=round(confidence, 3),
            summary=summary,
            matched_terms=[],
            missing_terms=[],
            coverage_ratio=round(score, 3),
            clarity_score=1.0 if question and explanation else 0.0,
            structure_score=1.0 if question and explanation and options else 0.0,
            difficulty_score=round(1.0 - (0.2 if "difficulty" in missing_fields else 0.0), 3),
            curriculum_context={
                "subject": expected_subject,
                "grade": expected_grade,
                "topic": expected_topic,
                "lesson": expected_lesson,
                "yccd": expected_yccd,
                "difficulty": expected_difficulty,
                "question_type": expected_question_type,
            },
            recommendations=self._merge_unique(recommendations),
            quality_flags=self._merge_unique(quality_flags),
        )

    def _extract_curriculum_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = dict(payload.get("yccd_item") or {})
        plan = dict(payload.get("plan") or {})

        context: dict[str, Any] = {}
        for source in (payload.get("curriculum_context"), plan.get("curriculum_context"), item.get("curriculum_context")):
            if isinstance(source, dict):
                context.update(source)

        generation_constraints = plan.get("generation_constraints")
        if not isinstance(generation_constraints, dict):
            generation_constraints = {}

        subject = context.get("subject") or item.get("subject") or item.get("mon") or payload.get("subject")
        grade = context.get("grade") or item.get("lop") or payload.get("lop")
        topic = context.get("topic") or item.get("chu_de") or payload.get("topic")
        lesson = context.get("lesson") or item.get("bai") or payload.get("lesson")
        yccd = context.get("yccd") or item.get("yccd") or payload.get("yccd")
        difficulty = context.get("difficulty") or payload.get("muc_do") or plan.get("muc_do")
        question_type = context.get("question_type") or generation_constraints.get("question_type") or payload.get("question_type")
        num_questions = context.get("num_questions") or payload.get("num_questions") or generation_constraints.get("question_count")
        expected_options = generation_constraints.get("option_count") or payload.get("expected_options")

        resolved_context = {
            "subject": self._coerce_text(subject),
            "grade": self._coerce_int(grade),
            "topic": self._coerce_text(topic),
            "lesson": self._coerce_text(lesson),
            "yccd": self._coerce_text(yccd),
            "difficulty": self._coerce_text(difficulty),
            "question_type": self._coerce_text(question_type),
            "num_questions": self._coerce_int(num_questions),
            "expected_options": self._coerce_int(expected_options) or 4,
            "must_include_answer": bool(generation_constraints.get("must_include_answer", False)),
            "must_include_explanation": bool(generation_constraints.get("must_include_explanation", False)),
            "quality_targets": list(plan.get("quality_targets") or []),
            "focus_terms": list(plan.get("focus_terms") or []),
            "plan_notes": list(plan.get("plan_notes") or []),
        }
        resolved_context["grade_band"] = self._grade_band(resolved_context["grade"])
        return resolved_context

    @staticmethod
    def _grade_band(grade: int | None) -> str:
        if grade is None:
            return "không xác định"
        if grade <= 2:
            return "đầu tiểu học"
        if grade <= 4:
            return "giữa tiểu học"
        return "cuối tiểu học"

    @classmethod
    def _grade_mentions(cls, text: str) -> set[int]:
        normalized = cls._normalize_text(text)
        return {int(match) for match in re.findall(r"\b(?:lop|lớp)\s*(\d+)\b", normalized)}

    @classmethod
    def _grade_conflict(cls, expected_grade: int | None, response_text: str) -> bool:
        if expected_grade is None:
            return False
        mentions = cls._grade_mentions(response_text)
        return any(mention != expected_grade for mention in mentions)

    @staticmethod
    def _is_strict_mode(payload: dict[str, Any]) -> bool:
        return bool(payload.get("strict_alignment"))

    @staticmethod
    def _has_required_output(payload: dict[str, Any]) -> bool:
        question = str(payload.get("question") or "").strip()
        explanation = str(payload.get("explanation") or "").strip()
        answer = str(payload.get("answer") or "").strip().upper()
        options = payload.get("options") or []
        has_valid_answer = answer in {"A", "B", "C", "D"}
        has_question = bool(question)
        has_explanation = bool(explanation)
        has_options = isinstance(options, list) and (not options or len(options) >= 4)
        return has_question and has_explanation and has_valid_answer and has_options

    @staticmethod
    def _grade_length_limit(grade: int | None) -> int:
        if grade is None:
            return 240
        if grade <= 2:
            return 180
        if grade <= 4:
            return 220
        return 260

    @staticmethod
    def _difficulty_target(difficulty: str) -> str:
        normalized = difficulty.strip().lower()
        if "vận dụng cao" in normalized or "van dung cao" in normalized:
            return "advanced"
        if "vận dụng" in normalized or "van dung" in normalized:
            return "application"
        if "thông hiểu" in normalized or "thong hieu" in normalized:
            return "understanding"
        if "nhận biết" in normalized or "nhan biet" in normalized:
            return "recall"
        return "general"

    def _build_response_text(self, payload: dict[str, Any]) -> str:
        question = self._coerce_text(payload.get("question"))
        explanation = self._coerce_text(payload.get("explanation"))
        answer = self._coerce_text(payload.get("answer"))
        options = payload.get("options") or []
        option_text = " ".join(self._coerce_text(option) for option in options)
        return " ".join(part for part in [question, explanation, answer, option_text] if part).strip()

    def _field_overlap(self, expected_text: str, response_text: str) -> tuple[float, list[str], list[str]]:
        expected_terms = self._significant_terms(expected_text, limit=10)
        if not expected_terms:
            return 1.0, [], []

        response_tokens = set(self._tokenize(response_text))
        matched_terms = [term for term in expected_terms if term in response_tokens or term in self._normalize_text(response_text)]
        missing_terms = [term for term in expected_terms if term not in matched_terms]
        ratio = len(matched_terms) / len(expected_terms)
        return ratio, matched_terms, missing_terms

    def _strict_alignment_review(
        self,
        *,
        context: dict[str, Any],
        response_text: str,
        question_length: int,
        grade_limit: int,
        difficulty_score: float,
        structure_score: float,
    ) -> dict[str, Any]:
        subject_ratio, _, _ = self._field_overlap(context["subject"], response_text)
        topic_ratio, _, _ = self._field_overlap(context["topic"], response_text)
        lesson_ratio, _, _ = self._field_overlap(context["lesson"], response_text)
        yccd_ratio, _, _ = self._field_overlap(context["yccd"], response_text)
        grade_conflict = self._grade_conflict(context["grade"], response_text)

        score = 1.0
        issues: list[str] = []
        off_topic_points: list[str] = []

        if context["subject"] and subject_ratio < 0.4:
            score -= 0.15
            issues.append(f"subject_mismatch:{context['subject']}")
            off_topic_points.append(f"Nội dung lệch môn {context['subject']}.")

        if context["topic"] and topic_ratio < 0.6:
            score -= 0.25
            issues.append(f"topic_mismatch:{context['topic']}")
            off_topic_points.append(f"Nội dung lệch chủ đề {context['topic']}.")

        if context["lesson"] and lesson_ratio < 0.55:
            score -= 0.25
            issues.append(f"lesson_mismatch:{context['lesson']}")
            off_topic_points.append(f"Nội dung lệch bài học {context['lesson']}.")

        if context["yccd"] and yccd_ratio < 0.6:
            score -= 0.25
            issues.append("yccd_mismatch")
            off_topic_points.append("Nội dung chưa bám sát YCCĐ.")

        if grade_conflict:
            score -= 0.15
            issues.append(f"grade_conflict:{context['grade']}")
            off_topic_points.append(f"Có dấu hiệu sai lớp so với lớp {context['grade']}.")

        if context["grade"] is not None and question_length > grade_limit:
            score -= 0.05
            issues.append("grade_length_mismatch")

        if context["difficulty"] and difficulty_score < 0.75:
            score -= 0.2
            issues.append(f"difficulty_mismatch:{context['difficulty']}")
            off_topic_points.append(f"Độ khó chưa khớp yêu cầu '{context['difficulty']}'.")

        if context["question_type"] == _QUESTION_TYPE_MULTIPLE_CHOICE and structure_score < 1.0:
            score -= 0.15
            issues.append("question_type_mismatch")
            off_topic_points.append("Định dạng câu hỏi chưa khớp yêu cầu trắc nghiệm nhiều lựa chọn.")

        if issues:
            score = min(score, max(0.25, 0.55 - 0.05 * len(issues)))

        return {
            "score": max(0.0, round(score, 3)),
            "issues": issues,
            "off_topic_points": off_topic_points,
        }

    def _build_heuristic_assessment(self, payload: dict[str, Any]) -> AlignmentAssessment:
        item = dict(payload.get("yccd_item") or {})
        response_text = self._build_response_text(payload)
        question = self._coerce_text(payload.get("question"))
        explanation = self._coerce_text(payload.get("explanation"))
        answer = self._coerce_text(payload.get("answer")).upper()
        options = [self._coerce_text(option) for option in (payload.get("options") or []) if self._coerce_text(option)]
        context = self._extract_curriculum_context(payload)

        matched_points: list[str] = []
        missing_points: list[str] = []
        off_topic_points: list[str] = []
        recommendations: list[str] = []
        quality_flags: list[str] = []
        matched_terms: list[str] = []
        missing_terms: list[str] = []

        context_fields = [
            context["subject"],
            str(context["grade"]) if context["grade"] is not None else "",
            context["topic"],
            context["lesson"],
            context["yccd"],
        ]
        context_text = " ".join(field for field in context_fields if field).strip()
        context_quality_score = sum(1 for field in context_fields if field) / len(context_fields)

        subject_ratio, subject_matched, subject_missing = self._field_overlap(context["subject"], response_text)
        topic_ratio, topic_matched, topic_missing = self._field_overlap(context["topic"], response_text)
        lesson_ratio, lesson_matched, lesson_missing = self._field_overlap(context["lesson"], response_text)
        yccd_ratio, yccd_matched, yccd_missing = self._field_overlap(context["yccd"], response_text)
        grade_conflict = self._grade_conflict(context["grade"], response_text)
        curriculum_coverage = round(
            0.15 * subject_ratio + 0.20 * topic_ratio + 0.20 * lesson_ratio + 0.30 * yccd_ratio + 0.15 * (1.0 if not grade_conflict else 0.0),
            3,
        )
        matched_terms.extend(self._merge_unique(subject_matched, topic_matched, lesson_matched, yccd_matched))
        missing_terms.extend(self._merge_unique(subject_missing, topic_missing, lesson_missing, yccd_missing))

        question_length = len(question)
        grade_limit = self._grade_length_limit(context["grade"])
        length_fit = 1.0 if question_length <= grade_limit else max(0.3, grade_limit / max(question_length, 1))

        structure_checks = 0
        structure_total = 0

        structure_total += 1
        if question:
            structure_checks += 1
            matched_points.append("Có câu hỏi đầu ra.")
        else:
            missing_points.append("Thiếu câu hỏi đầu ra.")

        structure_total += 1
        if explanation and len(explanation) >= 10:
            structure_checks += 1
            matched_points.append("Có lời giải thích đủ ngữ cảnh sư phạm.")
        else:
            missing_points.append("Lời giải thích còn thiếu hoặc quá ngắn.")

        structure_total += 1
        answer_valid = answer in {"A", "B", "C", "D"}
        if answer_valid:
            structure_checks += 1
            matched_points.append("Đáp án ở định dạng A/B/C/D hợp lệ.")
        else:
            missing_points.append("Đáp án chưa ở định dạng A/B/C/D.")

        expected_type = self._normalize_text(context["question_type"])
        has_mc_signal = bool(options or answer or context["must_include_answer"] or context["must_include_explanation"])
        if expected_type == _QUESTION_TYPE_MULTIPLE_CHOICE or has_mc_signal:
            structure_total += 1
            if len(options) == 4:
                structure_checks += 1
                matched_points.append("Đúng định dạng trắc nghiệm 4 lựa chọn.")
            elif has_mc_signal:
                missing_points.append("Thiếu đúng 4 lựa chọn cho câu trắc nghiệm.")
                off_topic_points.append("Định dạng câu hỏi chưa khớp yêu cầu trắc nghiệm nhiều lựa chọn.")
        elif options:
            structure_total += 1
            structure_checks += 1
            matched_points.append("Định dạng câu hỏi có lựa chọn trả lời.")

        structure_score = structure_checks / structure_total if structure_total else 0.0

        if context["topic"]:
            topic_ratio, topic_matched, topic_missing = self._field_overlap(context["topic"], response_text)
            if topic_ratio >= 0.35:
                matched_points.append(f"Bám chủ đề '{context['topic']}'.")
            else:
                missing_points.append(f"Chưa bám đủ chủ đề '{context['topic']}'.")
                off_topic_points.append(f"Nội dung lệch khỏi chủ đề '{context['topic']}'.")
            matched_terms.extend(topic_matched)
            missing_terms.extend(topic_missing)
        else:
            matched_points.append("Chủ đề curriculum không được cung cấp rõ.")

        if context["lesson"]:
            lesson_ratio, lesson_matched, lesson_missing = self._field_overlap(context["lesson"], response_text)
            if lesson_ratio >= 0.25:
                matched_points.append(f"Bám bài học '{context['lesson']}'.")
            else:
                missing_points.append(f"Chưa thể hiện rõ bài học '{context['lesson']}'.")
                off_topic_points.append(f"Nội dung lệch khỏi bài học '{context['lesson']}'.")
            matched_terms.extend(lesson_matched)
            missing_terms.extend(lesson_missing)
        else:
            matched_points.append("Bài học curriculum không được cung cấp rõ.")

        if context["yccd"]:
            yccd_ratio, yccd_matched, yccd_missing = self._field_overlap(context["yccd"], response_text)
            if yccd_ratio >= 0.5:
                matched_points.append("Bám sát YCCĐ đầu vào.")
            elif yccd_ratio >= 0.3:
                matched_points.append("Có dấu hiệu bám YCCĐ nhưng cần siết chặt hơn.")
                missing_points.append("Mức bám YCCĐ chưa đủ sâu.")
            else:
                missing_points.append("Chưa bám sát YCCĐ đầu vào.")
                off_topic_points.append("Nội dung lệch khỏi YCCĐ.")
            matched_terms.extend(yccd_matched)
            missing_terms.extend(yccd_missing)
        else:
            missing_points.append("Thiếu YCCĐ để đối chiếu curriculum.")

        difficulty_target = self._difficulty_target(context["difficulty"])
        reasoning_markers = sum(1 for marker in _REASONING_MARKERS if marker in self._normalize_text(question + " " + explanation))
        difficulty_score = 0.5
        if difficulty_target == "recall":
            difficulty_score = 1.0 if question_length <= grade_limit and len(explanation) >= 10 else 0.7
        elif difficulty_target == "understanding":
            difficulty_score = 1.0 if len(explanation) >= 12 and question_length <= grade_limit + 20 else 0.75
        elif difficulty_target == "application":
            difficulty_score = 1.0 if reasoning_markers >= 1 else 0.7
        elif difficulty_target == "advanced":
            difficulty_score = 1.0 if reasoning_markers >= 2 and len(explanation) >= 20 else 0.6

        if context["difficulty"]:
            if difficulty_score >= 0.75:
                matched_points.append(f"Phù hợp mức độ nhận thức '{context['difficulty']}'.")
            else:
                missing_points.append(f"Mức độ nhận thức '{context['difficulty']}' chưa khớp đầy đủ.")
                off_topic_points.append(f"Độ khó chưa khớp yêu cầu '{context['difficulty']}'.")

        if context["grade"] is not None:
            if question_length <= grade_limit:
                matched_points.append(f"Phù hợp độ dài cho lớp {context['grade']}.")
            else:
                missing_points.append(f"Câu hỏi dài hơn ngưỡng khuyến nghị cho lớp {context['grade']}.")
                off_topic_points.append(f"Độ dài chưa phù hợp lớp {context['grade']}.")

        content_coverage_score = curriculum_coverage
        if matched_terms:
            matched_points.append("Có các từ khóa curriculum trọng tâm xuất hiện trong đầu ra.")

        if context_quality_score < 1.0:
            recommendations.append("Bổ sung đủ lớp/chủ đề/bài/YCCĐ để đánh giá chính xác hơn.")

        if structure_score < 1.0:
            recommendations.append("Chuẩn hóa lại cấu trúc câu hỏi, đáp án và lời giải.")

        if curriculum_coverage < 0.35:
            recommendations.append("Siết lại nội dung để bám sát YCCĐ và chủ đề.")

        score = round(
            max(
                0.0,
                min(
                    1.0,
                    (
                        0.45 * content_coverage_score
                        + 0.20 * structure_score
                        + 0.15 * difficulty_score
                        + 0.10 * context_quality_score
                        + 0.10 * length_fit
                    ),
                ),
            ),
            3,
        )

        confidence = round(
            max(
                0.3,
                min(
                    1.0,
                    0.4 * score
                    + 0.25 * content_coverage_score
                    + 0.15 * structure_score
                    + 0.10 * context_quality_score
                    + 0.10 * difficulty_score,
                ),
            ),
            3,
        )

        strict_review = self._strict_alignment_review(
            context=context,
            response_text=response_text,
            question_length=question_length,
            grade_limit=grade_limit,
            difficulty_score=difficulty_score,
            structure_score=structure_score,
        )
        score = round(min(score, strict_review["score"]), 3)
        confidence = round(min(confidence, max(0.3, strict_review["score"])), 3)
        missing_points.extend(strict_review["issues"])
        off_topic_points.extend(strict_review["off_topic_points"])

        summary = (
            f"Đánh giá alignment theo curriculum context: lớp {context['grade'] or 'không xác định'}, "
            f"chủ đề '{context['topic'] or 'không xác định'}', bài '{context['lesson'] or 'không xác định'}'."
        )

        quality_flags = self._merge_unique(off_topic_points, missing_points)

        return AlignmentAssessment(
            score=score,
            matched_points=self._merge_unique(matched_points),
            missing_points=self._merge_unique(missing_points),
            off_topic_points=self._merge_unique(off_topic_points),
            confidence=confidence,
            summary=summary,
            matched_terms=self._merge_unique(matched_terms),
            missing_terms=self._merge_unique(missing_terms),
            coverage_ratio=content_coverage_score,
            clarity_score=round(structure_score, 3),
            structure_score=round(structure_score, 3),
            difficulty_score=round(difficulty_score, 3),
            curriculum_context=context,
            recommendations=self._merge_unique(recommendations),
            quality_flags=self._merge_unique(quality_flags),
        )

    def _normalize_llm_report(self, llm_report: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(llm_report)
        normalized.setdefault("score", normalized.get("coverage_ratio", 0.0))
        normalized.setdefault("confidence", normalized.get("score", 0.0))
        normalized.setdefault("matched_points", normalized.get("matched_terms") or [])
        normalized.setdefault("missing_points", normalized.get("missing_terms") or [])
        normalized.setdefault("off_topic_points", normalized.get("quality_flags") or [])
        normalized.setdefault("summary", "LLM review complete")
        return normalized

    def _merge_assessments(self, heuristic: AlignmentAssessment, llm_report: dict[str, Any] | None) -> AlignmentAssessment:
        if not llm_report:
            return heuristic

        normalized_llm = self._normalize_llm_report(llm_report)
        merged_score = max(heuristic.score, float(normalized_llm.get("score", 0.0) or 0.0))
        merged_confidence = max(heuristic.confidence, float(normalized_llm.get("confidence", 0.0) or 0.0))

        heuristic.score = round(merged_score, 3)
        heuristic.confidence = round(merged_confidence, 3)
        heuristic.matched_points = self._merge_unique(
            heuristic.matched_points,
            [str(item) for item in normalized_llm.get("matched_points") or []],
        )
        heuristic.missing_points = self._merge_unique(
            heuristic.missing_points,
            [str(item) for item in normalized_llm.get("missing_points") or []],
        )
        heuristic.off_topic_points = self._merge_unique(
            heuristic.off_topic_points,
            [str(item) for item in normalized_llm.get("off_topic_points") or []],
        )
        heuristic.recommendations = self._merge_unique(
            heuristic.recommendations,
            [str(item) for item in normalized_llm.get("recommendations") or []],
        )
        heuristic.quality_flags = self._merge_unique(
            heuristic.quality_flags,
            [str(item) for item in normalized_llm.get("quality_flags") or []],
            heuristic.off_topic_points,
            heuristic.missing_points,
        )
        heuristic.summary = str(normalized_llm.get("summary") or heuristic.summary)
        heuristic.matched_terms = self._merge_unique(
            heuristic.matched_terms,
            [str(item) for item in normalized_llm.get("matched_terms") or []],
        )
        heuristic.missing_terms = self._merge_unique(
            heuristic.missing_terms,
            [str(item) for item in normalized_llm.get("missing_terms") or []],
        )
        heuristic.coverage_ratio = max(heuristic.coverage_ratio, float(normalized_llm.get("coverage_ratio", heuristic.coverage_ratio) or heuristic.coverage_ratio))
        heuristic.clarity_score = max(heuristic.clarity_score, float(normalized_llm.get("clarity_score", heuristic.clarity_score) or heuristic.clarity_score))
        return heuristic

    def _llm_assessment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.llm_client:
            return None

        timeout = self._timeout_seconds()
        try:
            response = call_with_timeout(
                lambda: self.llm_client.chat_json(
                    ALIGNMENT_SYSTEM_PROMPT,
                    build_alignment_prompt(payload),
                    model=getattr(self.llm_client, "alignment_model_name", "gpt-4o"),
                    timeout=timeout,
                ),
                timeout=timeout,
                fallback=None,
            )
        except Exception:
            return None

        if not isinstance(response, dict):
            return None

        return response

    @staticmethod
    def _timeout_seconds() -> int:
        raw_timeout = getenv("AI_EXAM_LLM_TIMEOUT_SECONDS", "20").strip()
        try:
            return max(5, int(raw_timeout))
        except ValueError:
            return 20

    def execute(self, lesson_plan) -> AgentResult:
        try:
            payload = dict(lesson_plan or {})
            strict_mode = self._is_strict_mode(payload)
            strict_assessment = self._build_strict_assessment(payload)
            heuristic = self._build_heuristic_assessment(payload)
            llm_report = self._llm_assessment(payload)
            strict_context = strict_mode or all(
                strict_assessment.curriculum_context.get(field) not in (None, "", [])
                for field in ("subject", "grade", "topic", "lesson", "yccd")
            )

            if strict_context:
                merged = strict_assessment
                if llm_report:
                    merged = self._merge_assessments(merged, llm_report)
            else:
                merged = self._merge_assessments(heuristic, llm_report)

            report = merged.to_dict()
            final_payload = dict(payload)
            final_payload.update(report)
            final_payload["alignment_report"] = report

            llm_pass = bool(
                isinstance(llm_report, dict)
                and bool(llm_report)
                and bool(self._normalize_llm_report(llm_report).get("pass", llm_report.get("pass", False)))
            )
            required_output = self._has_required_output(payload)
            if strict_context:
                status = "success" if report["aligned"] else "failed"
            else:
                if llm_pass:
                    status = "success"
                elif not strict_mode and required_output:
                    status = "success"
                else:
                    status = "success" if report["score"] >= _PASS_THRESHOLD and not report["off_topic_points"] else "failed"
            next_action = "continue" if status == "success" else "refine"
            issues = list(report["off_topic_points"] or report["missing_points"] or [])
            if not issues and status == "failed":
                issues = ["Alignment score below threshold"]

            if status == "success":
                return self.ok(
                    final_payload,
                    confidence=report["confidence"],
                    metadata={
                        "agent": self.name,
                        "mode": "llm+heuristic" if llm_report else "heuristic",
                        "score": report["score"],
                    },
                )

            return self.fail(
                issues,
                output=final_payload,
                confidence=report["confidence"],
                next_action=next_action,
                metadata={
                    "agent": self.name,
                    "mode": "llm+heuristic" if llm_report else "heuristic",
                    "score": report["score"],
                },
            )
        except Exception as exc:
            error_payload = dict(lesson_plan or {}) if isinstance(lesson_plan, dict) else {}
            error_payload["alignment_report"] = {
                "score": 0.0,
                "matched_points": [],
                "missing_points": [],
                "off_topic_points": [f"Alignment evaluation failed: {exc}"],
                "confidence": 0.0,
                "summary": f"Alignment evaluation failed: {type(exc).__name__}",
                "compliance_score": 0.0,
            }
            return self.fail(
                [f"Alignment evaluation failed: {exc}"],
                output=error_payload,
                next_action="refine",
                metadata={"agent": self.name, "error_type": type(exc).__name__},
            )
