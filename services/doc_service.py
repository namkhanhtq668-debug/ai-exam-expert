from __future__ import annotations

from dataclasses import dataclass

from clients.base_llm_client import BaseLLMClient
from services.compliance_service import ComplianceService
from services.schema_service import SchemaService
from services.telemetry_service import TelemetryService

_TEXT_VALIDATOR = SchemaService({"type": "string", "minLength": 1})
_COMPLIANCE = ComplianceService({"type": "string", "minLength": 1})


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    valid, _ = _TEXT_VALIDATOR.validate(text)
    return text if valid else ""


@dataclass
class DocService:
    llm_client: BaseLLMClient
    telemetry: TelemetryService

    SUM_PROMPT = """Bạn là trợ lý giáo dục AI. Tóm tắt ngắn gọn tài liệu đưa vào, gồm:
- Nội dung chính (5–7 gạch đầu dòng)
- Khái niệm quan trọng
- 5 câu hỏi củng cố

Tài liệu:
{text}
"""

    QA_PROMPT = """Bạn là trợ lý AI. Chỉ trả lời dựa trên nội dung trích dẫn bên dưới.
[TRÍCH DẪN TÀI LIỆU]
{context}
[CÂU HỎI]
{question}
"""

    def summarize(self, text: str, username: str | None = None) -> str:
        prompt = self.SUM_PROMPT.format(text=text[:16000])
        response = self.llm_client.generate_text(prompt)
        self.telemetry.record_doc_action(username, "summary", len(text))
        output = _safe_text(response)
        _COMPLIANCE.soft_review_text(output, context=text, label="doc_summary")
        return output

    def answer(self, context: str, question: str, username: str | None = None) -> str:
        prompt = self.QA_PROMPT.format(context=context, question=question)
        response = self.llm_client.generate_text(prompt)
        self.telemetry.record_doc_action(username, "qa", len(question))
        output = _safe_text(response)
        _COMPLIANCE.soft_review_text(output, context={"context": context, "question": question}, label="doc_qa")
        return output
