from __future__ import annotations

from dataclasses import dataclass

from clients.base_llm_client import BaseLLMClient
from services.lesson_plan_service import (
    generate_lesson_plan_data_only as _generate_data_only,
    generate_lesson_plan_html_simple as _generate_html_simple,
)
from services.telemetry_service import TelemetryService


@dataclass
class LessonPlanGenerationService:
    llm_client: BaseLLMClient
    telemetry: TelemetryService

    def generate_html(
        self,
        cap_hoc: str,
        mon: str,
        lop: str,
        bo_sach: str,
        tuan: int,
        tiet: int,
        ten_bai: str,
        thoi_luong: int,
        si_so: int,
        lesson_context: str,
        teacher_note: str,
        username: str | None = None,
    ) -> str:
        html = _generate_html_simple(
            self.llm_client,
            cap_hoc=cap_hoc,
            mon=mon,
            lop=lop,
            bo_sach=bo_sach,
            tuan=tuan,
            tiet=tiet,
            ten_bai=ten_bai,
            thoi_luong=thoi_luong,
            si_so=si_so,
            lesson_context=lesson_context,
            teacher_note=teacher_note,
        )
        self.telemetry.record_lesson_plan_creation(username, True, {"module": "lesson_plan", "ten_bai": ten_bai})
        return html

    def generate_data(
        self,
        meta_ppct: dict,
        teacher_note: str,
        username: str | None = None,
    ) -> dict:
        data = _generate_data_only(self.llm_client, meta_ppct, teacher_note)
        self.telemetry.record_lesson_plan_creation(username, True, {"module": "lesson_plan_data"})
        return data
