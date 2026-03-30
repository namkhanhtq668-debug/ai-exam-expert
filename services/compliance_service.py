import logging
import re
from collections.abc import Iterable
from typing import Any

from services.schema_service import SchemaService

class ComplianceService:
    def __init__(self, schema, compliance_threshold=0.8):
        """
        Initialize the compliance service.
        Args:
            schema (dict): JSON schema for validation.
            compliance_threshold (float): Minimum compliance score required (0.0 to 1.0).
        """
        self.schema = schema
        self.schema_service = SchemaService(schema)
        self.compliance_threshold = compliance_threshold
        self.logger = logging.getLogger("ComplianceService")

    def _flatten_text(self, data: Any, *, limit: int = 8000) -> str:
        parts: list[str] = []

        def _walk(value: Any) -> None:
            if len(" ".join(parts)) >= limit:
                return
            if value is None:
                return
            if isinstance(value, str):
                text = value.strip()
                if text:
                    parts.append(text)
                return
            if isinstance(value, dict):
                for key, item in value.items():
                    key_text = str(key).strip()
                    if key_text:
                        parts.append(key_text)
                    if len(" ".join(parts)) >= limit:
                        return
                    _walk(item)
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    _walk(item)
                return
            text = str(value).strip()
            if text:
                parts.append(text)

        _walk(data)
        return " ".join(parts)[:limit]

    def _keyword_overlap(self, source: str, target: str) -> int:
        source_terms = {
            token
            for token in re.findall(r"[A-Za-zÀ-ỹ0-9_]+", source.lower())
            if len(token) >= 4
        }
        target_lower = target.lower()
        return sum(1 for term in source_terms if term in target_lower)

    def _has_obvious_contradiction(self, text: str) -> bool:
        lowered = text.lower()
        if re.search(r"\bkhông\s+(nên|được|thể|cần|phải)\b", lowered) and re.search(
            r"\b(nên|được|thể|cần|phải)\b", lowered
        ):
            return True
        if "luôn" in lowered and "không bao giờ" in lowered:
            return True
        if "đúng" in lowered and "sai" in lowered:
            return True
        return False

    def soft_review_text(
        self,
        text: Any,
        *,
        context: Any | None = None,
        expected_topics: Iterable[str] | None = None,
        required_sections: Iterable[str] | None = None,
        label: str = "ai_output",
    ) -> list[str]:
        warnings: list[str] = []
        content = str(text or "").strip() if not isinstance(text, str) else text.strip()
        context_text = self._flatten_text(context) if context is not None else ""
        lower_content = content.lower()
        is_html_like = "<html" in lower_content or "<table" in lower_content or "<div" in lower_content
        has_structured_markers = is_html_like or "<" in content or "```" in content or "\n-" in content or "\n*" in content

        if not content:
            warnings.append("Output trống.")
        elif len(content) < 40 and not has_structured_markers:
            warnings.append("Output khá ngắn, có thể còn yếu.")

        if expected_topics:
            topics = [str(topic).strip() for topic in expected_topics if str(topic).strip()]
            if topics:
                exact_match = any(topic.lower() in lower_content for topic in topics)
                if not exact_match:
                    topic_overlap = max(self._keyword_overlap(topic, content) for topic in topics)
                    if topic_overlap == 0 and len(content) >= 40:
                        warnings.append("Output chưa bám rõ chủ đề đầu vào.")

        if context_text and len(content) >= 80 and "lesson_plan_html" not in label and self._keyword_overlap(context_text, content) < 2:
            warnings.append("Output ít liên hệ với ngữ cảnh đầu vào.")

        if required_sections:
            missing = [str(section).strip() for section in required_sections if str(section).strip()]
            if missing and not (is_html_like and "lesson_plan_html" in label):
                lowered = content.lower()
                present = [section for section in missing if section.lower() in lowered]
                if not present and len(content) >= 50:
                    warnings.append("Output chưa thể hiện rõ các phần bắt buộc.")

        if content and self._has_obvious_contradiction(content):
            warnings.append("Có dấu hiệu mâu thuẫn nội dung.")

        if warnings:
            self.logger.warning("%s semantic review warnings: %s", label, "; ".join(warnings))
        return warnings

    def soft_review_payload(
        self,
        data: Any,
        *,
        context: Any | None = None,
        expected_topics: Iterable[str] | None = None,
        required_sections: Iterable[str] | None = None,
        label: str = "ai_payload",
    ) -> list[str]:
        warnings: list[str] = []
        payload_text = self._flatten_text(data)
        context_text = self._flatten_text(context) if context is not None else ""
        lower_payload = payload_text.lower()

        if not payload_text:
            warnings.append("Payload trống.")
        elif len(payload_text) < 70:
            warnings.append("Payload còn ngắn, có thể chưa đủ nội dung.")

        if expected_topics:
            topics = [str(topic).strip() for topic in expected_topics if str(topic).strip()]
            if topics:
                exact_match = any(topic.lower() in lower_payload for topic in topics)
                if not exact_match:
                    topic_overlap = max(self._keyword_overlap(topic, payload_text) for topic in topics)
                    if topic_overlap == 0 and len(payload_text) >= 70:
                        warnings.append("Payload chưa bám rõ chủ đề đầu vào.")

        if context_text and len(payload_text) >= 120 and self._keyword_overlap(context_text, payload_text) < 2:
            warnings.append("Payload ít liên hệ với ngữ cảnh đầu vào.")

        if required_sections:
            required = [str(section).strip() for section in required_sections if str(section).strip()]
            lowered = payload_text.lower()
            missing = [section for section in required if section.lower() not in lowered]
            if missing:
                warnings.append(f"Thiếu các phần bắt buộc: {', '.join(missing)}.")

        if payload_text and self._has_obvious_contradiction(payload_text):
            warnings.append("Có dấu hiệu mâu thuẫn nội dung.")

        if warnings:
            self.logger.warning("%s semantic review warnings: %s", label, "; ".join(warnings))
        return warnings

    def validate_schema(self, data):
        """
        Validate data against the JSON schema.
        Args:
            data (dict): Data to validate.
        Returns:
            bool: True if data is valid, False otherwise.
        """
        try:
            valid, errors = self.schema_service.validate(data)
            if not valid:
                self.logger.warning("Schema validation failed: %s", "; ".join(errors))
            return valid
        except Exception as e:
            self.logger.error("Validation error: %s", e)
            return False

    def check_compliance_score(self, score):
        """
        Check if the compliance score meets the threshold.
        Args:
            score (float): Compliance score (0.0 to 1.0).
        Returns:
            bool: True if score meets or exceeds the threshold, False otherwise.
        """
        return score >= self.compliance_threshold

    def evaluate_compliance(self, data, score):
        """
        Evaluate compliance based on schema validation and score.
        Args:
            data (dict): Data to validate.
            score (float): Compliance score.
        Returns:
            bool: True if data passes all compliance checks, False otherwise.
        """
        is_valid = self.validate_schema(data)
        meets_threshold = self.check_compliance_score(score)
        return is_valid and meets_threshold
