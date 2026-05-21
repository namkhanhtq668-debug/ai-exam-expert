# -*- coding: utf-8 -*-
"""
Pipeline — orchestrate 5 module thành 1 flow duy nhất.

Flow:
    LessonContext (do CODE cấp)
    → prompt_builder.build_lesson_prompt()      [tạo prompt cho AI]
    → AI gọi (Gemini/OpenAI) -> raw response
    → prompt_builder.parse_json_response()      [parse JSON]
    → validator.validate_lesson_plan()          [check schema + phrase cấm]
    → normalizer.normalize_lesson_plan()        [làm sạch text]
    → renderer.render_lesson_docx()             [render DOCX]
    → bytes file .docx

Public API chính:
    - generate_docx_from_ai_response(ctx, raw_ai_text) -> PipelineResult
        Chain hoàn chỉnh từ output AI → DOCX bytes.
    - generate_docx_from_data(data) -> PipelineResult
        Bỏ qua AI, dùng JSON có sẵn (cho fixture/test/sample).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .normalizer import normalize_lesson_plan
from .prompt_builder import LessonContext, build_lesson_prompt, parse_json_response
from .renderer import render_lesson_docx
from .reviewer import review_lesson_plan
from .validator import validate_lesson_plan


@dataclass
class PipelineResult:
    ok: bool = False
    docx_bytes: Optional[bytes] = None
    json_data: Optional[Dict[str, Any]] = None       # JSON sau review (truyền vào renderer)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    replaced_phrases: List[str] = field(default_factory=list)
    review_fixes: List[str] = field(default_factory=list)   # 🆕 các sửa từ reviewer
    stage: str = ""                                   # parse/validate/normalize/review/render

    def summary(self) -> str:
        if self.ok:
            base = f"✅ Render OK ({len(self.docx_bytes or b'')} bytes)"
            extras = []
            if self.warnings:
                extras.append(f"⚠️ {len(self.warnings)} cảnh báo")
            if self.replaced_phrases:
                extras.append(f"🧹 thay {len(self.replaced_phrases)} phrase cấm (normalize)")
            if self.review_fixes:
                extras.append(f"🔧 {len(self.review_fixes)} chỉnh sửa (review)")
            return base + (" — " + ", ".join(extras) if extras else "")
        return f"❌ Fail ở stage '{self.stage}': " + "; ".join(self.errors[:3])


# ============================================================================
# Build prompt only (helper cho caller cần gọi AI riêng)
# ============================================================================

def build_prompt(ctx: LessonContext) -> str:
    """Wrapper tiện lợi để build prompt từ context."""
    return build_lesson_prompt(ctx)


# ============================================================================
# Pipeline chính
# ============================================================================

def generate_docx_from_ai_response(
    ctx: LessonContext,
    raw_ai_text: str,
) -> PipelineResult:
    """Chain hoàn chỉnh: output AI thô → DOCX bytes.

    Args:
        ctx: ngữ cảnh bài học (để check thời lượng khớp).
        raw_ai_text: text AI trả về (có thể có markdown code fence).

    Returns:
        PipelineResult với docx_bytes nếu OK, hoặc errors nếu fail.
    """
    result = PipelineResult()

    # 1. Parse JSON
    result.stage = "parse"
    data = parse_json_response(raw_ai_text)
    if data is None:
        result.errors.append("AI không trả về JSON hợp lệ (parse fail).")
        return result

    # 2. Validate
    result.stage = "validate"
    val = validate_lesson_plan(data, expected_duration_minutes=ctx.duration_minutes)
    if not val.ok:
        result.errors.extend(val.errors)
        result.warnings.extend(val.warnings)
        return result
    result.warnings.extend(val.warnings)

    # 3. Normalize
    result.stage = "normalize"
    norm = normalize_lesson_plan(data)
    result.replaced_phrases = norm.replaced_phrases
    cleaned = norm.data

    # 4. Re-validate sau normalize (đảm bảo không còn phrase cấm)
    val2 = validate_lesson_plan(cleaned, expected_duration_minutes=ctx.duration_minutes)
    if val2.banned_phrases_found:
        result.errors.append(
            "Sau normalize vẫn còn phrase cấm: " + ", ".join(val2.banned_phrases_found)
        )
        return result

    # 5. 🆕 Review — kiểm + chỉnh trước khi render (deterministic heuristic)
    result.stage = "review"
    rev = review_lesson_plan(cleaned)
    result.review_fixes = rev.fixes_applied
    polished = rev.data

    # 6. Render
    result.stage = "render"
    try:
        docx_bytes = render_lesson_docx(polished)
    except Exception as e:
        result.errors.append(f"Renderer fail: {type(e).__name__}: {e}")
        return result

    result.ok = True
    result.docx_bytes = docx_bytes
    result.json_data = polished
    return result


def generate_docx_from_data(
    data: Dict[str, Any],
    expected_duration_minutes: Optional[int] = None,
) -> PipelineResult:
    """Bỏ qua AI — dùng JSON có sẵn (cho fixture/test).

    Vẫn chạy qua validate → normalize → review để đảm bảo output sạch.
    """
    result = PipelineResult()

    result.stage = "validate"
    val = validate_lesson_plan(data, expected_duration_minutes=expected_duration_minutes)
    if not val.ok:
        result.errors.extend(val.errors)
        result.warnings.extend(val.warnings)
        return result
    result.warnings.extend(val.warnings)

    result.stage = "normalize"
    norm = normalize_lesson_plan(data)
    result.replaced_phrases = norm.replaced_phrases

    # 🆕 Review
    result.stage = "review"
    rev = review_lesson_plan(norm.data)
    result.review_fixes = rev.fixes_applied

    result.stage = "render"
    try:
        docx_bytes = render_lesson_docx(rev.data)
    except Exception as e:
        result.errors.append(f"Renderer fail: {type(e).__name__}: {e}")
        return result

    result.ok = True
    result.docx_bytes = docx_bytes
    result.json_data = rev.data
    return result


# ============================================================================
# Sample loader (tiện lợi cho test/demo)
# ============================================================================

_SAMPLES_DIR = Path(__file__).parent / "samples"


def load_sample(name: str) -> Dict[str, Any]:
    """Load 1 sample JSON theo tên (không cần đuôi .json).

    Available samples:
        - 'toan_4_on_tap' — Bài 1. Ôn tập các số đến 100 000
    """
    path = _SAMPLES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Sample '{name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Sample '{name}' không phải JSON object.")
    return data


def list_samples() -> List[str]:
    """Liệt kê tên các sample có sẵn."""
    if not _SAMPLES_DIR.exists():
        return []
    return sorted(p.stem for p in _SAMPLES_DIR.glob("*.json"))
