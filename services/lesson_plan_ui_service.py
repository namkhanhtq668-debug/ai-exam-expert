from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, MutableMapping


StateMapping = MutableMapping[str, Any]


@dataclass
class LessonPlanUIService:
    state: StateMapping
    system_api_key_getter: Callable[[], str]
    extract_text_from_pdf_bytes: Callable[[bytes, int, bool], str]
    read_file_content: Callable[[Any, str], str]
    key_prefix: str = "lesson_plan"

    def key(self, name: str) -> str:
        return f"{self.key_prefix}_{name}"

    def api_key(self) -> str:
        return (self.state.get("api_key") or self.system_api_key_getter() or "").strip()

    def init_state(self) -> None:
        self.state.setdefault(self.key("html"), "")
        self.state.setdefault(self.key("title"), "GiaoAn")

    def set_html(self, html: str, title: str) -> None:
        self.state[self.key("html")] = html
        self.state[self.key("title")] = title

    def clear_html(self) -> None:
        self.state[self.key("html")] = ""

    def get_html(self) -> str:
        return str(self.state.get(self.key("html"), "") or "")

    def get_title(self) -> str:
        return str(self.state.get(self.key("title"), "GiaoAn") or "GiaoAn")

    def extract_from_upload(self, uploaded_file) -> str:
        if not uploaded_file:
            return ""
        name = (getattr(uploaded_file, "name", "") or "").lower()
        try:
            if name.endswith(".pdf"):
                pdf_bytes = uploaded_file.getvalue()
                return self.extract_text_from_pdf_bytes(pdf_bytes, max_pages=6, ocr_if_needed=True) or ""
            if name.endswith(".docx"):
                return self.read_file_content(uploaded_file, "docx") or ""
            if name.endswith(".txt"):
                return uploaded_file.getvalue().decode("utf-8", errors="ignore")
        except Exception:
            return ""
        return ""
