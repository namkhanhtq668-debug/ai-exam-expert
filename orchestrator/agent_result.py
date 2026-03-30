from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    status: str
    output: Any = None
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)
    next_action: str = "continue"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "confidence": self.confidence,
            "issues": list(self.issues),
            "next_action": self.next_action,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def coerce(
        cls,
        value: Any,
        *,
        status: str = "success",
        next_action: str = "continue",
        confidence: float = 0.0,
        issues: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AgentResult":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                status=value.get("status", status),
                output=value.get("output", value),
                confidence=float(value.get("confidence", confidence) or 0.0),
                issues=list(value.get("issues") or issues or []),
                next_action=value.get("next_action", next_action),
                metadata=dict(value.get("metadata") or metadata or {}),
            )
        if value is None:
            return cls(
                status=status,
                output=None,
                confidence=confidence,
                issues=list(issues or []),
                next_action=next_action,
                metadata=dict(metadata or {}),
            )
        return cls(
            status=status,
            output=value,
            confidence=confidence,
            issues=list(issues or []),
            next_action=next_action,
            metadata=dict(metadata or {}),
        )
