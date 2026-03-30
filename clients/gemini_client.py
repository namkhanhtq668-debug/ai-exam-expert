from __future__ import annotations

from typing import Any

import google.generativeai as genai

from clients.base_llm_client import BaseLLMClient
from prompts.yccd_prompts import YCCD_SAFE_SETTINGS, build_yccd_question_prompt


class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model_name = model_name
        if api_key:
            genai.configure(api_key=api_key)

    def generate_question_yccd(
        self,
        yccd_item: dict[str, Any],
        muc_do: str = "Thông hiểu",
        *,
        context: dict[str, Any] | None = None,
    ) -> dict | None:
        if not yccd_item:
            return None

        try:
            return self.generate_json(
                prompt=build_yccd_question_prompt(yccd_item, muc_do, context=context),
                system_instruction=None,
                safety_settings=YCCD_SAFE_SETTINGS,
            )
        except Exception:
            return None

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        model: str = "gpt-4o",
        timeout: int = 60,
    ) -> dict:
        if not self.api_key:
            return {}
        model_obj = genai.GenerativeModel(model, system_instruction=system_prompt)
        res = model_obj.generate_content(
            user_content,
            generation_config={"response_mime_type": "application/json"},
        )
        return self.parse_json_text(res.text)

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        safety_settings: list[dict[str, Any]] | None = None,
    ) -> str:
        if not self.api_key:
            return ""
        model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction) if system_instruction else genai.GenerativeModel(self.model_name)
        res = model.generate_content(prompt, safety_settings=safety_settings)
        return (res.text or "").strip()

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        safety_settings: list[dict[str, Any]] | None = None,
    ) -> dict | None:
        if not self.api_key:
            return None
        model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction) if system_instruction else genai.GenerativeModel(self.model_name)
        res = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
            safety_settings=safety_settings,
        )
        try:
            return self.parse_json_text(res.text)
        except Exception:
            return None
