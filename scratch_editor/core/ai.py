"""Gemini client wrapper – key nhập trong UI khi dùng.

Không tự đọc env (theo lựa chọn của giáo viên), nhưng cho phép get_default_key()
trả về ENV nếu có – chỉ dùng làm gợi ý điền sẵn vào ô nhập.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional


class AIConfigError(Exception):
    pass


class AIRequestError(Exception):
    pass


@dataclass
class AIConfig:
    api_key: str = ""
    model: str = "gemini-3.5-flash-lite"
    temperature: float = 0.4
    max_output_tokens: int = 4096

    def is_ready(self) -> bool:
        return bool(self.api_key.strip())


def get_default_key_hint() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


class GeminiClient:
    """Client mỏng quanh google.generativeai – chịu lỗi mạng, parse JSON an toàn."""

    def __init__(self, config: AIConfig):
        if not config.is_ready():
            raise AIConfigError("Chưa nhập GEMINI_API_KEY trong UI.")
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:
            raise AIConfigError(
                "Thiếu thư viện 'google-generativeai'. "
                "Cài bằng: pip install google-generativeai"
            ) from e
        self._genai = genai
        self.config = config
        genai.configure(api_key=config.api_key)
        self._model = genai.GenerativeModel(config.model)

    # ---------- chat ----------
    def generate(self, prompt: str, *, system: str | None = None,
                 retries: int = 2) -> str:
        full = prompt if not system else f"{system}\n\n---\n\n{prompt}"
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                resp = self._model.generate_content(
                    full,
                    generation_config={
                        "temperature": self.config.temperature,
                        "max_output_tokens": self.config.max_output_tokens,
                    },
                )
                text = getattr(resp, "text", None)
                if not text:
                    # đôi khi text rỗng do safety block
                    raise AIRequestError("Gemini trả về rỗng (có thể bị chặn nội dung).")
                return text
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    raise AIRequestError(f"Gọi Gemini thất bại: {e}") from e
        raise AIRequestError(str(last_err) if last_err else "unknown error")

    def generate_json(self, prompt: str, *, system: str | None = None) -> Any:
        """Yêu cầu model trả JSON, tự bóc ```json fence và parse."""
        text = self.generate(prompt, system=system)
        return parse_json_loose(text)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


def parse_json_loose(text: str) -> Any:
    """Bóc fence + cắt khoảng trắng, parse JSON. Ném ValueError nếu thất bại."""
    if not text:
        raise ValueError("Phản hồi rỗng")
    m = _JSON_FENCE.search(text)
    payload = m.group(1).strip() if m else text.strip()
    # cắt phần trước/sau cặp { } / [ ] đầu tiên/cuối cùng
    if not (payload.startswith("{") or payload.startswith("[")):
        first = min((i for i in (payload.find("{"), payload.find("[")) if i >= 0),
                    default=-1)
        if first >= 0:
            payload = payload[first:]
    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"Không parse được JSON: {e}\nNội dung:\n{payload[:500]}")
