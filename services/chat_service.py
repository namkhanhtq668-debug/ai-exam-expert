from __future__ import annotations

from dataclasses import dataclass

from clients.base_llm_client import BaseLLMClient
from services.compliance_service import ComplianceService
from services.schema_service import SchemaService
from services.telemetry_service import TelemetryService

_TEXT_VALIDATOR = SchemaService({"type": "string", "minLength": 1})
_COMPLIANCE = ComplianceService({"type": "string", "minLength": 1})


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    valid, _ = _TEXT_VALIDATOR.validate(text)
    return text if valid else ""


@dataclass
class ChatService:
    llm_client: BaseLLMClient
    telemetry: TelemetryService

    def ask(self, prompt: str, system_prompt: str, *, username: str | None = None) -> str:
        response = self.llm_client.generate_text(prompt, system_instruction=system_prompt)
        self.telemetry.record_chat_question(username, prompt)
        text = _safe_text(response)
        _COMPLIANCE.soft_review_text(text, context=prompt, label="chat")
        return text
