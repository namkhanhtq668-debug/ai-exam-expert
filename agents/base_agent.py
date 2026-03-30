from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from orchestrator.agent_result import AgentResult


class BaseAgent(ABC):
    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, *args, **kwargs) -> AgentResult:
        raise NotImplementedError("Subclasses must implement the execute method.")

    def normalize_result(
        self,
        value: Any,
        *,
        status: str = "success",
        confidence: float = 0.0,
        issues: list[str] | None = None,
        next_action: str = "continue",
        metadata: dict[str, Any] | None = None,
    ) -> AgentResult:
        coerced_metadata = dict(metadata or {})
        coerced_metadata.setdefault("agent", self.name)
        return AgentResult.coerce(
            value,
            status=status,
            confidence=confidence,
            issues=issues,
            next_action=next_action,
            metadata=coerced_metadata,
        )

    def ok(
        self,
        output: Any = None,
        *,
        issues: list[str] | None = None,
        confidence: float = 1.0,
        next_action: str = "continue",
        metadata: dict[str, Any] | None = None,
    ) -> AgentResult:
        return AgentResult(
            status="success",
            output=output,
            confidence=confidence,
            issues=issues or [],
            next_action=next_action,
            metadata={**(metadata or {}), "agent": self.name},
        )

    def fail(
        self,
        issues: list[str],
        *,
        output: Any = None,
        confidence: float = 0.0,
        next_action: str = "retry",
        metadata: dict[str, Any] | None = None,
    ) -> AgentResult:
        return AgentResult(
            status="failed",
            output=output,
            confidence=confidence,
            issues=issues,
            next_action=next_action,
            metadata={**(metadata or {}), "agent": self.name},
        )
