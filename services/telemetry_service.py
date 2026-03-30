from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.audit_service import AuditService


@dataclass
class TelemetryService:
    audit: AuditService

    def record_module_entry(self, module_name: str, username: str | None = None) -> None:
        self.audit.record_event(
            trace_id=username or "anonymous",
            event_type="module_entry",
            metadata={"module": module_name, "username": username or "anonymous"},
        )

    def record_lesson_plan_creation(self, username: str | None, success: bool, detail: Any = None) -> None:
        self.audit.record_event(
            trace_id=username or "lesson_plan",
            event_name="lesson_plan",
            metadata={"user": username or "anonymous", "success": success, "detail": detail},
        )

    def record_chat_question(self, username: str | None, prompt_text: str | None) -> None:
        self.audit.record_event(
            trace_id=username or "chat",
            event_name="chat_question",
            metadata={
                "user": username or "anonymous",
                "prompt_len": len(prompt_text or ""),
            },
        )

    def record_doc_action(self, username: str | None, action: str, payload_len: int) -> None:
        self.audit.record_event(
            trace_id=username or "doc_ai",
            event_name="doc_ai",
            metadata={
                "user": username or "anonymous",
                "action": action,
                "payload_len": payload_len,
            },
        )

    def record_mindmap_generation(self, username: str | None, payload_len: int) -> None:
        self.audit.record_event(
            trace_id=username or "mindmap",
            event_name="mindmap_generation",
            metadata={
                "user": username or "anonymous",
                "payload_len": payload_len,
            },
        )
