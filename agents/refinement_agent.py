from __future__ import annotations

from os import getenv
from typing import Any

from agents.base_agent import BaseAgent
from clients.base_llm_client import BaseLLMClient
from orchestrator.agent_result import AgentResult
from services.llm_utils import call_with_timeout


class RefinementAgent(BaseAgent):
    def __init__(self, llm_client: BaseLLMClient):
        super().__init__()
        self.llm_client = llm_client

    @staticmethod
    def _coerce_text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _timeout_seconds() -> int:
        raw_timeout = getenv("AI_EXAM_LLM_TIMEOUT_SECONDS", "20").strip()
        try:
            return max(5, int(raw_timeout))
        except ValueError:
            return 20

    def execute(self, failed_output: dict[str, Any] | None) -> AgentResult:
        """
        Retry generation using critic feedback only.
        """
        payload = dict(failed_output or {})
        yccd_item = dict(payload.get("yccd_item") or {})
        muc_do = payload.get("muc_do", "ThÃ´ng hiÃ¡Â»Æ’u")

        if not yccd_item:
            return self.fail(["Thiáº¿u yccd_item Ä‘áº§u vÃ o"], output=payload, next_action="review_input")

        critic_report = dict(payload.get("critic_report") or payload.get("critique_report") or {})
        revision_focus = self._coerce_list(critic_report.get("revision_focus") or payload.get("revision_focus"))
        recommendations = self._coerce_list(critic_report.get("recommendations"))
        issues = self._coerce_list(critic_report.get("issues"))
        question = self._coerce_text(payload.get("question"))
        options = [self._coerce_text(option) for option in (payload.get("options") or []) if self._coerce_text(option)]
        answer = self._coerce_text(payload.get("answer")).upper()
        explanation = self._coerce_text(payload.get("explanation"))

        if not revision_focus:
            revision_focus = issues or recommendations

        yccd_item["retry"] = True
        refinement_context = {
            "critic_report": critic_report,
            "revision_focus": revision_focus,
            "recommendations": recommendations,
            "issues": issues,
            "scores": dict(critic_report.get("scores") or {}),
            "previous_question": question,
            "previous_options": options,
            "previous_answer": answer,
            "previous_explanation": explanation,
        }

        timeout = self._timeout_seconds()
        generated = call_with_timeout(
            lambda: self.llm_client.generate_question_yccd(yccd_item, muc_do, context=refinement_context),
            timeout=timeout,
            fallback=None,
        )
        if not generated:
            return self.fail(
                ["LLM không trả về kết quả hợp lệ sau refine"],
                output=payload,
                next_action="retry",
            )

        return self.ok(
            generated,
            metadata={
                "muc_do": muc_do,
                "retry": True,
                "refinement_context": refinement_context,
            },
        )
