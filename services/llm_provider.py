from __future__ import annotations

from os import getenv
from typing import Optional

from clients.base_llm_client import BaseLLMClient
from clients.gemini_client import GeminiClient
from clients.openai_client import OpenAIClient

DEFAULT_LLM_PROVIDER = "gemini"


class _MissingKeyLLMClient(BaseLLMClient):
    def __init__(self, provider: str, model_name: str):
        self.provider = provider
        self.model_name = model_name

    def generate_question_yccd(
        self,
        yccd_item: dict[str, Any],
        muc_do: str = "ThÃ´ng hiá»ƒu",
        *,
        context: dict[str, Any] | None = None,
    ) -> dict | None:
        return None

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        model: str = "gpt-4o",
        timeout: int = 60,
    ) -> dict:
        return {}

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        safety_settings: list[dict[str, Any]] | None = None,
    ) -> str:
        return ""

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        safety_settings: list[dict[str, Any]] | None = None,
    ) -> dict | None:
        return None


def _resolve_default_provider() -> str:
    return (getenv("AI_EXAM_LLM_PROVIDER") or DEFAULT_LLM_PROVIDER).strip().lower()


def _provider_default_api_key(provider: str) -> str:
    if provider == "openai":
        return (getenv("OPENAI_API_KEY") or "").strip()
    return (getenv("GOOGLE_API_KEY") or "").strip()


def build_llm_client(
    api_key: Optional[str],
    *,
    provider: Optional[str] = None,
    model_name: str = "gemini-2.0-flash",
) -> BaseLLMClient:
    """Construct the requested LLM client (Gemini by default)."""
    selected = (provider or _resolve_default_provider() or DEFAULT_LLM_PROVIDER).strip().lower()
    resolved_key = (api_key or "").strip() or _provider_default_api_key(selected)
    if not resolved_key:
        return _MissingKeyLLMClient(selected, model_name)
    if selected == "openai":
        return OpenAIClient(resolved_key)
    return GeminiClient(resolved_key, model_name=model_name)
