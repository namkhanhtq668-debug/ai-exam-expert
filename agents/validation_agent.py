from agents.base_agent import BaseAgent
from services.schema_service import SchemaService

class ValidationAgent(BaseAgent):
    def __init__(self, schema):
        super().__init__()
        self.schema_service = SchemaService(schema)

    def execute(self, data):
        """
        Validates the given data against the provided JSON schema.

        Args:
            data (dict): The data to validate.

        Returns:
            AgentResult: validation status and schema issues.
        """
        try:
            valid, errors = self.schema_service.validate(data)
            semantic_issues: list[str] = []
            payload = dict(data or {}) if isinstance(data, dict) else {}

            question = str(payload.get("question", "")).strip()
            options = list(payload.get("options") or [])
            answer = str(payload.get("answer", "")).strip().upper()
            if not question:
                semantic_issues.append("Thiếu nội dung câu hỏi.")
            if len(options) != 4:
                semantic_issues.append("Cần đúng 4 lựa chọn trả lời.")
            if options and any(not str(option).strip() for option in options):
                semantic_issues.append("Lựa chọn không được để trống.")
            if answer and answer not in {"A", "B", "C", "D"}:
                semantic_issues.append("Đáp án phải thuộc A/B/C/D.")

            if valid and not semantic_issues:
                return self.ok(data, confidence=1.0, metadata={"agent": self.name, "schema_valid": True})

            all_issues = list(errors) + semantic_issues
            next_action = "retry"
            if semantic_issues and not errors:
                next_action = "refine"

            return self.fail(
                all_issues,
                output=data,
                next_action=next_action,
                metadata={
                    "agent": self.name,
                    "schema_valid": bool(valid),
                    "semantic_issues": semantic_issues,
                },
            )
        except Exception as exc:
            return self.fail([str(exc)], output=data, next_action="retry", metadata={"agent": self.name})
