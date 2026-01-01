import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import pandas as pd
import docx
import json
import copy
import re
import io
import time
import requests
import random
import urllib.parse
import html
import os
from jsonschema import validate, Draft202012Validator, ValidationError

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG & KẾT NỐI
# ==============================================================================
MAX_FREE_USAGE = 3
MAX_PRO_USAGE = 15
BONUS_PER_REF = 0
BONUS_PRO_REF = 3
DISCOUNT_AMT = 0
COMMISSION_AMT = 10000
BANK_ID = "VietinBank"
BANK_ACC = "107878907329"
BANK_NAME = "TRAN THANH TUAN"
PRICE_VIP = 50000

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    SYSTEM_GOOGLE_KEY = st.secrets.get("GOOGLE_API_KEY", "")
    SEPAY_API_TOKEN = st.secrets.get("SEPAY_API_TOKEN", "")
except:
    SUPABASE_URL = ""
    SUPABASE_KEY = ""
    SYSTEM_GOOGLE_KEY = ""
    SEPAY_API_TOKEN = ""

# Model defaults - Ưu tiên Gemini Flash cho tốc độ, Pro cho chất lượng
MODEL_GEMINI = "gemini-2.0-flash" 

if 'engine_choice' not in st.session_state:
    st.session_state['engine_choice'] = 'gemini'

st.set_page_config(page_title="AI EXAM EXPERT v10 – 2026", page_icon="🎓", layout="wide", initial_sidebar_state="collapsed")

def safe_json_loads(text: str):
    """Parse JSON robustly from LLM outputs."""
    import json as _json
    import re as _re
    if text is None: raise ValueError("Empty text")
    s = str(text).strip()
    s = _re.sub(r"^```(?:json)?\s*", "", s, flags=_re.IGNORECASE)
    s = _re.sub(r"\s*```$", "", s)
    obj_match = _re.search(r"\{[\s\S]*\}", s)
    if obj_match: s2 = obj_match.group(0)
    else: s2 = s
    try:
        return _json.loads(s2)
    except Exception:
        s3 = _re.sub(r",\s*([}\]])", r"\1", s2)
        s3 = s3.replace("“", '"').replace("”", '"').replace("’", "'")
        try: return _json.loads(s3)
        except Exception as e: raise ValueError(f"Invalid JSON: {e}") from e

# ==============================================================================
# [MODULE NLS] DỮ LIỆU & CẤU HÌNH CHO SOẠN GIÁO ÁN NĂNG LỰC SỐ
# ==============================================================================
NLS_FRAMEWORK_DATA = """
KHUNG NĂNG LỰC SỐ (DIGITAL COMPETENCE FRAMEWORK) - CẬP NHẬT MỚI NHẤT
MÔ TẢ CÁC MIỀN NĂNG LỰC VÀ YÊU CẦU CẦN ĐẠT (YCCĐ):
1. MIỀN 1: KHAI THÁC DỮ LIỆU VÀ THÔNG TIN
   1.1. Duyệt, tìm kiếm và lọc dữ liệu.
   1.2. Đánh giá dữ liệu.
   1.3. Quản lý dữ liệu.
2. MIỀN 2: GIAO TIẾP VÀ HỢP TÁC
   2.1. Tương tác qua công nghệ.
   2.4. Hợp tác qua công nghệ.
   2.5. Văn hóa mạng.
3. MIỀN 3: SÁNG TẠO NỘI DUNG SỐ
4. MIỀN 4: AN TOÀN SỐ
5. MIỀN 5: GIẢI QUYẾT VẤN ĐỀ
6. MIỀN 6: ỨNG DỤNG AI
"""

SYSTEM_INSTRUCTION_NLS = f"""
Bạn là chuyên gia tư vấn giáo dục cao cấp, chuyên về chuyển đổi số và Khung Năng lực số (NLS).
DỮ LIỆU KHUNG NĂNG LỰC SỐ:
{NLS_FRAMEWORK_DATA}
NHIỆM VỤ CỐT LÕI: Phân tích và tích hợp NLS vào giáo án.
"""

def generate_nls_lesson_plan(api_key, lesson_content, distribution_content, textbook, subject, grade, analyze_only):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=SYSTEM_INSTRUCTION_NLS)
    user_prompt = f"THÔNG TIN: {textbook} | {subject} | {grade}. YÊU CẦU: {distribution_content}. NỘI DUNG: {lesson_content}"
    try:
        response = model.generate_content(user_prompt)
        return response.text
    except Exception as e:
        return f"Lỗi AI: {str(e)}"

# [MỚI] TÍCH HỢP MODULE SOẠN BÀI HƯỚNG B
try:
    from lesson_ui import module_lesson_plan_B
except ImportError:
    module_lesson_plan_B = None

# ==============================================================================
# 2. DỮ LIỆU CỐ ĐỊNH (CONSTANTS)
# ==============================================================================
FULL_YCCD_DATA = [
  {"id": "L1-SO-01", "mon": "Toán", "lop": 1, "chu_de": "Số và Phép tính", "bai": "Các số đến 100", "yccd": "Đếm, đọc, viết được các số trong phạm vi 100."},
  {"id": "L5-DL-01", "mon": "Toán", "lop": 5, "chu_de": "Đo lường", "bai": "Toán chuyển động", "yccd": "Giải bài toán về vận tốc, quãng đường, thời gian."}
]

PPCT_DATA = [
    {"cap_hoc": "Tiểu học", "mon": "Toán", "lop": "Lớp 5", "bo_sach": "Kết nối tri thức với cuộc sống", "tuan": 1, "tiet": 1, "bai_id": "T5-KNTT-T1-1", "ten_bai": "Ôn tập khái niệm phân số"},
]

APP_CONFIG = {
    "name": "AI EXAM EXPERT v10 – 2026",
    "role": "Trợ lý chuyên môn Cấp Sở",
    "context": """VAI TRÒ: Trợ lý AI Chuyên môn."""
}

EDUCATION_DATA = {
    "tieu_hoc": {"label": "Tiểu học", "grades": ["Lớp 1", "Lớp 2", "Lớp 3", "Lớp 4", "Lớp 5"], "subjects": ["Toán", "Tiếng Việt", "Tiếng Anh", "Tin học", "Khoa học", "Lịch sử và Địa lí", "Đạo đức", "Tự nhiên và Xã hội", "Công nghệ", "Âm nhạc", "Mĩ thuật", "Hoạt động trải nghiệm"], "legal": "Thông tư 27"},
    "thcs": {"label": "THCS", "grades": ["Lớp 6", "Lớp 7", "Lớp 8", "Lớp 9"], "subjects": ["Ngữ văn", "Toán", "Tiếng Anh", "KHTN", "Lịch sử và Địa lí", "GDCD", "Tin học", "Công nghệ"], "legal": "Thông tư 22"},
    "thpt": {"label": "THPT", "grades": ["Lớp 10", "Lớp 11", "Lớp 12"], "subjects": ["Ngữ văn", "Toán", "Tiếng Anh", "Vật lí", "Hóa học", "Sinh học", "Lịch sử", "Địa lí", "GDKT&PL", "Tin học", "Công nghệ"], "legal": "Cấu trúc 2025"}
}

BOOKS_LIST = ["Kết nối tri thức với cuộc sống", "Chân trời sáng tạo", "Cánh Diều", "Cùng khám phá", "Vì sự bình đẳng và dân chủ trong giáo dục"]
FULL_SCOPE_LIST = ["Khảo sát chất lượng đầu năm", "Kiểm tra giữa kì 1", "Kiểm tra cuối kì 1", "Kiểm tra giữa kì 2", "Kiểm tra cuối kì 2"]
LIMITED_SCOPE_LIST = ["Khảo sát chất lượng đầu năm", "Kiểm tra cuối kì 1", "Kiểm tra cuối kì 2"]
SCOPE_MAPPING = {"Khảo sát chất lượng đầu năm": "Ôn tập hè & Tuần 1-2"}
CURRICULUM_DATA = {"Toán": {"Lớp 6": {"Kiểm tra giữa kì 1": "Tập hợp số tự nhiên"}}}
LEGAL_DOCUMENTS = [{"code": "CV 2345", "title": "KHGD Tiểu học", "summary": "Xây dựng kế hoạch bài dạy", "highlight": True}]
SUBJECT_STRUCTURE_DATA = {"Mặc định": "NB (40%) - TH (30%) - VD (20%) - VDC (10%)"}

# ==============================================================================
# 3. GIAO DIỆN & CSS
# ==============================================================================
st.markdown("""
<style>
.kpi-card{background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:16px 18px; box-shadow:0 4px 8px rgba(0,0,0,0.04); margin-bottom:12px;}
.paper-view table { width: 100%; border-collapse: collapse; margin-bottom: 1em; }
.paper-view th, .paper-view td { border: 1px solid black; padding: 6px; text-align: left; vertical-align: top; }
.paper-view th { background-color: #f2f2f2; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. HÀM XỬ LÝ LOGIC (UTILS)
# ==============================================================================
def init_supabase():
    try: return create_client(SUPABASE_URL, SUPABASE_KEY)
    except: return None

def read_file_content(uploaded_file, file_type):
    if not uploaded_file: return ""
    try:
        if uploaded_file.name.endswith('.docx'):
            doc = docx.Document(io.BytesIO(uploaded_file.getvalue()))
            return "\n".join([p.text for p in doc.paragraphs])
        elif uploaded_file.name.endswith('.xlsx'):
            content = pd.read_excel(uploaded_file).to_string()
            return content
    except: return ""
    return ""

def create_word_doc(html, title):
    doc_content = f"""<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset='utf-8'><title>{title}</title><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom></w:WordDocument></xml><style>@page {{ size: 21cm 29.7cm; margin: 2cm 2cm 2cm 2cm; }} body {{ font-family: 'Times New Roman'; font-size: 13pt; }} table {{ border-collapse: collapse; width: 100%; border: 1px solid black; }} td, th {{ border: 1px solid black; padding: 5px; vertical-align: top; }}</style></head><body><div class="WordSection1">{html}</div></body></html>"""
    return "\ufeff" + doc_content

def _html_escape(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""
def _render_ul(items):
    if not items: return "<ul><li>...</li></ul>"
    lis = "".join([f"<li>{_html_escape(x)}</li>" for x in items if str(x).strip()])
    return f"<ul>{lis or '<li>...</li>'}</ul>"

# --- RENDERER GIÁO ÁN (ĐÃ FIX ĐỂ KHỚP DATA MAPPING) ---
def render_lesson_plan_html(data: dict) -> str:
    if "sections" in data:
        return render_lesson_plan_html_from_schema(data)
    return "Lỗi: Dữ liệu không đúng định dạng."

def render_lesson_plan_html_from_schema(data: dict) -> str:
    sections = data.get("sections", {})
    meta = data.get("meta", {})
    
    html_parts = []
    html_parts.append(f"<div style='font-family:Times New Roman, serif; font-size:13pt; line-height:1.3; color:#000;'><div style='text-align:center; font-weight:bold; font-size:14pt; margin-bottom:10px;'>KẾ HOẠCH BÀI DẠY</div>")
    html_parts.append(f"<div style='margin-bottom:10px;'><b>Cấp học:</b> {_html_escape(meta.get('cap_hoc', ''))} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Môn:</b> {_html_escape(meta.get('mon', ''))} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Lớp:</b> {_html_escape(meta.get('lop', ''))}<br/><b>Bộ sách:</b> {_html_escape(meta.get('bo_sach', ''))}<br/><b>PPCT:</b> Tuần {_html_escape(str(meta.get('ppct',{}).get('tuan','')))} – Tiết {_html_escape(str(meta.get('ppct',{}).get('tiet','')))} – Mã bài {_html_escape(str(meta.get('ppct',{}).get('bai_id','')))}<br/><b>Tên bài:</b> {_html_escape(meta.get('ten_bai', ''))}<br/><b>Thời lượng:</b> {_html_escape(str(meta.get('thoi_luong', '')))} phút &nbsp;&nbsp;|&nbsp;&nbsp; <b>Sĩ số:</b> {_html_escape(str(meta.get('si_so', '')))} HS</div>")
    
    # [FIX] Đồng bộ tiêu đề để khớp với validator
    section_map = [
        ("I", "I. YÊU CẦU CẦN ĐẠT"),
        ("II", "II. ĐỒ DÙNG DẠY HỌC"),
        ("III", "III. CÁC HOẠT ĐỘNG DẠY – HỌC CHỦ YẾU"),
        ("IV", "IV. ĐIỀU CHỈNH SAU BÀI DẠY (Rút kinh nghiệm)")
    ]
    
    for key, title in section_map:
        sec = sections.get(key, {})
        html_parts.append(f"<div style='margin:10px 0 6px 0; font-weight:bold;'>{title}</div>")
        
        if key == "III":
            acts = sec.get("hoat_dong", [])
            rows = ""
            for i, act in enumerate(acts, 1):
                gv_list = act.get("gv", [])
                hs_list = act.get("hs", [])
                
                gv_html = "<ul>" + "".join([f"<li>{_html_escape(x)}</li>" for x in gv_list]) + "</ul>" if isinstance(gv_list, list) else _html_escape(gv_list)
                hs_html = "<ul>" + "".join([f"<li>{_html_escape(x)}</li>" for x in hs_list]) + "</ul>" if isinstance(hs_list, list) else _html_escape(hs_list)
                
                rows += f"""<tr><td style='width:42px; text-align:center;'><b>{i}</b></td><td style='width:160px;'><b>{_html_escape(act.get('ten',''))}</b></td><td style='width:70px; text-align:center;'>{_html_escape(str(act.get('thoi_gian','')))}</td><td style='width:50%;'>{gv_html}</td><td style='width:50%;'>{hs_html}</td></tr>"""
            
            html_parts.append(f"<table border='1' style='width:100%; border-collapse:collapse;'><tr><th style='width:42px; text-align:center;'>STT</th><th style='width:160px; text-align:center;'>Hoạt động</th><th style='width:70px; text-align:center;'>Thời gian</th><th style='text-align:center;'>Hoạt động của GV</th><th style='text-align:center;'>Hoạt động của HS</th></tr>{rows}</table>")
        
        elif key == "IV":
            # [FIX] Đảm bảo hiển thị nội dung rút kinh nghiệm
            content = sec.get("Nội dung", "") or sec.get("dieu_chinh_sau_bai_day", "................................")
            html_parts.append(f"<div>{_html_escape(content)}</div>")
            
        else:
            for sub_k, sub_v in sec.items():
                label = sub_k.replace("_", " ").capitalize()
                content = _render_ul(sub_v) if isinstance(sub_v, list) else _html_escape(sub_v)
                html_parts.append(f"<div><b>{label}:</b>{content}</div>")
                
    html_parts.append("</div>")
    return "\n".join(html_parts)

def call_llm_text(
    *,
    engine: str,
    model_name: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    max_output_tokens: int = 4096,
    response_mime_type: str | None = None,
) -> str:

    # schema hiện được dùng ở lớp validate JSON bên ngoài; giữ tham số để tương thích.
    """Call the selected LLM engine and return plain text.

    Notes:
    - Gemini: uses google.generativeai with system_instruction and GenerationConfig.
    - OpenAI: uses openai Python SDK if available.
    """
    engine = (engine or "").strip().lower()
    if not api_key:
        raise ValueError("Thiếu API key cho engine đã chọn.")

    if engine == "gemini":
        # Google Gemini via google.generativeai
        try:
            import google.generativeai as genai  # type: ignore
        except Exception as e:
            raise RuntimeError(f"Không import được google.generativeai: {e}") from e

        genai.configure(api_key=api_key)

        try:
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type=response_mime_type or "text/plain",
            )
        except Exception:
            # Fallback for older SDK versions without response_mime_type
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        model = genai.GenerativeModel(model_name=model_name, system_instruction=system_prompt)
        res = model.generate_content(
            user_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        text = getattr(res, "text", None)
        if not text:
            # Some SDK versions return candidates list; try to extract safely.
            try:
                text = res.candidates[0].content.parts[0].text  # type: ignore
            except Exception:
                text = ""
        return (text or "").strip()

    if engine == "openai":
        # OpenAI via official SDK (if installed)
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError(f"Không import được openai SDK: {e}") from e

        client = OpenAI(api_key=api_key)
        # OpenAI max_tokens refers to output tokens
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    raise ValueError(f"Engine không hợp lệ: {engine}. Chỉ hỗ trợ: gemini, openai.")
    
def check_sepay_transaction(amount, content):
    return False 

# ==============================================================================
# SCHEMA & VALIDATION
# ==============================================================================
LESSON_PLAN_SCHEMA = {
    "type": "object",
    "required": ["meta", "sections"], 
    "additionalProperties": True,
    "properties": {
        "meta": {"type": "object"},
        "sections": {"type": "object"}
    }
}

def validate_lesson_plan(data: dict) -> None:
    try:
        Draft202012Validator.check_schema(LESSON_PLAN_SCHEMA)
        validate(instance=data, schema=LESSON_PLAN_SCHEMA)
    except Exception as e:
        print(f"Schema Warning: {e}")

# ==============================================================================
# AI LOGIC: PROMPT & GENERATION (ĐÃ FIX LỖI VALIDATION & MAPPING)
# ==============================================================================

def build_lesson_system_prompt_locked(meta: dict, teacher_note: str) -> str:
    return f"""
VAI TRÒ: Bạn là Giáo viên Tiểu học cốt cán, soạn KẾ HOẠCH BÀI DẠY (Giáo án) theo chuẩn CTGDPT 2018 (Công văn 2345/BGDĐT).

THÔNG TIN:
- Bài: {meta.get('ten_bai')}
- Lớp: {meta.get('lop')} | Môn: {meta.get('mon')}
- Bộ sách: {meta.get('bo_sach')}
- Thời lượng: {meta.get('thoi_luong')} phút | Sĩ số: {meta.get('si_so')}

GHI CHÚ GV: {teacher_note}

YÊU CẦU CẤU TRÚC JSON (BẮT BUỘC):
Trả về JSON object duy nhất với các key sau (KHÔNG dùng markdown):
1. "muc_tieu": {{ "yeu_cau_can_dat": [], "pham_chat": [], "nang_luc": [], "nang_luc_dac_thu": [], "nang_luc_so": [] }}
2. "chuan_bi": {{ "giao_vien": [], "hoc_sinh": [] }}
3. "tien_trinh": Mảng các hoạt động. Mỗi hoạt động gồm: 
   {{ "hoat_dong": "Tên hoạt động (VD: Khởi động)", "thoi_gian": "số phút", "cac_buoc": [ {{ "gv": "Mô tả chi tiết hoạt động GV", "hs": "Mô tả chi tiết hoạt động HS" }} ] }}
4. "rut_kinh_nghiem": {{ "dieu_chinh_sau_bai_day": "nội dung..." }}

LƯU Ý: 
- "tien_trinh" phải có đủ 4 pha: Khởi động, Khám phá/Hình thành kiến thức, Luyện tập, Vận dụng.
- Nội dung GV/HS phải chi tiết, rõ ràng.
""".strip()

# [HÀM TỰ ĐỘNG CHÈN NỘI DUNG NẾU AI VIẾT NGẮN]
def enrich_lesson_plan_data_min_detail(data: dict) -> dict:
    if "sections" not in data: return data
    sections = data["sections"]
    if "III" not in sections: sections["III"] = {"hoat_dong": []}
    
    acts = sections["III"]["hoat_dong"]
    required_phases = ["Khởi động", "Khám phá/Hình thành kiến thức", "Luyện tập", "Vận dụng"]
    existing_names = [a.get("ten", "").lower() for a in acts]
    
    # 1. Tự động chèn pha thiếu
    if len(acts) < 4:
        for phase in required_phases:
            if not any(phase.lower().split()[0] in name for name in existing_names):
                acts.append({
                    "ten": phase, 
                    "thoi_gian": "5-10 phút", 
                    "gv": [f"GV tổ chức hoạt động {phase}."], 
                    "hs": ["HS tham gia hoạt động."]
                })
    
    # 2. Tự động làm giàu nội dung GV/HS nếu quá ngắn
    for act in acts:
        if len(act.get("gv", [])) < 2:
            act["gv"] = act.get("gv", []) + ["GV quan sát, hỗ trợ HS gặp khó khăn.", "GV nhận xét, chốt kiến thức/kỹ năng.", "GV đặt câu hỏi gợi mở để HS tư duy."]
        if len(act.get("hs", [])) < 2:
            act["hs"] = act.get("hs", []) + ["HS lắng nghe, ghi chép.", "HS trình bày kết quả.", "HS nhận xét bài làm của bạn."]

    sections["III"]["hoat_dong"] = acts
    data["sections"] = sections
    return data

def build_lesson_system_prompt_data_only(meta: dict, teacher_note: str) -> str:
    return f"""
VAI TRÒ: Giáo viên.
NHIỆM VỤ: Soạn giáo án.
THÔNG TIN: {meta}
GHI CHÚ: {teacher_note}
YÊU CẦU: Trả về JSON với các trường: meta, sections (I, II, III, IV).
Trong đó sections.III.hoat_dong là mảng các object có ten, thoi_gian, gv, hs.
"""

def generate_lesson_plan_data_only(
    api_key: str,
    meta_ppct: dict,
    teacher_note: str,
    model_name: str = "gemini-2.0-flash"
) -> dict:
    genai.configure(api_key=api_key)
    req_meta = {
        "cap_hoc": meta_ppct.get("cap_hoc"), "mon": meta_ppct.get("mon"), "lop": meta_ppct.get("lop"),
        "bo_sach": meta_ppct.get("bo_sach"),
        "ppct": {"tuan": 1, "tiet": 1, "bai_id": "AUTO", "ghi_chu": ""},
        "ten_bai": meta_ppct.get("ten_bai"), "thoi_luong": 35, "si_so": 40
    }
    
    system_prompt = build_lesson_system_prompt_data_only(req_meta, teacher_note)
    model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
    
    try:
        res = model.generate_content(json.dumps({"meta": req_meta}, ensure_ascii=False))
        return json.loads(clean_json(res.text))
    except:
        return {"meta": req_meta, "sections": {}}


# [HÀM SINH GIÁO ÁN ĐÃ SỬA THAM SỐ VÀ LOGIC MAPPING]
def generate_lesson_plan_locked(api_key: str, meta_ppct: dict, bo_sach: str, thoi_luong: int, si_so: int, teacher_note: str, model_name: str = "gemini-2.0-flash", **kwargs):
    system_prompt = build_lesson_system_prompt_locked({**meta_ppct, "bo_sach": bo_sach, "thoi_luong": thoi_luong, "si_so": si_so}, teacher_note)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
    
    safe_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    req = {
        "meta": {
            "cap_hoc": meta_ppct.get("cap_hoc"), "mon": meta_ppct.get("mon"), "lop": meta_ppct.get("lop"),
            "bo_sach": bo_sach, "ten_bai": meta_ppct.get("ten_bai"),
            "thoi_luong": int(thoi_luong), "si_so": int(si_so)
        },
        "teacher_note": teacher_note
    }

    try:
        # Gọi AI
        res = model.generate_content(
            json.dumps(req, ensure_ascii=False), 
            generation_config={"response_mime_type": "application/json"}, 
            safety_settings=safe_settings
        )
        
        raw_text = clean_json(res.text)
        data = json.loads(raw_text)
        
        # [MAPPING DATA TỪ AI -> RENDERER]
        if "sections" not in data:
            data["sections"] = {}
            # Mapping I, II
            mt = data.get("muc_tieu", {})
            data["sections"]["I"] = {
                "yeu_cau_can_dat": mt.get("yeu_cau_can_dat", []),
                "pham_chat": mt.get("pham_chat", []),
                "nang_luc": mt.get("nang_luc", [])
            }
            cb = data.get("chuan_bi", {})
            data["sections"]["II"] = {
                "giao_vien": cb.get("giao_vien", []),
                "hoc_sinh": cb.get("hoc_sinh", [])
            }
            
            # Mapping III (Tiến trình)
            processed_activities = []
            raw_activities = data.get("tien_trinh", [])
            for act in raw_activities:
                gv_steps = []
                hs_steps = []
                for step in act.get("cac_buoc", []):
                    if "gv" in step: gv_steps.append(f"- {step['gv']}")
                    if "hs" in step: hs_steps.append(f"- {step['hs']}")
                
                # Fallback nếu AI trả string thay vì array
                if not gv_steps and "gv" in act: gv_steps = [str(act["gv"])]
                if not hs_steps and "hs" in act: hs_steps = [str(act["hs"])]

                processed_activities.append({
                    "ten": act.get("hoat_dong", "Hoạt động"),
                    "thoi_gian": str(act.get("thoi_gian", "")),
                    "gv": gv_steps,
                    "hs": hs_steps
                })
            data["sections"]["III"] = {"hoat_dong": processed_activities}
            
            # Mapping IV (Rút kinh nghiệm)
            rkn = data.get("rut_kinh_nghiem", {})
            val = rkn.get("dieu_chinh_sau_bai_day", "................")
            data["sections"]["IV"] = {"dieu_chinh_sau_bai_day": str(val)}

        if "meta" not in data: data["meta"] = req["meta"]

        # Gọi hàm Enrichment để tự động điền nếu thiếu
        data = enrich_lesson_plan_data_min_detail(data)

        validate_lesson_plan(data)
        return data

    except Exception as e:
        return {"renderHtml": f"Lỗi sinh nội dung: {str(e)}", "title": "Lỗi"}

def quality_check_lesson_html(render_html: str) -> tuple[bool, str]:
    import re
    text = re.sub(r"<[^>]+>", " ", render_html or "")
    # Nới lỏng kiểm tra: Không bắt buộc từ khóa cứng nhắc, chỉ cảnh báo nếu quá ngắn
    word_count = len(re.findall(r"\w+", text))
    if word_count < 400: # Giảm ngưỡng xuống 400
        return False, f"Nội dung quá ngắn ({word_count} từ). Cần tối thiểu 400 từ."
    return True, ""

# ==============================================================================
# YCCĐ MANAGER & GENERATOR
# ==============================================================================
class YCCDManager:
    def __init__(self): self.data = FULL_YCCD_DATA 
    def get_grades(self): return sorted(list(set([item['lop'] for item in self.data])))
    def get_topics_by_grade(self, grade): return sorted(list(set([item['chu_de'] for item in self.data if item['lop'] == grade])))
    def get_yccd_list(self, grade, topic): return [item for item in self.data if item['lop'] == grade and item['chu_de'] == topic]

class QuestionGeneratorYCCD:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
    def generate(self, yccd_item, muc_do="Thông hiểu"):
        prompt = f"""Soạn câu hỏi trắc nghiệm Toán lớp {yccd_item['lop']}, chủ đề {yccd_item['chu_de']}, YCCĐ: {yccd_item['yccd']}, mức độ {muc_do}. Trả JSON {{question, options[], answer, explanation}}."""
        try:
            res = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            return json.loads(clean_json(res.text))
        except: return None

# ==============================================================================
# MODULE LESSON PLAN (UI)
# ==============================================================================
def _lp_uid(): return st.session_state.get("user", {}).get("email", "guest")
def _lp_key(name): return f"lp_{name}_{_lp_uid()}"
def _lp_api_key(): return st.session_state.get("api_key") or SYSTEM_GOOGLE_KEY
def _lp_init_state():
    if _lp_key("history") not in st.session_state: st.session_state[_lp_key("history")] = []
    if _lp_key("last_html") not in st.session_state: st.session_state[_lp_key("last_html")] = ""
    if _lp_key("last_title") not in st.session_state: st.session_state[_lp_key("last_title")] = "GiaoAn"
def _lp_set_active(page): st.session_state["lp_active_page_admin_state"] = page
def _lp_get_active(default): return st.session_state.get("lp_active_page_admin_state", default)

def module_lesson_plan():
    _lp_init_state()

    # ---------- CSS bổ sung cho module (không làm hỏng CSS hiện có) ----------
    st.markdown("""
    <style>
      .lp-hero{
        background: linear-gradient(135deg, #0F172A 0%, #1D4ED8 55%, #60A5FA 100%);
        border-radius: 14px;
        padding: 22px 22px 18px 22px;
        color: white;
        border: 1px solid rgba(255,255,255,.18);
        box-shadow: 0 10px 18px rgba(2,6,23,.18);
        margin-bottom: 18px;
      }
      .lp-hero h2{margin:0; font-weight:800;}
      .lp-hero p{margin:6px 0 0 0; opacity:.9}
      .lp-kpi{
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 6px rgba(15,23,42,.06);
      }
      .lp-card{
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 18px;
        box-shadow: 0 2px 6px rgba(15,23,42,.06);
        margin-bottom: 14px;
      }
      .lp-label{font-weight:700; color:#0F172A;}
      .lp-hint{color:#64748B; font-size:13px; margin-top:4px;}
      .lp-pill{
        display:inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid #BFDBFE;
        background: #EFF6FF;
        color: #1D4ED8;
        font-size: 12px;
        font-weight: 800;
      }
    </style>
    """, unsafe_allow_html=True)

    # ---------- HERO ----------
    st.markdown("""
    <div class="lp-hero">
      <h2>📘 Trợ lý Soạn bài – Tạo Giáo án tự động</h2>
      <p>Soạn giáo án theo CTGDPT 2018, đúng cấu trúc hồ sơ chuyên môn, có tuỳ chọn mức chi tiết và phương pháp dạy học.</p>
    </div>
    """, unsafe_allow_html=True)

    # =========================
    # THIẾT LẬP TRÊN TRANG (KHÔNG DÙNG SIDEBAR)
    # =========================
    st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
    st.markdown("### ⚙️ Thiết lập tạo giáo án")

    with st.form(key=_lp_key("form_settings"), clear_on_submit=False):
        r1c1, r1c2, r1c3, r1c4 = st.columns([1.2, 1.0, 1.2, 1.6])

        with r1c1:
            school_year = st.selectbox(
                "Năm học",
                ["2024-2025", "2025-2026", "2026-2027"],
                index=1,
                key=_lp_key("year")
            )

        with r1c2:
            level_key = st.radio(
                "Cấp học",
                ["Tiểu học", "THCS", "THPT"],
                horizontal=True,
                key=_lp_key("level")
            )

        curr_lvl = "tieu_hoc" if level_key == "Tiểu học" else "thcs" if level_key == "THCS" else "thpt"
        edu = EDUCATION_DATA[curr_lvl]

        with r1c3:
            grade = st.selectbox("Khối lớp", edu["grades"], key=_lp_key("grade"))

        with r1c4:
            subject = st.selectbox("Môn học", edu["subjects"], key=_lp_key("subject"))

        r2c1, r2c2 = st.columns([2.2, 1.2])
        with r2c1:
            book = st.selectbox("Bộ sách", BOOKS_LIST, key=_lp_key("book"))
        
        # [SỬA ĐỔI THEO YÊU CẦU]: Thay scope bằng nhập Tuần (số)
        with r2c2:
             ppct_week = st.number_input(
                "Tuần (PPCT)",
                min_value=1, max_value=40,
                value=1, step=1,
                key=_lp_key("ppct_week")
            )
             # Giữ scope ảo để truyền vào hàm cũ nếu cần, tránh lỗi logic cũ
             scope = f"Tuần {ppct_week}" 

        # =========================
        # PPCT (Bước A - nhanh): Chọn tuần/tiết bằng số
        # =========================
        r2c3, r2c4 = st.columns([1, 2.2])
        with r2c3:
            ppct_period = st.number_input(
                "Tiết (PPCT)",
                min_value=1, max_value=10,
                value=1, step=1,
                key=_lp_key("ppct_period")
            )
        
        # [SỬA ĐỔI THEO YÊU CẦU]: Nhập tên bài học
        with r2c4:
             lesson_title_input = st.text_input("Tên bài học (PPCT)", key=_lp_key("lesson_title_input"))
    
        r3c1, r3c2, r3c3 = st.columns([1.6, 1.0, 1.0])
        with r3c1:
            template = st.selectbox(
                "Mẫu giáo án",
                [
                    "Chuẩn hồ sơ (35’ – 4 hoạt động)",
                    "Chi tiết (2–3 trang)",
                    "Thi GV dạy giỏi (kèm phân hoá & rubric)",
                    "Dạy học hợp tác (nhóm/góc)",
                    "Flipped classroom (giao nhiệm vụ trước)",
                    "Trải nghiệm – trò chơi hoá"
                ],
                key=_lp_key("template")
            )
        with r3c2:
            detail_level = st.select_slider(
                "Mức chi tiết",
                options=["Ngắn gọn", "Chuẩn", "Rất chi tiết"],
                value="Chuẩn",
                key=_lp_key("detail")
            )
        with r3c3:
            duration = st.number_input(
                "Thời lượng (phút)",
                min_value=30, max_value=90, value=35, step=5,
                key=_lp_key("duration")
            )

        r4c1, r4c2 = st.columns([2.2, 1.0])
        with r4c1:
            method_focus = st.multiselect(
                "Ưu tiên phương pháp",
                ["Hoạt động nhóm", "Trò chơi hoá", "Nêu vấn đề", "Trải nghiệm", "Dự án nhỏ", "CNTT/Năng lực số"],
                default=["Hoạt động nhóm"],
                key=_lp_key("method")
            )
        with r4c2:
            class_size = st.number_input(
                "Sĩ số lớp",
                min_value=10, max_value=60, value=40, step=1,
                key=_lp_key("class_size")
            )

        b1, b2, b3 = st.columns([1.2, 1.2, 1.6])
        with b1:
            generate_btn = st.form_submit_button("⚡ TẠO GIÁO ÁN", type="primary", use_container_width=True)
        with b2:
            regen_btn = st.form_submit_button("🔁 TẠO LẠI", use_container_width=True)
        with b3:
            clear_btn = st.form_submit_button("🧹 XÓA DS GIÁO ÁN", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Hiển thị tóm tắt PPCT đã chọn (để user nhìn thấy ngay)
    ppct_week_val = st.session_state.get(_lp_key("ppct_week"), 1)
    ppct_period_val = st.session_state.get(_lp_key("ppct_period"), 1)
    ppct_text = f"PPCT: Tuần {ppct_week_val}, Tiết {ppct_period_val} - Bài: {lesson_title_input}"
    st.caption(ppct_text)

    # =========================
    # KPI Row
    # =========================
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(
            f"<div class='lp-kpi'><div class='lp-label'>Cấp/Lớp</div>"
            f"<div class='lp-hint'>{level_key} – {grade}</div></div>",
            unsafe_allow_html=True
        )

    with k2:
        st.markdown(
            f"<div class='lp-kpi'><div class='lp-label'>Môn/Bộ sách</div>"
            f"<div class='lp-hint'>{subject} – {book}</div></div>",
            unsafe_allow_html=True
        )

    with k3:
        st.markdown(
            f"<div class='lp-kpi'><div class='lp-label'>Thời lượng/Sĩ số</div>"
            f"<div class='lp-hint'>{duration} phút – {class_size} HS</div></div>",
            unsafe_allow_html=True
        )

    with k4:
        st.markdown(
            f"<div class='lp-kpi'><div class='lp-label'>Mẫu</div>"
            f"<div class='lp-hint'>{template}</div></div>",
            unsafe_allow_html=True
        )

    st.write("")

    # ---------- Điều hướng dạng radio (cho phép nhảy trang bằng code) ----------
    pages = [
        "1) Thiết lập & Mục tiêu",
        "2) Kế hoạch hoạt động",
        "3) Phân hoá",
        "4) Đánh giá",
        "5) Học liệu",
        "6) Xem trước & Xuất",
    ]

    # IMPORTANT: đừng set st.session_state["lp_active_page_admin"] sau khi widget tạo
    # Ta dùng 2 key: 
    # - lp_active_page_admin_state: state điều khiển bằng code
    # - lp_active_page_admin: widget key (Streamlit quản lý)
    if "lp_active_page_admin_state" not in st.session_state:
        st.session_state["lp_active_page_admin_state"] = pages[0]

    active_default = _lp_get_active(pages[0])
    active_index = pages.index(active_default) if active_default in pages else 0

    active_page = st.radio(
        "📌 Điều hướng soạn giáo án",
        pages,
        index=active_index,
        key="lp_active_page_admin",
    )

    # Đồng bộ state sau khi user bấm chọn
    st.session_state["lp_active_page_admin_state"] = active_page

    # ---------- Render theo trang ----------
    if active_page == "1) Thiết lập & Mục tiêu":
        # (giữ nguyên nội dung của with tab1:)
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        # [SỬA ĐỔI] Lấy giá trị từ ô nhập ở form trên
        st.text_input(
            "Tên bài/Chủ đề (Đã nhập ở trên)",
            value=lesson_title_input,
            disabled=True, # Khóa lại vì đã nhập ở trên
            key=_lp_key("lesson_title_display")
        )
        st.text_area(
            "Mục tiêu (AI sẽ chuẩn hoá theo CTGDPT 2018)",
            key=_lp_key("objectives"),
            height=120,
            placeholder="Gợi ý: phẩm chất/năng lực, kiến thức, kĩ năng..."
        )
        st.text_area(
            "Chuẩn đầu ra / Yêu cầu cần đạt (nếu có)",
            key=_lp_key("yccd"),
            height=120,
            placeholder="Dán YCCĐ hoặc mô tả ngắn (nếu chưa có sẽ để AI tự suy luận theo bộ sách/phạm vi)."
        )
        st.markdown("</div>", unsafe_allow_html=True)

    elif active_page == "2) Kế hoạch hoạt động":
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        st.markdown("**Khung 4 hoạt động** (AI sẽ bám đúng thời lượng và chia pha hợp lý)")
        st.text_area("Hoạt động 1 – Khởi động (ý tưởng, trò chơi, dẫn nhập)", key=_lp_key("a1"), height=90)
        st.text_area("Hoạt động 2 – Hình thành kiến thức/Khám phá", key=_lp_key("a2"), height=90)
        st.text_area("Hoạt động 3 – Luyện tập", key=_lp_key("a3"), height=90)
        st.text_area("Hoạt động 4 – Vận dụng/Mở rộng", key=_lp_key("a4"), height=90)
        st.markdown("</div>", unsafe_allow_html=True)

    elif active_page == "3) Phân hoá":
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        st.text_area(
            "Phân hoá (HS yếu – TB – khá/giỏi)",
            key=_lp_key("diff"),
            height=150,
            placeholder="Ví dụ: HS yếu làm câu 1-2; khá/giỏi làm câu nâng cao nhẹ; hỗ trợ theo cặp..."
        )
        st.text_area("Hỗ trợ đặc thù (nếu có)", key=_lp_key("support"), height=90)
        st.markdown("</div>", unsafe_allow_html=True)

    elif active_page == "4) Đánh giá":
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        st.text_area(
            "Đánh giá trong giờ (câu hỏi nhanh/phiếu quan sát/tiêu chí)",
            key=_lp_key("assess"),
            height=160
        )
        st.text_area(
            "Rubric/Thang tiêu chí (nếu cần)",
            key=_lp_key("rubric"),
            height=120,
            placeholder="Ví dụ: Hoàn thành tốt/Hoàn thành/Chưa hoàn thành; tiêu chí cụ thể..."
        )
        st.markdown("</div>", unsafe_allow_html=True)

    elif active_page == "5) Học liệu":
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        st.text_area("Đồ dùng dạy học", key=_lp_key("materials"), height=120)
        st.text_area(
            "Học liệu số/CNTT (nếu dùng)",
            key=_lp_key("digital"),
            height=120,
            placeholder="Ví dụ: trình chiếu, phiếu học tập điện tử, trò chơi Quiz..."
        )
        st.markdown("</div>", unsafe_allow_html=True)

    else:  # "6) Xem trước & Xuất"
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        last_html = st.session_state.get(_lp_key("last_html"), "")
        if not last_html:
           st.info("Chưa có giáo án. Hãy bấm ⚡ TẠO GIÁO ÁN ở phần thiết lập phía trên.")
        else:
            content_html = str(last_html)
   
            st.markdown(f"<div class='paper-view'>{content_html}</div>", unsafe_allow_html=True)

            cdl1, cdl2 = st.columns([1, 1])
            with cdl1:
                st.download_button(
                    "⬇️ Tải Word giáo án",
                    create_word_doc(content_html, st.session_state.get(_lp_key("last_title"), "GiaoAn")),
                    file_name="GiaoAn.doc",
                    mime="application/msword",
                    type="primary",
                    key=_lp_key("dl_word")
                )
            with cdl2:
                if st.button("📌 Lưu vào danh sách", key=_lp_key("btn_save")):
                    st.session_state[_lp_key("history")].insert(0, {
                        "title": st.session_state.get(_lp_key("last_title"), "GiaoAn"),
                        "html": content_html
                    })
                    st.toast("Đã lưu!", icon="✅")
        st.markdown("</div>", unsafe_allow_html=True)

    # ---------- Lịch sử giáo án ----------
    history = st.session_state.get(_lp_key("history"), [])
    if history:
        st.markdown("<div class='lp-card'>", unsafe_allow_html=True)
        st.markdown("### 🗂️ Danh sách giáo án đã tạo")
        pick = st.selectbox(
            "Chọn giáo án đã lưu",
            range(len(history)),
            format_func=lambda i: history[i]["title"],
            key=_lp_key("pick_history")
        )
        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("📄 Mở giáo án", key=_lp_key("btn_open_hist")):
                st.session_state[_lp_key("last_title")] = history[pick]["title"]
                st.session_state[_lp_key("last_html")] = history[pick]["html"]
                st.rerun()
        with colB:
            if st.button("🗑️ Xoá giáo án này", key=_lp_key("btn_del_hist")):
                history.pop(pick)
                st.session_state[_lp_key("history")] = history
                st.toast("Đã xoá!", icon="🗑️")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # ===============================
    # XỬ LÝ NÚT BẤM (GỌI HÀM MỚI LOCKED)
    # ===============================
    if generate_btn or regen_btn:
        api_key = _lp_api_key()
        if not api_key:
            st.error("❌ Chưa có API Key.")
            st.stop()

        # Lấy dữ liệu người dùng đã nhập
        lesson_title = lesson_title_input.strip()
        objectives = st.session_state.get(_lp_key("objectives"), "").strip()
        yccd = st.session_state.get(_lp_key("yccd"), "").strip()

        # PPCT
        ppct_week_val = st.session_state.get(_lp_key("ppct_week"), 1)
        ppct_period_val = st.session_state.get(_lp_key("ppct_period"), 1)
        ppct_text = f"PPCT: Tuần {ppct_week_val}, Tiết {ppct_period_val}"

        # Gom ghi chú GV
        teacher_note = f"""
        {ppct_text}
        Mẫu: {template} | Mức chi tiết: {detail_level}
        Ưu tiên phương pháp: {", ".join(method_focus) if method_focus else "Chuẩn"}

        Mục tiêu GV nhập: {objectives if objectives else "(trống)"}
        YCCĐ GV nhập: {yccd if yccd else "(trống)"}

        Gợi ý hoạt động GV:
        - Khởi động: {st.session_state.get(_lp_key("a1"), "")}
        - Hình thành: {st.session_state.get(_lp_key("a2"), "")}
        - Luyện tập: {st.session_state.get(_lp_key("a3"), "")}
        - Vận dụng: {st.session_state.get(_lp_key("a4"), "")}

        Phân hoá: {st.session_state.get(_lp_key("diff"), "")}
        Hỗ trợ đặc thù: {st.session_state.get(_lp_key("support"), "")}
        Đánh giá trong giờ: {st.session_state.get(_lp_key("assess"), "")}
        Đồ dùng: {st.session_state.get(_lp_key("materials"), "")}
        """
        
        # Meta ảo để truyền vào hàm generate locked
        meta_ppct = {
             "cap_hoc": level_key,
             "mon": subject,
             "lop": grade,
             "tuan": ppct_week_val,
             "tiet": ppct_period_val,
             "ten_bai": lesson_title if lesson_title else f"{subject} {grade} ({ppct_text})",
             "bai_id": f"AUTO-{ppct_week_val}-{ppct_period_val}",
             "bo_sach": book,
             "ghi_chu": ""
        }

        try:
            with st.spinner("🔄 Đang tạo giáo án (JSON data-only)..."):
                # [ĐÃ SỬA LỖI GỌI HÀM: TRUYỀN ĐỦ THAM SỐ]
                data = generate_lesson_plan_locked(
                    api_key=api_key,
                    meta_ppct=meta_ppct,
                    bo_sach=book,
                    thoi_luong=int(duration),
                    si_so=int(class_size),
                    teacher_note=teacher_note,
                    model_name="gemini-2.0-flash"
                )
                
                # Check lỗi từ hàm trả về (nếu có)
                if "renderHtml" in data and "sections" not in data: 
                     st.error(data["renderHtml"])
                else:
                    html = render_lesson_plan_html(data)
                    
                    # Kiểm tra chất lượng lần cuối (chỉ warning)
                    ok, feedback = quality_check_lesson_html(html)
                    if not ok:
                        st.warning(f"Lưu ý: {feedback}")
                    
                    st.session_state[_lp_key("last_title")] = lesson_title
                    st.session_state[_lp_key("last_html")] = html
                    _lp_set_active("6) Xem trước & Xuất")
                    st.success("Thành công!")
                    st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")

    # ===============================
    # NÚT XOÁ
    # ===============================
    if clear_btn:
        st.session_state[_lp_key("history")] = []
        st.session_state[_lp_key("last_html")] = ""
        st.session_state[_lp_key("last_title")] = ""
        st.toast("🧹 Đã xoá dữ liệu")
        st.rerun()  
        
# ==============================================================================
# 6. LOGIN
# ==============================================================================
def login_screen():
    c1, c2, c3 = st.columns([1, 1.5, 1])

    with c2:
        st.markdown(
            "<h2 style='text-align:center; color:#1E3A8A'>🔐 HỆ THỐNG ĐĂNG NHẬP</h2>",
            unsafe_allow_html=True
        )

        # ✅ KHAI BÁO TAB ĐẦY ĐỦ
        tab_login, tab_signup = st.tabs(["ĐĂNG NHẬP", "ĐĂNG KÝ"])

        # ======================
        # TAB ĐĂNG NHẬP
        # ======================
        with tab_login:
            u = st.text_input("Tên đăng nhập", key="login_username")
            p = st.text_input("Mật khẩu", type="password", key="login_password")

            if st.button("ĐĂNG NHẬP", type="primary", key="login_btn"):
                client = init_supabase()
                if client:
                    try:
                        res = (
                            client.table("users_pro")
                            .select("*")
                            .eq("username", u)
                            .eq("password", p)
                            .execute()
                        )
                        if res.data:
                            user_data = res.data[0]
                            st.session_state["user"] = {
                                "email": user_data["username"],
                                "fullname": user_data["fullname"],
                                "role": user_data["role"],
                            }
                            st.success("Đăng nhập thành công!")
                            st.rerun()
                        else:
                            st.error("Sai tài khoản hoặc mật khẩu")
                    except Exception as e:
                        st.error(f"Lỗi đăng nhập: {e}")

        # ======================
        # TAB ĐĂNG KÝ
        # ======================
        with tab_signup:
            new_u = st.text_input("Tên đăng nhập mới", key="signup_username")
            new_p = st.text_input("Mật khẩu mới", type="password", key="signup_password")
            new_name = st.text_input("Họ và tên", key="signup_fullname")

            if st.button("TẠO TÀI KHOẢN", key="signup_btn"):
                client = init_supabase()
                if client and new_u and new_p:
                    try:
                        check = (
                            client.table("users_pro")
                            .select("*")
                            .eq("username", new_u)
                            .execute()
                        )
                        if check.data:
                            st.warning("Tên đăng nhập đã tồn tại!")
                        else:
                            client.table("users_pro").insert(
                                {
                                    "username": new_u,
                                    "password": new_p,
                                    "fullname": new_name,
                                    "role": "free",
                                    "usage_count": 0,
                                }
                            ).execute()
                            st.success("Đăng ký thành công! Mời đăng nhập.")
                    except Exception as e:
                        st.error(f"Lỗi đăng ký: {e}")

# ==============================================================================
# 8. ROUTER + SIDEBAR MENU (ỔN ĐỊNH, KHÔNG TRÙNG KEY, KHÔNG MẤT LOGIN)
# ==============================================================================

def dashboard_screen():
    # Dashboard 4 thẻ card, an toàn (CSS đã có sẵn .css-card)
    st.markdown("<div class='css-card'>", unsafe_allow_html=True)
    st.markdown("## 🏠 Dashboard – WEB AI GIÁO VIÊN")
    st.caption("Chọn mô-đun ở thanh bên trái để sử dụng.")
    st.markdown("</div>", unsafe_allow_html=True)

    # 4 cards
    st.markdown("""
    <style>
      .dash-grid {display:grid; grid-template-columns: repeat(4, 1fr); gap: 14px;}
      .dash-card {background:#fff; border:1px solid #E2E8F0; border-radius:14px; padding:16px;}
      .dash-title {font-weight:800; font-size:15px; color:#0F172A; margin:0 0 6px 0;}
      .dash-sub {font-size:13px; color:#64748B; margin:0;}
      .dash-badge {display:inline-block; font-size:11px; font-weight:700; padding:4px 10px; border-radius:999px; background:#EFF6FF; color:#1D4ED8; border:1px solid #BFDBFE;}
    </style>
    <div class="dash-grid">
      <div class="dash-card">
        <div class="dash-title">📘 Trợ lý Soạn bài – Đổi mới phương pháp</div>
        <p class="dash-sub">Tạo giáo án chuẩn CTGDPT 2018 theo môn/lớp/bộ sách.</p>
        <div style="margin-top:10px"><span class="dash-badge">Lesson Planner</span></div>
      </div>
      <div class="dash-card">
        <div class="dash-title">💻 AI EXAM – Soạn giáo án Năng lực số</div>
        <p class="dash-sub">Khung giáo án tích hợp năng lực số.</p>
        <div style="margin-top:10px"><span class="dash-badge">Digital Competency</span></div>
      </div>
      <div class="dash-card">
        <div class="dash-title">📝 AI EXAM EXPERT – Ra đề, KTĐG</div>
        <p class="dash-sub">Ma trận – Đặc tả – Đề – Đáp án theo đúng pháp lý.</p>
        <div style="margin-top:10px"><span class="dash-badge">Exam Engine</span></div>
      </div>
      <div class="dash-card">
        <div class="dash-title">🧠 AI EDU Advisor – Nhận xét, tư vấn</div>
        <p class="dash-sub">Nhận xét, tư vấn chuyên môn (mở rộng sau).</p>
        <div style="margin-top:10px"><span class="dash-badge">Advisor</span></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# --------- Modules placeholder (thầy có thể thay bằng module thật sau) ----------
def module_digital():
    # --- CSS Tùy chỉnh cho Module NLS (Giống giao diện React) ---
    st.markdown("""
    <style>
        .nls-container { background-color: #F8FAFC; padding: 20px; border-radius: 15px; }
        .nls-header { 
            background: linear-gradient(90deg, #1E3A8A 0%, #3B82F6 100%); 
            color: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .nls-card { 
            background: white; padding: 25px; border-radius: 12px; 
            border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; 
        }
        .nls-title { color: #1E3A8A; font-weight: 700; font-size: 16px; margin-bottom: 15px; border-left: 4px solid #3B82F6; padding-left: 10px; }
        .nls-upload-box { 
            border: 2px dashed #93C5FD; background: #EFF6FF; border-radius: 10px; 
            padding: 20px; text-align: center; color: #1E40AF; font-size: 14px;
        }
        .nls-btn {
            width: 100%; background: linear-gradient(90deg, #2563EB 0%, #1D4ED8 100%);
            color: white; font-weight: bold; padding: 12px; border-radius: 8px;
            text-align: center; border: none; cursor: pointer;
        }
        .nls-btn:hover { opacity: 0.9; }
    </style>
    """, unsafe_allow_html=True)

    # --- Header ---
    st.markdown("""
    <div class="nls-header">
        <div>
            <h2 style="margin:0; font-size: 22px;">💻 AI EXAM - SOẠN GIÁO ÁN NLS</h2>
            <p style="margin:5px 0 0 0; opacity: 0.9; font-size: 14px;">Hệ thống tích hợp Năng lực số tự động cho Giáo viên</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- Layout Chính: 2 Cột (Form bên trái, Hướng dẫn bên phải) ---
    col_left, col_right = st.columns([2, 1])

    with col_left:
        # 1. Thông tin bài dạy
        st.markdown('<div class="nls-card">', unsafe_allow_html=True)
        st.markdown('<div class="nls-title">1. Thông tin Kế hoạch bài dạy</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1: textbook = st.selectbox("Bộ sách", ["Kết nối tri thức", "Chân trời sáng tạo", "Cánh Diều"], key="nls_book")
        with c2: subject = st.selectbox("Môn học", ["Toán", "Ngữ văn", "Tin học", "KHTN", "Lịch sử & Địa lí"], key="nls_sub")
        with c3: grade = st.selectbox("Khối lớp", [f"Lớp {i}" for i in range(1, 13)], index=6, key="nls_grade") # Mặc định lớp 3
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. Tài liệu đầu vào
        st.markdown('<div class="nls-card">', unsafe_allow_html=True)
        st.markdown('<div class="nls-title">2. Tài liệu đầu vào (Upload file Word)</div>', unsafe_allow_html=True)
        
        c_up1, c_up2 = st.columns(2)
        with c_up1:
            st.markdown('<div class="nls-upload-box">📂 Tải lên Giáo án gốc<br>(Bắt buộc)</div>', unsafe_allow_html=True)
            file_lesson = st.file_uploader("Chọn file Giáo án", type=['docx'], key="nls_u1", label_visibility="collapsed")
        
        with c_up2:
            st.markdown('<div class="nls-upload-box">📊 Tải lên PPCT<br>(Tùy chọn để AI tham khảo)</div>', unsafe_allow_html=True)
            file_ppct = st.file_uploader("Chọn file PPCT", type=['docx'], key="nls_u2", label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)

        # 3. Tùy chọn & Xử lý
        st.markdown('<div class="nls-card">', unsafe_allow_html=True)
        st.markdown('<div class="nls-title">3. Tùy chọn xử lý</div>', unsafe_allow_html=True)
        
        check_col1, check_col2 = st.columns(2)
        with check_col1: analyze_only = st.checkbox("Chỉ phân tích (Không sửa nội dung)", key="nls_chk1")
        with check_col2: detailed_report = st.checkbox("Kèm báo cáo giải trình chi tiết", key="nls_chk2")

        st.write("") # Spacer
        
        # Nút bấm xử lý
        if st.button("✨ BẮT ĐẦU TÍCH HỢP NĂNG LỰC SỐ", type="primary", use_container_width=True):
            api_key = st.session_state.get("api_key") or SYSTEM_GOOGLE_KEY
            if not api_key:
                st.error("⚠️ Vui lòng nhập API Key ở Tab Hồ Sơ trước!")
            elif not file_lesson:
                st.error("⚠️ Vui lòng tải lên file Giáo án gốc!")
            else:
                with st.spinner("🤖 AI đang phân tích và tích hợp năng lực số... Vui lòng đợi 30s"):
                    # Đọc nội dung file
                    lesson_text = read_file_content(file_lesson, 'docx')
                    ppct_text = read_file_content(file_ppct, 'docx') if file_ppct else ""
                    
                    # Gọi hàm xử lý (Đã định nghĩa ở Bước 1)
                    result_text = generate_nls_lesson_plan(
                        api_key, lesson_text, ppct_text, textbook, subject, grade, analyze_only
                    )
                    
                    # Lưu kết quả vào session
                    st.session_state['nls_result'] = result_text
                    st.success("✅ Đã xử lý xong!")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        # Sidebar thông tin (Giống UI React)
        st.markdown("""
        <div class="nls-card" style="background:#EFF6FF; border:1px solid #BFDBFE;">
            <h4 style="color:#1E3A8A; margin-top:0;">💡 Hướng dẫn nhanh</h4>
            <ol style="font-size:14px; padding-left:15px; color:#334155;">
                <li>Chọn <b>Bộ sách, Môn, Lớp</b>.</li>
                <li>Tải lên <b>Giáo án gốc</b> (File Word .docx).</li>
                <li>Tải lên <b>PPCT</b> (Nếu muốn AI bám sát yêu cầu trường).</li>
                <li>Bấm <b>Bắt đầu</b> và đợi kết quả.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="nls-card">
            <h4 style="color:#1E3A8A; margin-top:0;">🌐 Các miền Năng lực số</h4>
            <ul style="font-size:13px; padding-left:15px; color:#475569;">
                <li>Khai thác dữ liệu & thông tin</li>
                <li>Giao tiếp & Hợp tác số</li>
                <li>Sáng tạo nội dung số</li>
                <li>An toàn & An ninh số</li>
                <li>Giải quyết vấn đề với công nghệ</li>
                <li><b>Ứng dụng AI (Mới)</b></li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    # --- Hiển thị kết quả ---
    if 'nls_result' in st.session_state and st.session_state['nls_result']:
        st.markdown("---")
        st.subheader("📄 KẾT QUẢ GIÁO ÁN NLS")
        
        # Tab xem trước và tải về
        tab_view, tab_download = st.tabs(["Xem trước", "Tải về"])
        
        with tab_view:
            st.markdown(st.session_state['nls_result'])
            
        with tab_download:
            # Tái sử dụng hàm create_word_doc có sẵn trong app.py cũ
            doc_html = st.session_state['nls_result'].replace("\n", "<br>") # Chuyển đổi sơ bộ sang HTML
            st.download_button(
                label="⬇️ Tải Giáo án Word (.doc)",
                data=create_word_doc(doc_html, "Giao_An_NLS"),
                file_name=f"Giao_An_NLS_{subject}_{grade}.doc",
                mime="application/msword",
                type="primary"
            )

def module_advisor():
    st.markdown("<div class='css-card'>", unsafe_allow_html=True)
    st.markdown("## 🧠 AI EDU Advisor – Nhận xét & Tư vấn")
    st.info("Mô-đun đang hoàn thiện. (Sẽ tích hợp sau)")
    st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# ENTRY POINT (ỔN ĐỊNH: sidebar + router theo current_page)
# ==============================================================================
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "dashboard"

if "user" not in st.session_state:
    login_screen()
else:
    with st.sidebar:
        st.markdown("## 🏫 AIEXAM.VN")
        st.caption("WEB AI GIÁO VIÊN")
        st.divider()

        page_map = {
            "🏠 Dashboard": "dashboard",
            "📘 Trợ lý Soạn bài": "lesson_plan",
            "💻 Soạn bài Năng lực số": "digital",
            "📝 Ra đề – KTĐG": "exam",
            "🧠 Nhận xét – Tư vấn": "advisor",
        }

        # chọn theo current_page (đồng bộ)
        reverse_map = {v: k for k, v in page_map.items()}
        current_label = reverse_map.get(st.session_state["current_page"], "🏠 Dashboard")

        menu_label = st.radio(
            "📌 Chọn mô-đun",
            list(page_map.keys()),
            index=list(page_map.keys()).index(current_label),
            key="sidebar_menu_main"
        )

        st.session_state["current_page"] = page_map[menu_label]

        st.divider()
        if st.button("🚪 Đăng xuất", use_container_width=True, key="sb_logout"):
            st.session_state.pop("user", None)
            st.session_state["current_page"] = "dashboard"
            st.rerun()

    # ROUTER
    page = st.session_state["current_page"]

    if page == "dashboard":
        dashboard_screen()
    elif page == "lesson_plan":
        # [MỚI] CHỌN MODULE: Ưu tiên Hướng B (PPCT thật), nếu lỗi fallback về cũ
        if module_lesson_plan_B:
            module_lesson_plan_B(
                SYSTEM_GOOGLE_KEY=SYSTEM_GOOGLE_KEY,
                BOOKS_LIST=BOOKS_LIST,
                EDUCATION_DATA=EDUCATION_DATA,
                FULL_SCOPE_LIST=FULL_SCOPE_LIST,
                create_word_doc_func=create_word_doc,
                model_name="gemini-2.0-flash"
            )
        else:
            module_lesson_plan()
    elif page == "digital":
        module_digital()
    elif page == "advisor":
        module_advisor()
    else:
        main_app()
