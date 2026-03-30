from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv
from typing import Any
import re
import unicodedata

from agents.base_agent import BaseAgent
from clients.base_llm_client import BaseLLMClient
from prompts.critic_prompts import CRITIC_SYSTEM_PROMPT, build_critic_prompt
from services.llm_utils import call_with_timeout

_REQUIRED_OPTIONS = 4
_CRITERIA = ("alignment", "clarity", "accuracy", "distractor_quality", "explanation_quality")
_REASONING_MARKERS = {
    "vi",
    "neu",
    "suy",
    "luan",
    "phan",
    "tich",
    "giai",
    "tinh",
}
_STOPWORDS = {
    "va",
    "la",
    "cua",
    "trong",
    "tren",
    "duoi",
    "mot",
    "cac",
    "nhung",
    "duoc",
    "cho",
    "voi",
    "ve",
    "khi",
    "de",
    "pham",
}


@dataclass(slots=True)
class CriticAssessment:
    scores: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    confidence: float = 0.0
    recommended_action: str = "refine"
    summary: str = ""
    matched_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    revision_focus: list[str] = field(default_factory=list)
    minor_issue_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        report = {
            "scores": {key: round(float(value), 3) for key, value in self.scores.items()},
            "issues": list(self.issues),
            "confidence": round(self.confidence, 3),
            "recommended_action": self.recommended_action,
            "summary": self.summary,
            "matched_terms": list(self.matched_terms),
            "missing_terms": list(self.missing_terms),
            "quality_flags": list(self.quality_flags),
            "recommendations": list(self.recommendations),
            "revision_focus": list(self.revision_focus),
        }
        report["pass"] = report["recommended_action"] == "pass"
        return report


class CriticAgent(BaseAgent):
    def __init__(self, llm_client: BaseLLMClient | None = None):
        super().__init__()
        self.llm_client = llm_client

    @staticmethod
    def _coerce_text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @classmethod
    def _normalize_text(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return re.sub(r"[^\w]+", " ", ascii_text.lower()).strip()

    @classmethod
    def _tokens(cls, value: str) -> list[str]:
        return [token for token in cls._normalize_text(value).split() if token]

    @staticmethod
    def _contains_normalized(haystack: str, needle: str) -> bool:
        normalized_haystack = CriticAgent._normalize_text(haystack)
        normalized_needle = CriticAgent._normalize_text(needle)
        if not normalized_needle:
            return True
        if not normalized_haystack:
            return False
        return normalized_needle in normalized_haystack

    @classmethod
    def _significant_terms(cls, value: str, *, limit: int = 10) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for token in cls._tokens(value):
            if len(token) < 3 or token in seen or token in _STOPWORDS:
                continue
            seen.add(token)
            terms.append(token)
            if len(terms) >= limit:
                break
        return terms

    @staticmethod
    def _difficulty_target(difficulty: str) -> str:
        normalized = difficulty.strip().lower()
        if "van dung cao" in normalized or ("van dung" in normalized and "cao" in normalized):
            return "advanced"
        if "van dung" in normalized:
            return "application"
        if "thong hieu" in normalized:
            return "understanding"
        if "nhan biet" in normalized:
            return "recall"
        return "general"

    def _extract_expected_context(self, payload: dict[str, Any]) -> dict[str, str]:
        item = dict(payload.get("yccd_item") or {})
        return {
            "subject": self._coerce_text(item.get("mon") or payload.get("subject")),
            "grade": self._coerce_text(item.get("lop") or payload.get("grade")),
            "topic": self._coerce_text(item.get("chu_de") or payload.get("topic")),
            "lesson": self._coerce_text(item.get("bai") or payload.get("lesson")),
            "yccd": self._coerce_text(item.get("yccd") or payload.get("yccd")),
        }

    def _extract_difficulty(self, payload: dict[str, Any]) -> str:
        plan = payload.get("plan") or {}
        context = dict(plan.get("curriculum_context") or {})
        return self._coerce_text(
            context.get("difficulty") or payload.get("difficulty") or plan.get("difficulty", {}).get("requested") or ""
        )

    @staticmethod
    def _build_option_lookup(options: list[str]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for option in options:
            stripped = option.strip()
            if not stripped:
                continue
            letter = stripped[0].upper()
            if letter in {"A", "B", "C", "D"} and letter not in lookup:
                lookup[letter] = stripped
        return lookup

    @staticmethod
    def _difficulty_rank(level: str) -> int:
        mapping = {"recall": 0, "understanding": 1, "application": 2, "advanced": 3, "general": 1}
        return mapping.get(level, 1)

    def _estimate_actual_difficulty(self, question: str, explanation: str) -> str:
        combined = " ".join(part for part in (question, explanation) if part)
        tokens = self._tokens(combined)
        reasoning_hits = sum(1 for token in tokens if token in _REASONING_MARKERS)
        explanation_words = len(explanation.split())
        question_words = len(question.split())
        if reasoning_hits >= 3 or explanation_words >= 60 or question_words >= 50:
            return "advanced"
        if reasoning_hits >= 2 or explanation_words >= 40:
            return "application"
        if reasoning_hits >= 1 or explanation_words >= 25 or question_words >= 30:
            return "understanding"
        return "recall"

    @staticmethod
    def _option_similarity(a: str, b: str) -> float:
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / max(len(tokens_a), len(tokens_b))

    @classmethod
    def _is_placeholder_option(cls, option: str) -> bool:
        normalized = cls._normalize_text(option)
        return any(marker in normalized for marker in ("lua chon", "phuong an", "trung lap", "dap an dung", "dap an sai"))

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

    def _score_alignment(self, expected: dict[str, str], response_text: str) -> tuple[float, list[str], list[str]]:
        expected_terms = self._significant_terms(" ".join(expected.values()), limit=10)
        if not expected_terms:
            return 1.0, [], []

        response_tokens = set(self._tokens(response_text))
        matched = [term for term in expected_terms if term in response_tokens]
        missing = [term for term in expected_terms if term not in matched]
        score = len(matched) / len(expected_terms)
        for field, penalty in (("subject", 0.25), ("topic", 0.2), ("lesson", 0.2), ("yccd", 0.15)):
            expected_value = expected.get(field, "")
            if expected_value and not self._contains_normalized(response_text, expected_value):
                missing.append(field)
                score -= penalty
        score = max(0.0, score)
        return round(score, 3), matched, missing

    def _score_clarity(self, question: str, explanation: str, options: list[str], answer: str) -> tuple[float, list[str], list[str]]:
        issues: list[str] = []
        matched: list[str] = []
        score = 1.0

        if question:
            matched.append("Question exists")
        else:
            issues.append("Missing question text.")
            score -= 0.4

        if len(question) >= 10 and "?" in question:
            matched.append("Question is clear")
        else:
            issues.append("Question is too brief or lacks punctuation.")
            score -= 0.2

        unique_ratio = len(set(question.lower().split())) / max(len(question.split()), 1)
        if unique_ratio >= 0.5:
            matched.append("Question avoids repetition.")
        else:
            issues.append("Question repeats the same terms.")
            score -= 0.1

        if len(explanation) >= 12:
            matched.append("Explanation has enough length.")
        else:
            issues.append("Explanation is too short.")
            score -= 0.15

        if options and len(options) == _REQUIRED_OPTIONS:
            matched.append("Provides 4 choices.")
        else:
            issues.append("Does not include four answer choices.")
            score -= 0.2

        if answer in {"A", "B", "C", "D"}:
            matched.append("Answer key follows format.")
        else:
            issues.append("Answer key is not A/B/C/D.")
            score -= 0.2

        placeholder = sum(1 for option in options if self._is_placeholder_option(option))
        if placeholder:
            issues.append("Placeholder text detected among options.")
            score -= 0.1

        return max(0.0, round(score, 3)), matched, issues

    def _score_accuracy(self, question: str, explanation: str, answer: str, options: list[str], expected: dict[str, str]) -> tuple[float, list[str], list[str]]:
        issues: list[str] = []
        matched: list[str] = []
        score = 1.0

        if answer in {"A", "B", "C", "D"}:
            matched.append("Answer is formatted correctly.")
        else:
            issues.append("Answer key is missing or invalid.")
            score -= 0.35

        if explanation and len(explanation) >= 15:
            matched.append("Explanation is sufficiently detailed.")
        else:
            issues.append("Explanation lacks depth.")
            score -= 0.2

        if question and options:
            matched.append("Enough information to cross-check.")
        else:
            issues.append("Insufficient information to validate accuracy.")
            score -= 0.2

        subject = expected.get("subject", "")
        if subject and not self._contains_normalized(question + " " + explanation, subject):
            issues.append("Content drifts from the declared subject.")
            score -= 0.25

        if explanation and answer and answer not in self._normalize_text(explanation):
            issues.append("Explanation does not mention the answer.")
            score -= 0.2

        return max(0.0, round(score, 3)), matched, issues

    def _score_distractors(self, options: list[str], answer: str) -> tuple[float, list[str], list[str]]:
        issues: list[str] = []
        matched: list[str] = []
        if not options or len(options) < _REQUIRED_OPTIONS:
            return 0.0, matched, ["Not enough options."]

        normalized_options = [self._normalize_text(option) for option in options if option.strip()]
        if len(normalized_options) < _REQUIRED_OPTIONS:
            return 0.0, matched, ["Options include empty or placeholder entries."]

        uniqueness = len(set(normalized_options)) / len(normalized_options)
        lengths = [len(option) for option in normalized_options]
        length_balance = 1.0
        if lengths and max(lengths) > 0:
            length_balance = max(0.3, 1.0 - (max(lengths) - min(lengths)) / max(lengths))

        if uniqueness >= 0.8:
            matched.append("Options are unique.")
        else:
            issues.append("Distractors repeat too much.")

        if length_balance >= 0.7:
            matched.append("Lengths are balanced.")
        else:
            issues.append("Distractor lengths vary wildly.")

        placeholder_count = sum(1 for option in options if self._is_placeholder_option(option))
        if placeholder_count:
            issues.append("Placeholder text exists in options.")

        answer_text = ""
        lookup = self._build_option_lookup(options)
        if answer in lookup:
            answer_text = self._normalize_text(lookup[answer])

        if answer_text:
            for option in normalized_options:
                if option != answer_text and self._option_similarity(answer_text, option) >= 0.75:
                    issues.append("Some options mimic the correct answer.")
                    break

        duplicates = sum(
            1 for idx in range(len(normalized_options)) for jdx in range(idx + 1, len(normalized_options))
            if self._option_similarity(normalized_options[idx], normalized_options[jdx]) >= 0.9
        )
        if duplicates:
            issues.append("Multiple distractors are near-duplicates.")

        score = round(max(0.0, min(1.0, 0.6 * uniqueness + 0.4 * length_balance)), 3)
        return score, matched, issues

    def _score_explanation(self, explanation: str, alignment_score: float, question: str, difficulty: str) -> tuple[float, list[str], list[str]]:
        issues: list[str] = []
        matched: list[str] = []
        if not explanation:
            return 0.0, matched, ["Missing explanation."]

        tokens = self._tokens(explanation)
        reasoning_hits = sum(1 for token in tokens if token in _REASONING_MARKERS)
        score = 0.5

        if len(explanation) >= 20:
            matched.append("Explanation has sufficient length.")
            score += 0.15
        else:
            issues.append("Explanation is short.")
            score -= 0.15

        if reasoning_hits >= 1:
            matched.append("Contains reasoning keywords.")
            score += 0.15
        else:
            issues.append("Explanation lacks reasoning cues.")

        if alignment_score >= 0.35:
            matched.append("Explanation links to curriculum.")
            score += 0.1
        else:
            issues.append("Explanation drifts from curriculum focus.")

        normalized_question = self._normalize_text(question)
        if normalized_question and normalized_question in self._normalize_text(explanation):
            matched.append("Explanation references the question.")
            score += 0.05

        difficulty_target = self._difficulty_target(difficulty)
        if difficulty_target == "advanced" and reasoning_hits < 2:
            issues.append("High difficulty but lacks argumentation.")
            score -= 0.15
        if difficulty_target == "application" and reasoning_hits < 1:
            issues.append("Application level question but explanation lacks context.")
            score -= 0.1
        if difficulty_target == "recall" and len(question) > 60:
            issues.append("Recall-level question is too verbose.")
            score -= 0.05

        return max(0.0, min(1.0, round(score, 3))), matched, issues

    def _detect_answer_key_issues(self, answer: str, options: list[str], explanation: str) -> tuple[float, list[str]]:
        issues: list[str] = []
        penalty = 0.0
        answer_letter = (answer or "").strip().upper()
        lookup = self._build_option_lookup(options)
        if answer_letter not in lookup:
            issues.append("Answer key does not map to any provided option.")
            penalty += 0.35
            return min(penalty, 0.8), issues

        normalized_explanation = self._normalize_text(explanation)
        correct_option = lookup[answer_letter]
        answer_text = self._normalize_text(correct_option)
        mention_answer = False
        if answer_letter.lower() in normalized_explanation:
            mention_answer = True
        if answer_text and answer_text in normalized_explanation:
            mention_answer = True
        if explanation and not mention_answer:
            issues.append("Explanation fails to mention the declared answer.")
            penalty += 0.2

        for other_letter in lookup:
            if other_letter == answer_letter:
                continue
            marker = f"dap an {other_letter.lower()}"
            if marker in normalized_explanation:
                issues.append("Explanation references a different answer option than the declared key.")
                penalty += 0.25
                break

        return min(penalty, 0.8), issues

    def _detect_weak_distractors(self, options: list[str], answer: str) -> tuple[float, list[str]]:
        issues: list[str] = []
        penalty = 0.0
        normalized = [self._normalize_text(option) for option in options if option.strip()]
        if len(normalized) < _REQUIRED_OPTIONS:
            issues.append("Not enough answer choices to evaluate distractors.")
            penalty += 0.35
            return min(penalty, 0.8), issues

        duplicates = sum(
            1
            for idx in range(len(normalized))
            for jdx in range(idx + 1, len(normalized))
            if self._option_similarity(normalized[idx], normalized[jdx]) >= 0.9
        )
        if duplicates:
            issues.append("Distractors are too similar or duplicate.")
            penalty += min(0.25, 0.05 * duplicates)

        lookup = self._build_option_lookup(options)
        answer_letter = (answer or "").strip().upper()
        normalized_answer = ""
        if answer_letter in lookup:
            normalized_answer = self._normalize_text(lookup[answer_letter])
        for option_text in normalized:
            if not normalized_answer or option_text == normalized_answer:
                continue
            if self._option_similarity(normalized_answer, option_text) >= 0.75:
                issues.append("Distractors mimic the correct answer too closely.")
                penalty += 0.15
                break

        placeholder_count = sum(1 for option in options if self._is_placeholder_option(option))
        if placeholder_count:
            issues.append("Distractors contain placeholder language.")
            penalty += min(0.2, 0.06 * placeholder_count)

        lengths = [len(option) for option in normalized if option]
        if lengths:
            max_len, min_len = max(lengths), min(lengths)
            if max_len > 0 and (max_len - min_len) / max_len > 0.8:
                issues.append("Distractors are imbalanced in length.")
                penalty += 0.1

        return min(penalty, 0.9), issues

    def _detect_explanation_mismatch(
        self, explanation: str, answer: str, options: list[str], question: str, difficulty: str
    ) -> tuple[float, list[str]]:
        issues: list[str] = []
        penalty = 0.0
        if not explanation:
            issues.append("Missing explanation for the item.")
            penalty += 0.3
            return min(penalty, 0.8), issues

        normalized_explanation = self._normalize_text(explanation)
        normalized_question = self._normalize_text(question)
        if question and normalized_question and normalized_question not in normalized_explanation:
            issues.append("Explanation does not reference the question statement.")
            penalty += 0.1

        answer_letter = (answer or "").strip().upper()
        lookup = self._build_option_lookup(options)
        expected_answer_text = lookup.get(answer_letter, "")
        answer_mentions = any(
            marker in normalized_explanation
            for marker in (
                answer_letter.lower(),
                f"dap an {answer_letter.lower()}",
                self._normalize_text(expected_answer_text),
            )
            if marker
        )
        if not answer_mentions:
            issues.append("Explanation is not anchored to the declared answer.")
            penalty += 0.2

        if difficulty:
            target = self._difficulty_target(difficulty)
            actual = self._estimate_actual_difficulty(question, explanation)
            if target != actual and abs(self._difficulty_rank(target) - self._difficulty_rank(actual)) >= 2:
                issues.append("Explanation depth does not match the requested difficulty.")
                penalty += 0.15

        return min(penalty, 0.8), issues

    def _detect_off_topic(self, expected: dict[str, str], question: str, explanation: str) -> tuple[float, list[str]]:
        issues: list[str] = []
        penalty = 0.0
        context = " ".join(part for part in (question, explanation) if part)
        for field, label in (
            ("subject", "subject"),
            ("grade", "grade"),
            ("topic", "topic"),
            ("lesson", "lesson"),
            ("yccd", "YCCĐ"),
        ):
            expected_value = expected.get(field, "")
            if expected_value and not self._contains_normalized(context, expected_value):
                issues.append(f"Missing {label} cues.")
                penalty += 0.14
        return min(penalty, 0.9), issues

    def _detect_difficulty_mismatch(self, difficulty: str, question: str, explanation: str) -> tuple[float, list[str]]:
        issues: list[str] = []
        penalty = 0.0
        if not difficulty:
            return penalty, issues

        target = self._difficulty_target(difficulty)
        actual = self._estimate_actual_difficulty(question, explanation)
        delta = abs(self._difficulty_rank(target) - self._difficulty_rank(actual))
        if delta >= 2:
            issues.append(f"Difficulty mismatch: requested {target}, actual {actual}.")
            penalty += 0.25
        elif delta == 1 and target != actual:
            issues.append(f"Item leans toward {actual} while curriculum requested {target}.")
            penalty += 0.12
        return min(penalty, 0.4), issues

    def _detect_clarity_ambiguity(self, question: str) -> tuple[float, list[str]]:
        issues: list[str] = []
        penalty = 0.0
        if not question:
            issues.append("Missing question text.")
            penalty += 0.4
            return min(penalty, 0.7), issues

        word_count = len(question.split())
        if word_count < 10:
            issues.append("Question is too short.")
            penalty += 0.15
        if "?" not in question:
            issues.append("Question lacks a question mark.")
            penalty += 0.1
        unique_ratio = len(set(question.lower().split())) / max(word_count, 1)
        if unique_ratio < 0.45:
            issues.append("Question repeats the same terms.")
            penalty += 0.08

        return min(penalty, 0.6), issues

    def _apply_real_error_checks(
        self,
        question: str,
        explanation: str,
        options: list[str],
        answer: str,
        expected: dict[str, str],
        difficulty: str,
    ) -> tuple[dict[str, float], list[str], list[str]]:
        penalties = {name: 0.0 for name in _CRITERIA}
        issues: list[str] = []
        recommendations: list[str] = []

        answer_penalty, answer_issues = self._detect_answer_key_issues(answer, options, explanation)
        penalties["accuracy"] += answer_penalty
        issues.extend(answer_issues)

        distractor_penalty, distractor_issues = self._detect_weak_distractors(options, answer)
        penalties["distractor_quality"] += distractor_penalty
        issues.extend(distractor_issues)

        explanation_penalty, explanation_issues = self._detect_explanation_mismatch(
            explanation, answer, options, question, difficulty
        )
        penalties["explanation_quality"] += explanation_penalty
        issues.extend(explanation_issues)

        clarity_penalty, clarity_issues = self._detect_clarity_ambiguity(question)
        penalties["clarity"] += clarity_penalty
        issues.extend(clarity_issues)

        off_topic_penalty, off_topic_issues = self._detect_off_topic(expected, question, explanation)
        penalties["alignment"] += off_topic_penalty
        issues.extend(off_topic_issues)

        difficulty_penalty, difficulty_issues = self._detect_difficulty_mismatch(difficulty, question, explanation)
        penalties["explanation_quality"] += difficulty_penalty
        penalties["alignment"] += min(difficulty_penalty, 0.15)
        if difficulty_issues:
            recommendations.append("Adjust the explanation depth to match the requested difficulty.")
        issues.extend(difficulty_issues)

        return penalties, issues, recommendations

    @classmethod
    def _has_critical_issue(cls, issues: list[str], question: str, options: list[str], answer: str, explanation: str) -> bool:
        normalized = [cls._normalize_text(issue) for issue in issues]
        critical_markers = (
            "missing question",
            "answer key does not map",
            "not enough options",
            "missing explanation",
            "references a different answer option",
            "duplicate",
            "placeholder",
        )
        if any(any(marker in issue for marker in critical_markers) for issue in normalized):
            return True
        if not question.strip():
            return True
        if not options or len(options) < _REQUIRED_OPTIONS:
            return True
        if answer not in {"A", "B", "C", "D"}:
            return True
        return False

    @staticmethod
    def _is_minor_issue(normalized_issue: str) -> bool:
        minor_markers = (
            "question is too brief",
            "lack punctuation",
            "question lacks a question mark",
            "explanation does not mention the answer",
            "explanation does not reference the question statement",
            "explanation lacks depth",
            "missing grade cues",
            "missing topic cues",
            "missing lesson cues",
            "missing yccd cues",
            "question repeats the same terms",
        )
        return any(marker in normalized_issue for marker in minor_markers)

    def _build_rubric_assessment(self, payload: dict[str, Any]) -> CriticAssessment:
        question = self._coerce_text(payload.get("question"))
        explanation = self._coerce_text(payload.get("explanation"))
        answer = self._coerce_text(payload.get("answer")).upper()
        options = [self._coerce_text(option) for option in (payload.get("options") or []) if self._coerce_text(option)]
        expected = self._extract_expected_context(payload)
        response_text = " ".join(part for part in (question, explanation, " ".join(options), answer) if part)

        alignment_score, alignment_matched, alignment_missing = self._score_alignment(expected, response_text)
        clarity_score, clarity_matched, clarity_issues = self._score_clarity(question, explanation, options, answer)
        accuracy_score, accuracy_matched, accuracy_issues = self._score_accuracy(question, explanation, answer, options, expected)
        distractor_score, distractor_matched, distractor_issues = self._score_distractors(options, answer)
        difficulty = self._extract_difficulty(payload)
        explanation_score, explanation_matched, explanation_issues = self._score_explanation(explanation, alignment_score, question, difficulty)

        detection_penalties, detection_issues, detection_recommendations = self._apply_real_error_checks(
            question, explanation, options, answer, expected, difficulty
        )

        scores = {
            "alignment": round(alignment_score, 3),
            "clarity": round(clarity_score, 3),
            "accuracy": round(accuracy_score, 3),
            "distractor_quality": round(distractor_score, 3),
            "explanation_quality": round(explanation_score, 3),
        }
        for criterion, penalty in detection_penalties.items():
            if penalty:
                scores[criterion] = max(0.0, round(scores.get(criterion, 0.0) - penalty, 3))

        overall_score = round(sum(scores[name] for name in _CRITERIA) / len(_CRITERIA), 3)

        base_issues = self._merge_unique(
            alignment_missing,
            clarity_issues,
            accuracy_issues,
            distractor_issues,
            explanation_issues,
        )
        issues = self._merge_unique(base_issues, detection_issues)
        matched_terms = self._merge_unique(
            alignment_matched,
            clarity_matched,
            accuracy_matched,
            distractor_matched,
            explanation_matched,
        )

        recommendations: list[str] = []
        if scores["alignment"] < 0.7:
            recommendations.append("Increase curriculum alignment references.")
        if scores["clarity"] < 0.7:
            recommendations.append("Rewrite the question for clarity.")
        if scores["accuracy"] < 0.7:
            recommendations.append("Double-check the answer key and references.")
        if scores["distractor_quality"] < 0.7:
            recommendations.append("Make distractors distinct and proportional.")
        if scores["explanation_quality"] < 0.7:
            recommendations.append("Expand the explanation with reasoning.")
        recommendations = self._merge_unique(recommendations, detection_recommendations)

        normalized_issue_texts = [self._normalize_text(issue) for issue in issues if issue]
        minor_issue_texts = [issue for issue in normalized_issue_texts if self._is_minor_issue(issue)]
        serious_issue_texts = [issue for issue in normalized_issue_texts if issue not in minor_issue_texts]

        critical_issue = self._has_critical_issue(issues, question, options, answer, explanation)
        if critical_issue:
            recommended_action = "reject"
        elif (
            overall_score >= 0.85
            and all(scores[criterion] >= 0.8 for criterion in _CRITERIA)
            and not detection_issues
        ):
            recommended_action = "pass"
        elif (
            overall_score >= 0.82
            and all(scores[criterion] >= 0.75 for criterion in _CRITERIA)
            and not serious_issue_texts
            and normalized_issue_texts
        ):
            recommended_action = "pass"
        else:
            recommended_action = "refine"

        issue_penalty = min(0.3, 0.04 * len(issues))
        weighted_confidence = (
            0.4 * overall_score
            + 0.2 * scores["alignment"]
            + 0.2 * scores["accuracy"]
            + 0.1 * scores["clarity"]
            + 0.1 * scores["explanation_quality"]
        )
        confidence = round(max(0.25, min(0.95, weighted_confidence - issue_penalty)), 3)

        quality_flags = self._merge_unique(
            issues,
            [f"{name}:{score}" for name, score in scores.items() if score < 0.7],
        )
        summary = (
            f"Rubric critique: alignment={scores['alignment']}, clarity={scores['clarity']}, "
            f"accuracy={scores['accuracy']}, distractor_quality={scores['distractor_quality']}, "
            f"explanation_quality={scores['explanation_quality']}."
        )

        return CriticAssessment(
            scores=scores,
            issues=issues,
            confidence=confidence,
            recommended_action=recommended_action,
            summary=summary,
            matched_terms=matched_terms,
            missing_terms=alignment_missing,
            quality_flags=quality_flags,
            recommendations=recommendations,
            revision_focus=list(recommendations[:5]),
            minor_issue_only=bool(normalized_issue_texts and not serious_issue_texts),
        )

    def _normalize_llm_report(self, llm_report: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(llm_report)
        if "scores" not in normalized:
            normalized["scores"] = {
                "alignment": float(normalized.get("coverage_ratio", 0.0) or 0.0),
                "clarity": float(normalized.get("clarity_score", 0.0) or 0.0),
                "accuracy": float(normalized.get("accuracy", 0.0) or 0.0),
                "distractor_quality": float(normalized.get("distractor_quality", 0.0) or 0.0),
                "explanation_quality": float(normalized.get("explanation_quality", 0.0) or 0.0),
            }
        normalized.setdefault("issues", normalized.get("quality_flags") or [])
        normalized.setdefault("recommended_action", "pass" if bool(normalized.get("pass", False)) else "refine")
        normalized.setdefault("confidence", normalized.get("confidence", 0.0))
        normalized.setdefault("summary", "LLM critique complete")
        normalized["recommended_action"] = self._normalize_action(str(normalized.get("recommended_action", "")))
        return normalized

    @staticmethod
    def _normalize_action(action: str) -> str:
        normalized = action.strip().lower()
        mapping = {
            "continue": "pass",
            "pass": "pass",
            "refine": "refine",
            "rewrite": "reject",
            "reject": "reject",
        }
        return mapping.get(normalized, normalized or "refine")

    def _llm_assessment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.llm_client:
            return None
        timeout = self._timeout_seconds()
        try:
            response = call_with_timeout(
                lambda: self.llm_client.chat_json(
                    CRITIC_SYSTEM_PROMPT,
                    build_critic_prompt(payload),
                    model=getattr(self.llm_client, "critic_model_name", "gpt-4o"),
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

    def _emit_result(self, payload: dict[str, Any], assessment: CriticAssessment, mode: str) -> Any:
        metadata = {
            "agent": self.name,
            "mode": mode,
            "scores": assessment.scores,
            "recommended_action": assessment.recommended_action,
            "minor_issue_only": assessment.minor_issue_only,
        }
        if assessment.recommended_action == "pass":
            return self.ok(
                payload,
                confidence=assessment.confidence,
                metadata=metadata,
                issues=assessment.issues,
                next_action="continue",
            )
        return self.fail(
            assessment.issues or ["Critic requests refinement."],
            output=payload,
            confidence=assessment.confidence,
            metadata=metadata,
            next_action=assessment.recommended_action,
        )

    def execute(self, lesson_plan):
        payload = dict(lesson_plan or {})
        heuristic_assessment = self._build_rubric_assessment(payload)
        heuristic_payload = dict(payload)
        heuristic_payload["critic_report"] = heuristic_assessment.to_dict()
        heuristic_payload["revision_focus"] = heuristic_assessment.revision_focus[:5]
        heuristic_payload["quality_targets"] = [
            "Bám sát YCCĐ",
            "4 phương án rõ ràng",
            "Giải thích ngắn gọn, dễ hiểu",
        ]
        heuristic_payload["focus_terms"] = heuristic_assessment.matched_terms[:6]

        llm_report = self._llm_assessment(heuristic_payload)
        if not llm_report:
            return self._emit_result(heuristic_payload, heuristic_assessment, "heuristic")

        normalized_llm = self._normalize_llm_report(llm_report)
        llm_scores = normalized_llm.get("scores") or {}
        merged_scores = {
            key: round(max(heuristic_assessment.scores.get(key, 0.0), float(llm_scores.get(key, 0.0) or 0.0)), 3)
            for key in _CRITERIA
        }
        if merged_issues:
            for criterion in _CRITERIA:
                base_score = round(heuristic_assessment.scores.get(criterion, 0.0), 3)
                merged_scores[criterion] = min(merged_scores[criterion], base_score)

        merged_issues = self._merge_unique(
            heuristic_assessment.issues,
            [str(item).strip() for item in (normalized_llm.get("issues") or []) if str(item).strip()],
        )
        merged_recommendations = self._merge_unique(
            heuristic_assessment.recommendations,
            [str(item).strip() for item in (normalized_llm.get("recommendations") or []) if str(item).strip()],
        )
        merged_revision_focus = self._merge_unique(
            heuristic_assessment.revision_focus,
            [str(item).strip() for item in (normalized_llm.get("revision_focus") or []) if str(item).strip()],
        )
        merged_matched_terms = self._merge_unique(
            heuristic_assessment.matched_terms,
            [str(item).strip() for item in (normalized_llm.get("matched_terms") or []) if str(item).strip()],
        )
        merged_missing_terms = self._merge_unique(
            heuristic_assessment.missing_terms,
            [str(item).strip() for item in (normalized_llm.get("missing_terms") or []) if str(item).strip()],
        )

        overall_score = round(sum(merged_scores.values()) / len(_CRITERIA), 3)
        base_confidence = max(
            heuristic_assessment.confidence,
            float(normalized_llm.get("confidence", 0.0) or 0.0),
            overall_score,
        )
        issue_penalty = 0.03 * len(merged_issues)
        adjusted_confidence = base_confidence - issue_penalty
        confidence = round(max(0.25, adjusted_confidence), 3)

        normalized_issue_texts = [self._normalize_text(issue) for issue in merged_issues if issue]
        minor_issue_texts = [issue for issue in normalized_issue_texts if self._is_minor_issue(issue)]
        serious_issue_texts = [issue for issue in normalized_issue_texts if issue not in minor_issue_texts]

        recommended_action = normalized_llm.get("recommended_action") or heuristic_assessment.recommended_action
        if merged_issues:
            question = self._coerce_text(payload.get("question"))
            explanation = self._coerce_text(payload.get("explanation"))
            answer = (self._coerce_text(payload.get("answer")) or "").upper()
            options = [self._coerce_text(option) for option in (payload.get("options") or []) if self._coerce_text(option)]
            critical = self._has_critical_issue(merged_issues, question, options, answer, explanation)
            if critical:
                recommended_action = "reject"
            else:
                pass_threshold = 0.82
                criterion_threshold = 0.75
                strong_pass = (
                    overall_score >= pass_threshold
                    and all(scores[criterion] >= criterion_threshold for criterion in _CRITERIA)
                    and not serious_issue_texts
                )
                if strong_pass:
                    recommended_action = "pass"
                else:
                    recommended_action = "refine"
        summary = str(normalized_llm.get("summary") or heuristic_assessment.summary)
        quality_flags = self._merge_unique(merged_issues, [f"{key}:{score}" for key, score in merged_scores.items() if score < 0.7])
        minor_issue_only = bool(normalized_issue_texts and not serious_issue_texts)

        merged_assessment = CriticAssessment(
            scores=merged_scores,
            issues=merged_issues,
            confidence=confidence,
            recommended_action=recommended_action,
            summary=summary,
            matched_terms=merged_matched_terms,
            missing_terms=merged_missing_terms,
            quality_flags=quality_flags,
            recommendations=merged_recommendations,
            revision_focus=merged_revision_focus[:5],
            minor_issue_only=minor_issue_only,
        )

        critiqued_payload = dict(heuristic_payload)
        critiqued_payload["critic_report"] = {
            **merged_assessment.to_dict(),
            "mode": "llm+heuristic",
            "coverage_ratio": merged_scores["alignment"],
            "pedagogy_score": round((merged_scores["clarity"] + merged_scores["explanation_quality"]) / 2, 3),
            "distractor_score": merged_scores["distractor_quality"],
            "explanation_score": merged_scores["explanation_quality"],
        }
        critiqued_payload["revision_focus"] = merged_revision_focus[:5]
        critiqued_payload["quality_targets"] = heuristic_payload["quality_targets"]
        critiqued_payload["focus_terms"] = merged_matched_terms[:6]

        return self._emit_result(critiqued_payload, merged_assessment, "llm+heuristic")
