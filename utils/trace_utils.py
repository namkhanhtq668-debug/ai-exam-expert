from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "authorization",
    "password",
    "secret",
    "token",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_sensitive_data(value: Any, sensitive_keys: set[str] | None = None) -> Any:
    keys = sensitive_keys or SENSITIVE_KEYS
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in keys:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(item, keys)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_data(item, keys) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item, keys) for item in value)
    return value


def build_trace_event(
    trace_id: str,
    event_type: str,
    *,
    agent: str | None = None,
    status: str | None = None,
    duration_ms: float | None = None,
    attempt: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "trace_id": trace_id,
        "event_type": event_type,
    }
    if agent is not None:
        event["agent"] = agent
    if status is not None:
        event["status"] = status
    if duration_ms is not None:
        event["duration_ms"] = round(float(duration_ms), 3)
    if attempt is not None:
        event["attempt"] = attempt
    if payload is not None:
        event["payload"] = redact_sensitive_data(payload)
    return event
