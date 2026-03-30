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
class MindmapService:
    llm_client: BaseLLMClient
    telemetry: TelemetryService

    BASE_PROMPT = """Bạn là trợ lý AI tạo sơ đồ tư duy dạng Markdown cây cho giáo viên.
Yêu cầu:
- Có đúng 1 tiêu đề dạng `# Chủ đề`
- Tối đa 4 nhánh chính, mỗi nhánh 2-4 ý phụ
- Dùng từ khóa ngắn gọn (3-6 từ)
- Không dùng câu hỏi bắt đầu bằng Vì sao/Ai/Khi nào
- Kết thúc bằng dòng `Gợi ý sử dụng: ...`
Phong cách: {style}
Mục đích: {goal}

Nội dung nhập:
{content}
"""

    def create(self, content: str, *, style: str, goal: str, username: str | None = None) -> str:
        prompt = self.BASE_PROMPT.format(style=style, goal=goal, content=content[:12000])
        response = self.llm_client.generate_text(prompt)
        self.telemetry.record_mindmap_generation(username, len(content))
        output = _safe_text(response)
        _COMPLIANCE.soft_review_text(output, context=content, expected_topics=[style, goal], label="mindmap")
        return output
