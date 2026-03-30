from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from supabase import create_client

from utils.trace_utils import build_trace_event

class AuditService:
    def __init__(self, supabase_url=None, supabase_key=None, log_file="audit_logs.jsonl", enabled: bool = True):
        env_enabled = os.getenv("AI_EXAM_AUDIT_ENABLED")
        if env_enabled is not None:
            enabled = env_enabled.strip().lower() not in {"0", "false", "no", "off"}
        env_log_file = os.getenv("AI_EXAM_AUDIT_LOG_FILE")
        if env_log_file:
            log_file = env_log_file
        supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        supabase_key = supabase_key or os.getenv("SUPABASE_KEY")
        self.supabase_client = None
        if supabase_url and supabase_key:
            self.supabase_client = create_client(supabase_url, supabase_key)
        self.log_file = Path(log_file)
        self.enabled = enabled
        self.logger = logging.getLogger("AuditService")

    def _write_jsonl(self, log_entry: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def log_to_file(self, log_entry: dict[str, Any]) -> None:
        self._write_jsonl(log_entry)

    def log_to_supabase(self, log_entry: dict[str, Any]) -> None:
        if self.supabase_client and self.enabled:
            try:
                self.supabase_client.table("audit_logs").insert(log_entry).execute()
            except Exception as e:
                self.logger.error(f"Failed to log to Supabase: {e}")

    def record_event(self, trace_id: str, event_type: str, **payload: Any) -> dict[str, Any]:
        event = build_trace_event(trace_id, event_type, payload=payload or None)
        self.log_to_file(event)
        self.log_to_supabase(event)
        self.logger.info("%s trace=%s", event_type, trace_id)
        return event

    def record_agent_step(
        self,
        trace_id: str,
        agent: str,
        status: str | None = None,
        *,
        duration_ms: float | None = None,
        attempt: int | None = None,
        confidence: float | None = None,
        issues: list[str] | None = None,
        next_action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if confidence is not None:
            payload["confidence"] = confidence
        if issues is not None:
            payload["issues"] = issues
        if next_action is not None:
            payload["next_action"] = next_action
        if metadata is not None:
            payload["metadata"] = metadata
        event = build_trace_event(
            trace_id,
            "agent_step",
            agent=agent,
            status=status,
            duration_ms=duration_ms,
            attempt=attempt,
            payload=payload or None,
        )
        self.log_to_file(event)
        self.log_to_supabase(event)
        self.logger.info("agent_step trace=%s agent=%s status=%s", trace_id, agent, status or "unknown")
        return event

    def record_run(self, trace_id: str, status: str, *, attempts: int, duration_ms: float | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"attempts": attempts}
        if errors:
            payload["errors"] = errors
        event = build_trace_event(
            trace_id,
            "run",
            status=status,
            duration_ms=duration_ms,
            payload=payload,
        )
        self.log_to_file(event)
        self.log_to_supabase(event)
        self.logger.info("run trace=%s status=%s attempts=%s", trace_id, status, attempts)
        return event

    def record_exception(self, trace_id: str, agent: str, error: Exception | str, *, stage: str | None = None, duration_ms: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": str(error)}
        if stage is not None:
            payload["stage"] = stage
        event = build_trace_event(
            trace_id,
            "agent_error",
            agent=agent,
            status="failed",
            duration_ms=duration_ms,
            payload=payload,
        )
        self.log_to_file(event)
        self.log_to_supabase(event)
        self.logger.error("agent_error trace=%s agent=%s error=%s", trace_id, agent, error)
        return event
