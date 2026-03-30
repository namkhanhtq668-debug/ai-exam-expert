from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any

from utils.json_utils import clean_json


class BaseLLMClient(ABC):
    @abstractmethod
    def generate_question_yccd(
        self,
        yccd_item: dict[str, Any],
        muc_do: str = "Thông hiểu",
        *,
        context: dict[str, Any] | None = None,
    ) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        model: str = "gpt-4o",
        timeout: int = 60,
    ) -> dict:
        raise NotImplementedError

    @staticmethod
    def parse_json_text(text: str) -> dict:
        return json.loads(clean_json(text))
