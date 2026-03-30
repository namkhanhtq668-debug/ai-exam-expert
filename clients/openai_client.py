from __future__ import annotations

from typing import Any

import requests

from clients.base_llm_client import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _chat_completion(
        self,
        system_prompt: str,
        user_content: str,
        model: str,
        timeout: int,
        *,
        response_format: dict | None = None,
    ) -> dict:
        if not self.api_key:
            return {}
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": 0.6,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code >= 400:
            raise ValueError(f"OpenAI API lỗi {r.status_code}: {r.text[:300]}")
        return r.json()

    def generate_question_yccd(
        self,
        yccd_item: dict[str, Any],
        muc_do: str = "ThÃ´ng hiá»ƒu",
        *,
        context: dict[str, Any] | None = None,
    ) -> dict | None:
        raise NotImplementedError("OpenAIClient does not generate YCCD questions directly.")

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        model: str = "gpt-4o",
        timeout: int = 60,
    ) -> dict:
        data = self._chat_completion(
            system_prompt,
            user_content,
            model,
            timeout,
            response_format={"type": "json_object"},
        )
        if not data:
            return {}
        content = data["choices"][0]["message"]["content"]
        return self.parse_json_text(content)

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        safety_settings: list[dict[str, Any]] | None = None,
    ) -> str:
        if not self.api_key:
            return ""
        data = self._chat_completion(
            system_instruction or "",
            prompt,
            model="gpt-4o",
            timeout=60,
        )
        if not data:
            return ""
        content = data["choices"][0]["message"]["content"]
        return str(content or "").strip()

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        safety_settings: list[dict[str, Any]] | None = None,
    ) -> dict | None:
        if not self.api_key:
            return None
        data = self._chat_completion(
            system_instruction or "",
            prompt,
            model="gpt-4o",
            timeout=60,
            response_format={"type": "json_object"},
        )
        if not data:
            return None
        content = data["choices"][0]["message"]["content"]
        try:
            return self.parse_json_text(content)
        except Exception:
            return None
