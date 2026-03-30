from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from orchestrator.agent_result import AgentResult
from orchestrator.routing_rules import can_transition


@dataclass
class WorkflowState:
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    stage: str = "initialized"
    request: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempt_count: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None

    def advance(self, next_stage: str, *, actor: str | None = None, action: str | None = None, detail: dict[str, Any] | None = None) -> None:
        if not can_transition(self.stage, next_stage):
            raise ValueError(f"Invalid workflow transition: {self.stage} -> {next_stage}")

        self.stage = next_stage
        self.transitions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": self.transitions[-1]["to"] if self.transitions else "initialized",
            "to": next_stage,
            "actor": actor,
            "action": action,
            "detail": dict(detail or {}),
            "trace_id": self.trace_id,
        })

    def record(self, agent_name: str, result: Any, *, duration_ms: float | None = None) -> None:
        if isinstance(result, AgentResult):
            normalized = result.to_dict()
        elif isinstance(result, dict):
            normalized = dict(result)
        else:
            normalized = {
                "status": getattr(result, "status", None),
                "confidence": getattr(result, "confidence", None),
                "issues": list(getattr(result, "issues", []) or []),
                "next_action": getattr(result, "next_action", None),
                "metadata": dict(getattr(result, "metadata", {}) or {}),
                "output": getattr(result, "output", None),
            }

        status = normalized.get("status")
        confidence = normalized.get("confidence")
        issues = list(normalized.get("issues") or [])
        next_action = normalized.get("next_action")
        metadata = dict(normalized.get("metadata") or {})

        self.history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "stage": self.stage,
            "status": status,
            "confidence": confidence,
            "issues": issues,
            "next_action": next_action,
            "duration_ms": duration_ms,
            "trace_id": self.trace_id,
            "metadata": metadata,
            "result": normalized,
        })

    def finish(self, success: bool = True) -> None:
        target_stage = "finalized" if success else "failed"
        if self.stage != target_stage:
            self.advance(target_stage, actor="orchestrator", action="finish")
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def duration_ms(self) -> float | None:
        if not self.started_at:
            return None
        started = datetime.fromisoformat(self.started_at)
        finished = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now(timezone.utc)
        return max(0.0, (finished - started).total_seconds() * 1000.0)

    def summary(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "stage": self.stage,
            "attempts": self.attempt_count,
            "history_count": len(self.history),
            "transition_count": len(self.transitions),
            "error_count": len(self.errors),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": round(self.duration_ms(), 3) if self.duration_ms() is not None else None,
            "success": self.stage == "finalized",
        }
