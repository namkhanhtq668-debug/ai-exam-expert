from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator


class SchemaService:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema
        self.validator = Draft202012Validator(schema)

    def validate(self, data: Any) -> tuple[bool, list[str]]:
        errors = [err.message for err in self.validator.iter_errors(data)]
        return (len(errors) == 0, errors)

