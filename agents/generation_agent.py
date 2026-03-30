from __future__ import annotations

from os import getenv
from agents.base_agent import BaseAgent
from clients.base_llm_client import BaseLLMClient
from orchestrator.agent_result import AgentResult
from services.llm_utils import call_with_timeout


class GenerationAgent(BaseAgent):
    def __init__(self, llm_client: BaseLLMClient):
        super().__init__()
        self.llm_client = llm_client

    def execute(self, input_data) -> AgentResult:
        """
        Delegates generation to the injected LLM client and returns AgentResult.
        """
        payload = dict(input_data or {})
        yccd_item = payload.get("yccd_item")
        muc_do = payload.get("muc_do", "Thông hiểu")
        if not yccd_item:
            return self.fail(["Thiếu yccd_item đầu vào"], output=payload, next_action="review_input")

        generation_context = dict(payload.get("generation_context") or {})
        generation_context.setdefault(
            "input_snapshot",
            {
                "has_lop": bool(yccd_item.get("lop")) if isinstance(yccd_item, dict) else False,
                "has_chu_de": bool(yccd_item.get("chu_de")) if isinstance(yccd_item, dict) else False,
                "has_bai": bool(yccd_item.get("bai")) if isinstance(yccd_item, dict) else False,
                "has_yccd": bool(yccd_item.get("yccd")) if isinstance(yccd_item, dict) else False,
            },
        )
        generation_context.setdefault("yccd_summary", str((yccd_item or {}).get("yccd", ""))[:160] if isinstance(yccd_item, dict) else "")
        if payload.get("plan"):
            plan = payload.get("plan") or {}
            generation_context.setdefault("strategy", plan.get("strategy") or {})
            generation_context.setdefault("plan_notes", plan.get("plan_notes") or [])
            generation_context.setdefault("quality_targets", plan.get("quality_targets") or [])
            generation_context.setdefault("focus_terms", plan.get("focus_terms") or [])
            generation_context.setdefault("curriculum_context", plan.get("curriculum_context") or {})
            generation_context.setdefault("topic_focus", plan.get("topic_focus") or {})
            generation_context.setdefault("difficulty", plan.get("difficulty") or {})
            generation_context.setdefault("constraints", plan.get("constraints") or {})
            generation_context.setdefault("retrieval_context", plan.get("retrieval_context") or {})

        timeout = self._timeout_seconds()
        generated = call_with_timeout(
            lambda: self.llm_client.generate_question_yccd(yccd_item, muc_do, context=generation_context),
            timeout=timeout,
            fallback=None,
        )
        if not generated:
            return self.fail(["LLM không trả về kết quả hợp lệ"], output=payload, next_action="retry")

        return self.ok(generated, metadata={"muc_do": muc_do, "generation_context": generation_context})

    @staticmethod
    def _timeout_seconds() -> int:
        raw_timeout = getenv("AI_EXAM_LLM_TIMEOUT_SECONDS", "20").strip()
        try:
            return max(5, int(raw_timeout))
        except ValueError:
            return 20
