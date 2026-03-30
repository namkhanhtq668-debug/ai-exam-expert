from __future__ import annotations

import json
import re
from typing import Any

from services.compliance_service import ComplianceService
from services.schema_service import SchemaService


LESSON_PLAN_SAFE_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

_TEXT_VALIDATOR = SchemaService({"type": "string", "minLength": 1})
_LESSON_DATA_VALIDATOR = SchemaService(
    {
        "type": "object",
        "properties": {
            "meta": {"type": "object"},
            "sections": {"type": "object"},
        },
        "required": ["meta", "sections"],
        "additionalProperties": True,
    }
)
_COMPLIANCE = ComplianceService({"type": "object"})


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    valid, _ = _TEXT_VALIDATOR.validate(text)
    return text if valid else ""


def _safe_lesson_data(meta: dict[str, Any], sections: object) -> dict[str, Any]:
    payload = {"meta": meta, "sections": sections if isinstance(sections, dict) else {}}
    valid, _ = _LESSON_DATA_VALIDATOR.validate(payload)
    return payload if valid else {"meta": meta, "sections": {}}


def clean_json(text: str) -> str:
    text = (text or "").strip()
    if "```" in text:
        parts = re.split(r"```(?:json)?", text)
        if len(parts) > 1:
            text = parts[1]

    start_idx = text.find("{")
    if start_idx == -1:
        return "{}"
    text = text[start_idx:]

    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text)
        return json.dumps(obj)
    except Exception:
        end_idx = text.rfind("}")
        if end_idx != -1:
            return text[: end_idx + 1]
        return text


def build_lesson_system_prompt_data_only(meta: dict[str, Any], teacher_note: str) -> str:
    return f"""
Báº¡n lÃ  GIÃO VIÃŠN TIá»‚U Há»ŒC cá»‘t cÃ¡n, soáº¡n Káº¾ HOáº CH BÃ€I Dáº Y theo CTGDPT 2018 (CV 2345/BGDÄT-GDTH).
NHIá»†M Vá»¤:
- Báº¡n sáº½ nháº­n INPUT lÃ  1 JSON cÃ³ trÆ°á»ng meta (thÃ´ng tin bÃ i) vÃ  note (ghi chÃº GV).
- Báº¡n pháº£i tráº£ vá» DUY NHáº¤T 1 JSON há»£p lá»‡, KHÃ”NG kÃ¨m chá»¯ giáº£i thÃ­ch.
YÃŠU Cáº¦U CHáº¤T LÆ¯á»¢NG (Ráº¤T QUAN TRá»ŒNG):
- Viáº¿t ÄÃšNG NGHIá»†P Vá»¤ SÆ¯ PHáº M, khÃ´ng viáº¿t khung chung chung.
- Cáº¤M cÃ¡c cá»¥m: "Bá»• sung ná»™i dung", "BÆ°á»›c 1/2", "Nhiá»‡m vá»¥ 1/2", "Tá»• chá»©c bÆ°á»›c...".
- Pháº§n III pháº£i cÃ³ Ná»˜I DUNG Dáº Y - Há»ŒC THáº¬T: bÃ i táº­p/vÃ­ dá»¥/cÃ¢u há»i, sáº£n pháº©m HS (báº£ng con/vá»Ÿ/phiáº¿u), lá»i gá»£i má»Ÿ GV.
- Náº¿u lÃ  TOÃN: báº¯t buá»™c cÃ³ tá»‘i thiá»ƒu 2 má»¥c "BÃ i 1/2/..." hoáº·c "VÃ­ dá»¥..." vÃ  cÃ³ sá»‘ liá»‡u/phÃ©p tÃ­nh cá»¥ thá»ƒ (vd: 12,5 - 3,7; 4,2 Ã— 0,5).
Cáº¤U TRÃšC Báº®T BUá»˜C:
Tráº£ vá» JSON cÃ³ dáº¡ng:
{{
  "sections": {{
    "I": {{
      "yeu_cau_can_dat": [... >=5 Ã½ ...],
      "nang_luc": [... >=3 Ã½ ...],
      "pham_chat": [... >=2 Ã½ ...],
      "nang_luc_dac_thu": [... >=2 Ã½ ...],
      "nang_luc_so": [... >=1 Ã½ ...]
    }},
    "II": {{
      "giao_vien": [... >=6 Ã½ ...],
      "hoc_sinh": [... >=6 Ã½ ...]
    }},
    "III": {{
      "bang": [
        {{"kieu":"header", "tieu_de":"1. Khá»Ÿi Ä‘á»™ng:"}},
        {{"kieu":"row", "thoi_gian":4, "giao_vien":"...", "hoc_sinh":"..."}},
        {{"kieu":"header", "tieu_de":"2. Luyá»‡n táº­p:"}},
        {{"kieu":"row", "thoi_gian":10, "giao_vien":"...", "hoc_sinh":"BÃ i 1: ..."}}
      ]
    }},
    "IV": {{
      "dieu_chinh_sau_bai_day": "... (Ä‘á»ƒ dÃ²ng cháº¥m cho GV ghi hoáº·c gá»£i Ã½ 3 Ã½) ..."
    }}
  }}
}}
QUY Táº®C Báº¢NG (III.bang):
- bang lÃ  Báº¢NG 2 Cá»˜T (GV/HS), nhÆ°ng tráº£ vá» dáº¡ng JSON Ä‘á»ƒ há»‡ thá»‘ng render.
- kieu="header": chá»‰ dÃ¹ng Ä‘á»ƒ ngÄƒn cÃ¡ch hoáº¡t Ä‘á»™ng lá»›n (Khá»Ÿi Ä‘á»™ng/KhÃ¡m phÃ¡-HÃ¬nh thÃ nh/Luyá»‡n táº­p/Váº­n dá»¥ng).
- kieu="row": pháº£i cÃ³ giao_vien vÃ  hoc_sinh viáº¿t Cá»¤ THá»‚ (cÃ³ cÃ¢u há»i, nhiá»‡m vá»¥, sáº£n pháº©m).
- Tá»•ng sá»‘ dÃ²ng bang tá»‘i thiá»ƒu 10 (khÃ´ng tÃ­nh header), Æ°u tiÃªn 12â€“18 dÃ²ng tuá»³ bÃ i.
- thoi_gian: phÃºt cá»§a dÃ²ng (1â€“10). Tá»•ng cá»™ng xáº¥p xá»‰ meta.thoi_luong.
Bá»I Cáº¢NH BÃ€I Dáº Y:
- Cáº¥p há»c: {meta.get('cap_hoc')}
- MÃ´n: {meta.get('mon')}
- Lá»›p: {meta.get('lop')}
- Bá»™ sÃ¡ch: {meta.get('bo_sach')}
- TÃªn bÃ i: {meta.get('ten_bai')}
- PPCT: {meta.get('ppct')}
GHI CHÃš GV (náº¿u cÃ³): {teacher_note}
Chá»‰ tráº£ JSON há»£p lá»‡.
""".strip()


def generate_lesson_plan_data_only(
    llm_client: Any,
    meta_ppct: dict[str, Any],
    teacher_note: str,
    model_name: str = "gemini-2.0-flash",
) -> dict[str, Any]:
    req_meta = {
        "cap_hoc": meta_ppct.get("cap_hoc", ""),
        "mon": meta_ppct.get("mon", ""),
        "lop": meta_ppct.get("lop", ""),
        "bo_sach": meta_ppct.get("bo_sach", ""),
        "ppct": meta_ppct.get("ppct", {}) or {},
        "ten_bai": meta_ppct.get("ten_bai", ""),
        "thoi_luong": int(meta_ppct.get("thoi_luong", 40) or 40),
        "si_so": int(meta_ppct.get("si_so", 35) or 35),
    }
    system_prompt = build_lesson_system_prompt_data_only(req_meta, teacher_note)
    base_req = {"meta": req_meta, "note": teacher_note}
    raw = llm_client.generate_json(
        json.dumps(base_req, ensure_ascii=False),
        system_instruction=system_prompt,
        safety_settings=LESSON_PLAN_SAFE_SETTINGS,
    )
    if raw is None or not isinstance(raw, dict):
        raw = {}
    payload = _safe_lesson_data(req_meta, raw.get("sections", {}))
    _COMPLIANCE.soft_review_payload(
        payload,
        context=req_meta,
        expected_topics=[req_meta.get("ten_bai", ""), req_meta.get("mon", ""), req_meta.get("lop", ""), req_meta.get("cap_hoc", "")],
        required_sections=["I", "II", "III", "IV"],
        label="lesson_plan_json",
    )
    return payload


def generate_lesson_plan_html_simple(
    llm_client: Any,
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
    model_name: str = "gemini-2.0-flash",
) -> str:
    system_instruction = """Báº¡n lÃ  GIÃO VIÃŠN cá»‘t cÃ¡n, chuyÃªn soáº¡n Káº¾ HOáº CH BÃ€I Dáº Y theo CTGDPT 2018.
YÃŠU Cáº¦U Báº®T BUá»˜C:
- Äáº¦U RA: CHá»ˆ TRáº¢ Vá»€ 01 KHá»I HTML HOÃ€N CHá»ˆNH (khÃ´ng markdown, khÃ´ng giáº£i thÃ­ch).
- Font: Times New Roman, cá»¡ 13pt; in A4 Ä‘áº¹p.
- CÃ³ 4 pháº§n:
  I. YÃªu cáº§u cáº§n Ä‘áº¡t (Kiáº¿n thá»©c/KÄ© nÄƒng; NÄƒng lá»±c; Pháº©m cháº¥t; NÄƒng lá»±c Ä‘áº·c thÃ¹ náº¿u cÃ³; NÄƒng lá»±c sá»‘ náº¿u phÃ¹ há»£p).
  II. Äá»“ dÃ¹ng dáº¡y â€“ há»c (GV/HS).
  III. CÃ¡c hoáº¡t Ä‘á»™ng dáº¡y â€“ há»c chá»§ yáº¿u: Báº®T BUá»˜C lÃ  <table border="1"> 2 cá»™t:
      Cá»™t 1: Hoáº¡t Ä‘á»™ng cá»§a GiÃ¡o viÃªn
      Cá»™t 2: Hoáº¡t Ä‘á»™ng cá»§a Há»c sinh
     Chia 3 hoáº¡t Ä‘á»™ng lá»›n: Khá»Ÿi Ä‘á»™ng; KhÃ¡m phÃ¡/HÃ¬nh thÃ nh kiáº¿n thá»©c; Luyá»‡n táº­p/Váº­n dá»¥ng.
     VIáº¾T CHI TIáº¾T: cÃ¢u há»i gá»£i má»Ÿ, vÃ­ dá»¥ minh há»a, bÃ i táº­p cá»¥ thá»ƒ, dá»± kiáº¿n Ä‘Ã¡p Ã¡n/nháº­n xÃ©t.
  IV. Äiá»u chá»‰nh sau bÃ i dáº¡y: Ä‘á»ƒ dÃ²ng cháº¥m.
- KHÃ”NG dÃ¹ng cÃ¡c cá»¥m 'BÆ°á»›c 1/2', 'Nhiá»‡m vá»¥ 1/2', 'Bá»• sung ná»™i dung' chung chung.
- Náº¿u cÃ³ Ná»˜I DUNG BÃ€I Há»ŒC tá»« file (PDF/DOCX): pháº£i bÃ¡m sÃ¡t thuáº­t ngá»¯, vÃ­ dá»¥, bÃ i táº­p trong Ä‘Ã³. KhÃ´ng tá»± bá»‹a ngoÃ i tÃ i liá»‡u trá»« khi ghi chÃº GV yÃªu cáº§u.
"""
    lesson_context = (lesson_context or "").strip()
    ctx_block = ""
    if lesson_context:
        ctx_block = "\n\n[Ná»˜I DUNG BÃ€I Há»ŒC TRÃCH Tá»ª TÃ€I LIá»†U GV Táº¢I LÃŠN â€“ Æ¯U TIÃŠN BÃM SÃT]\n" + lesson_context[:12000]
    prompt = f"""THÃ”NG TIN BÃ€I Dáº Y:
- Cáº¥p há»c: {cap_hoc}
- MÃ´n: {mon}
- Lá»›p: {lop}
- Bá»™ sÃ¡ch: {bo_sach}
- Tuáº§n/Tiáº¿t (PPCT): {tuan}/{tiet}
- TÃªn bÃ i: {ten_bai}
- Thá»i lÆ°á»£ng: {thoi_luong} phÃºt
- SÄ© sá»‘: {si_so}
GHI CHÃš/ÄIá»€U CHá»ˆNH Cá»¦A GV:
{teacher_note.strip() if teacher_note else "(KhÃ´ng cÃ³)"}
{ctx_block}
HÃƒY SOáº N GIÃO ÃN HTML HOÃ€N CHá»ˆNH THEO ÄÃšNG YÃŠU Cáº¦U.
"""
    html = _safe_text(
        llm_client.generate_text(
            prompt,
            system_instruction=system_instruction,
            safety_settings=LESSON_PLAN_SAFE_SETTINGS,
        )
    )
    if "```" in html:
        parts = re.split(r"```(?:html)?", html)
        if len(parts) >= 2:
            html = parts[1].strip()
    if "<html" not in html.lower():
        html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"/>
<style>
  @page {{ size: 21cm 29.7cm; margin: 2cm; }}
  body{{font-family:'Times New Roman',serif;font-size:13pt;line-height:1.35;color:#111;}}
  table{{width:100%;border-collapse:collapse;table-layout:fixed;}}
  td,th{{border:1px solid #000;padding:6px;vertical-align:top;word-wrap:break-word;}}
  th{{text-align:center;font-weight:700;background:#f2f2f2;}}
  h1{{text-align:center;font-size:18pt;margin:0 0 10px 0;}}
  h2{{font-size:14pt;margin:12px 0 6px 0;}}
</style>
</head><body>
{html}
</body></html>"""
    output = _safe_text(html) or "<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\"></head><body></body></html>"
    _COMPLIANCE.soft_review_text(
        output,
        context={
            "cap_hoc": cap_hoc,
            "mon": mon,
            "lop": lop,
            "bo_sach": bo_sach,
            "ten_bai": ten_bai,
            "lesson_context": lesson_context,
            "teacher_note": teacher_note,
        },
        expected_topics=[ten_bai, mon, lop, cap_hoc],
        required_sections=["I.", "II.", "III.", "IV."],
        label="lesson_plan_html",
    )
    return output
