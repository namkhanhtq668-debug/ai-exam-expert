import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import pandas as pd
import docx
import json
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
# 0. CÁC HÀM TIỆN ÍCH CỐT LÕI (UTILS)
# ==============================================================================
def clean_json(text):
    """Làm sạch chuỗi JSON trả về từ AI."""
    if not text: return "{}"
    text = str(text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start_idx = text.find('{')
    if start_idx == -1: return "{}"
    text = text[start_idx:]
    try:
        # Xử lý lỗi trailing comma
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        return text
    except:
        return text

def safe_json_loads(text: str):
    """Parse JSON an toàn."""
    clean = clean_json(text)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        try:
            end = clean.rfind('}')
            if end != -1: return json.loads(clean[:end+1])
        except: pass
        return {}

def _html_escape(s): return html.escape(str(s)) if s else ""

def _render_ul(items):
    if not items: return ""
    # Nếu là string đơn thì trả về luôn, nếu là list thì tạo ul
    if isinstance(items, str): return _html_escape(items)
    lis = "".join([f"<li>{_html_escape(x)}</li>" for x in items if str(x).strip()])
    return f"<ul>{lis or ''}</ul>"

def create_word_doc(html_content, title):
    doc_content = f"""<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset='utf-8'><title>{title}</title><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom></w:WordDocument></xml><style>@page {{ size: 21cm 29.7cm; margin: 2cm 2cm 2cm 2cm; }} body {{ font-family: 'Times New Roman'; font-size: 13pt; }} table {{ border-collapse: collapse; width: 100%; border: 1px solid black; }} td, th {{ border: 1px solid black; padding: 5px; vertical-align: top; }}</style></head><body><div class="WordSection1">{html_content}</div></body></html>"""
    return "\ufeff" + doc_content

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG
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

st.set_page_config(page_title="AI EXAM EXPERT v10 – 2026", page_icon="🎓", layout="wide", initial_sidebar_state="collapsed")

# ==============================================================================
# [MODULE NLS] DỮ LIỆU & CẤU HÌNH
# ==============================================================================
NLS_FRAMEWORK_DATA = """
KHUNG NĂNG LỰC SỐ (DIGITAL COMPETENCE FRAMEWORK)
MÔ TẢ CÁC MIỀN NĂNG LỰC VÀ YÊU CẦU CẦN ĐẠT (YCCĐ):
1. MIỀN 1: KHAI THÁC DỮ LIỆU VÀ THÔNG TIN
2. MIỀN 2: GIAO TIẾP VÀ HỢP TÁC
3. MIỀN 3: SÁNG TẠO NỘI DUNG SỐ
4. MIỀN 4: AN TOÀN SỐ
5. MIỀN 5: GIẢI QUYẾT VẤN ĐỀ
6. MIỀN 6: ỨNG DỤNG AI
"""

SYSTEM_INSTRUCTION_NLS = f"""
Bạn là chuyên gia tư vấn giáo dục cao cấp, chuyên về chuyển đổi số.
DỮ LIỆU: {NLS_FRAMEWORK_DATA}
NHIỆM VỤ: Phân tích giáo án và tích hợp NLS.
"""

def generate_nls_lesson_plan(api_key, lesson_content, distribution_content, textbook, subject, grade, analyze_only):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=SYSTEM_INSTRUCTION_NLS)
    user_prompt = f"THÔNG TIN: {textbook}|{subject}|{grade}. NỘI DUNG: {lesson_content}"
    try:
        response = model.generate_content(user_prompt)
        return response.text
    except Exception as e:
        return f"Lỗi AI: {str(e)}"

# Placeholder cho module B nếu chưa có file
try:
    from lesson_ui import module_lesson_plan_B
except ImportError:
    module_lesson_plan_B = None

# ==============================================================================
# 2. DỮ LIỆU CỐ ĐỊNH (CONSTANTS)
# ==============================================================================
FULL_YCCD_DATA = [
  {"id": "L1-SO-01", "mon": "Toán", "lop": 1, "chu_de": "Số và Phép tính", "bai": "Các số đến 100", "yccd": "Đếm, đọc, viết số đến 100."},
  {"id": "L5-DL-01", "mon": "Toán", "lop": 5, "chu_de": "Đo lường", "bai": "Toán chuyển động", "yccd": "Giải bài toán về vận tốc, quãng đường, thời gian."}
]

PPCT_DATA = [
    {"cap_hoc": "Tiểu học", "mon": "Toán", "lop": "Lớp 5", "bo_sach": "Kết nối tri thức", "tuan": 1, "tiet": 1, "bai_id": "T5-KNTT-T1-1", "ten_bai": "Ôn tập khái niệm phân số"},
]

APP_CONFIG = {"name": "AI EXAM EXPERT v10 – 2026", "role": "Trợ lý chuyên môn Cấp Sở"}

EDUCATION_DATA = {
    "tieu_hoc": {"label": "Tiểu học", "grades": ["Lớp 1", "Lớp 2", "Lớp 3", "Lớp 4", "Lớp 5"], "subjects": ["Toán", "Tiếng Việt", "Tiếng Anh", "Tin học", "Khoa học", "LS&ĐL", "Đạo đức", "TN&XH", "Công nghệ", "Âm nhạc", "Mĩ thuật", "GDTC", "HĐTN"], "legal": "Thông tư 27"},
    "thcs": {"label": "THCS", "grades": ["Lớp 6", "Lớp 7", "Lớp 8", "Lớp 9"], "subjects": ["Ngữ văn", "Toán", "Tiếng Anh", "KHTN", "LS&ĐL", "GDCD", "Tin học", "Công nghệ", "GDTC", "Âm nhạc", "Mĩ thuật", "HĐTN"], "legal": "Thông tư 22"},
    "thpt": {"label": "THPT", "grades": ["Lớp 10", "Lớp 11", "Lớp 12"], "subjects": ["Ngữ văn", "Toán", "Tiếng Anh", "Vật lí", "Hóa học", "Sinh học", "Lịch sử", "Địa lí", "GDKT&PL", "Tin học", "Công nghệ", "Âm nhạc", "Mĩ thuật", "GDTC"], "legal": "Cấu trúc 2025"}
}

BOOKS_LIST = ["Kết nối tri thức", "Chân trời sáng tạo", "Cánh Diều", "Cùng khám phá", "Vì sự bình đẳng"]
FULL_SCOPE_LIST = ["Khảo sát đầu năm", "Giữa kì 1", "Cuối kì 1", "Giữa kì 2", "Cuối kì 2"]
# ==============================================================================
# 3. LOGIC SOẠN GIÁO ÁN (FIXED)
# ==============================================================================

# --- Render HTML ---
def render_lesson_plan_html(data: dict) -> str:
    if "sections" in data:
        return render_lesson_plan_html_from_schema(data)
    return "Lỗi: Dữ liệu không đúng định dạng."

def render_lesson_plan_html_from_schema(data: dict) -> str:
    sections = data.get("sections", {})
    meta = data.get("meta", {})
    
    html_parts = []
    html_parts.append(f"<div style='font-family:Times New Roman; font-size:13pt;'><div style='text-align:center; font-weight:bold; font-size:14pt; margin-bottom:10px;'>KẾ HOẠCH BÀI DẠY</div>")
    html_parts.append(f"<div style='margin-bottom:10px;'><b>Cấp học:</b> {_html_escape(meta.get('cap_hoc', ''))} | <b>Môn:</b> {_html_escape(meta.get('mon', ''))} | <b>Lớp:</b> {_html_escape(meta.get('lop', ''))}<br/><b>Bộ sách:</b> {_html_escape(meta.get('bo_sach', ''))}<br/><b>Tên bài:</b> {_html_escape(meta.get('ten_bai', ''))}<br/><b>Thời lượng:</b> {_html_escape(str(meta.get('thoi_luong', '')))} phút</div>")
    
    section_map = [("I", "I. YÊU CẦU CẦN ĐẠT"), ("II", "II. ĐỒ DÙNG DẠY HỌC"), ("III", "III. CÁC HOẠT ĐỘNG DẠY HỌC"), ("IV", "IV. ĐIỀU CHỈNH SAU BÀI DẠY")]
    
    for key, title in section_map:
        sec = sections.get(key, {})
        html_parts.append(f"<div style='margin:10px 0 6px 0; font-weight:bold;'>{title}</div>")
        
        if key == "III":
            acts = sec.get("hoat_dong", [])
            rows = ""
            for i, act in enumerate(acts, 1):
                gv_html = _render_ul(act.get("gv", []))
                hs_html = _render_ul(act.get("hs", []))
                rows += f"""<tr><td style='width:42px; text-align:center;'><b>{i}</b></td><td style='width:160px;'><b>{_html_escape(act.get('ten',''))}</b></td><td style='width:70px; text-align:center;'>{_html_escape(str(act.get('thoi_gian','')))}</td><td style='width:35%;'>{gv_html}</td><td style='width:35%;'>{hs_html}</td></tr>"""
            html_parts.append(f"<table border='1' style='width:100%; border-collapse:collapse;'><tr><th>STT</th><th>Hoạt động</th><th>Thời gian</th><th>GV</th><th>HS</th></tr>{rows}</table>")
        elif key == "IV":
            html_parts.append(f"<div>{_html_escape(sec.get('dieu_chinh_sau_bai_day', '................................'))}</div>")
        else:
            for sub_k, sub_v in sec.items():
                label = sub_k.replace("_", " ").capitalize()
                content = _render_ul(sub_v) if isinstance(sub_v, list) else _html_escape(sub_v)
                html_parts.append(f"<div><b>{label}:</b>{content}</div>")
                
    html_parts.append("</div>")
    return "\n".join(html_parts)

# --- Schema & AI Logic ---
LESSON_PLAN_SCHEMA = {
    "type": "object",
    "required": ["meta", "sections"], 
    "additionalProperties": True,
    "properties": { "meta": {"type": "object"}, "sections": {"type": "object"} }
}

def validate_lesson_plan(data: dict) -> None:
    try:
        Draft202012Validator.check_schema(LESSON_PLAN_SCHEMA)
        validate(instance=data, schema=LESSON_PLAN_SCHEMA)
    except: pass

def build_lesson_system_prompt_locked(meta: dict, teacher_note: str) -> str:
    return f"""
VAI TRÒ: Giáo viên Tiểu học cốt cán (CTGDPT 2018).
NHIỆM VỤ: Soạn Kế hoạch bài dạy chi tiết.

THÔNG TIN:
- Bài: {meta.get('ten_bai')}
- Lớp: {meta.get('lop')} | Môn: {meta.get('mon')} | Sách: {meta.get('bo_sach')}
- Thời lượng: {meta.get('thoi_luong')} phút | Sĩ số: {meta.get('si_so')}

GHI CHÚ GV: {teacher_note}

YÊU CẦU OUTPUT JSON (BẮT BUỘC):
Trả về JSON duy nhất:
1. "muc_tieu": {{ "yeu_cau_can_dat": [], "pham_chat": [], "nang_luc": [] }}
2. "chuan_bi": {{ "giao_vien": [], "hoc_sinh": [] }}
3. "tien_trinh": Mảng hoạt động. Mỗi cái: 
   {{ "hoat_dong": "Tên", "thoi_gian": "số phút", "cac_buoc": [ {{ "gv": "HĐ GV", "hs": "HĐ HS" }} ] }}
4. "rut_kinh_nghiem": {{ "dieu_chinh_sau_bai_day": "nội dung" }}

QUAN TRỌNG: 
- "tien_trinh" phải đủ 4 pha: Khởi động, Khám phá, Luyện tập, Vận dụng.
- Nội dung phải chi tiết (ít nhất 2 dòng mỗi bên GV/HS).
""".strip()

def enrich_lesson_plan_data_min_detail(data: dict) -> dict:
    """Tự động điền nội dung nếu AI trả về thiếu."""
    if "sections" not in data: return data
    sections = data["sections"]
    if "III" not in sections: sections["III"] = {"hoat_dong": []}
    
    acts = sections["III"]["hoat_dong"]
    required_phases = ["Khởi động", "Khám phá kiến thức", "Luyện tập", "Vận dụng"]
    existing_names = [a.get("ten", "").lower() for a in acts]
    
    # Chèn pha thiếu
    if len(acts) < 4:
        for phase in required_phases:
            if not any(phase.lower().split()[0] in name for name in existing_names):
                acts.append({
                    "ten": phase, "thoi_gian": "5-7 phút", 
                    "gv": [f"GV tổ chức {phase}.", "GV hỗ trợ HS."], 
                    "hs": ["HS tham gia.", "HS báo cáo kết quả."]
                })
    
    # Làm giàu nội dung
    for act in acts:
        if len(act.get("gv", [])) < 2:
            act["gv"] = act.get("gv", []) + ["GV quan sát, nhận xét.", "GV chốt kiến thức."]
        if len(act.get("hs", [])) < 2:
            act["hs"] = act.get("hs", []) + ["HS lắng nghe, ghi chép.", "HS thực hành."]

    sections["III"]["hoat_dong"] = acts
    data["sections"] = sections
    return data

def generate_lesson_plan_locked(api_key: str, meta_ppct: dict, bo_sach: str, thoi_luong: int, si_so: int, teacher_note: str, model_name: str = "gemini-2.0-flash"):
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
        res = model.generate_content(
            json.dumps(req, ensure_ascii=False), 
            generation_config={"response_mime_type": "application/json"}, 
            safety_settings=safe_settings
        )
        data = safe_json_loads(res.text)
        
        # Mapping Data
        if "sections" not in data:
            data["sections"] = {}
            mt = data.get("muc_tieu", {})
            data["sections"]["I"] = {"yeu_cau_can_dat": mt.get("yeu_cau_can_dat", []), "pham_chat": mt.get("pham_chat", []), "nang_luc": mt.get("nang_luc", [])}
            cb = data.get("chuan_bi", {})
            data["sections"]["II"] = {"giao_vien": cb.get("giao_vien", []), "hoc_sinh": cb.get("hoc_sinh", [])}
            
            processed_activities = []
            for act in data.get("tien_trinh", []):
                gv_steps = []
                hs_steps = []
                for step in act.get("cac_buoc", []):
                    if "gv" in step: gv_steps.append(f"- {step['gv']}")
                    if "hs" in step: hs_steps.append(f"- {step['hs']}")
                if not gv_steps and "gv" in act: gv_steps = [str(act["gv"])]
                if not hs_steps and "hs" in act: hs_steps = [str(act["hs"])]
                processed_activities.append({
                    "ten": act.get("hoat_dong", "Hoạt động"),
                    "thoi_gian": str(act.get("thoi_gian", "")),
                    "gv": gv_steps,
                    "hs": hs_steps
                })
            data["sections"]["III"] = {"hoat_dong": processed_activities}
            rkn = data.get("rut_kinh_nghiem", {})
            data["sections"]["IV"] = {"dieu_chinh_sau_bai_day": str(rkn.get("dieu_chinh_sau_bai_day", "................"))}

        if "meta" not in data: data["meta"] = req["meta"]
        data = enrich_lesson_plan_data_min_detail(data) 
        validate_lesson_plan(data)
        return data

    except Exception as e:
        return {"renderHtml": f"Lỗi sinh nội dung: {str(e)}", "title": "Lỗi"}

def quality_check_lesson_html(render_html: str) -> tuple[bool, str]:
    import re
    text = re.sub(r"<[^>]+>", " ", render_html or "")
    if len(text.split()) < 300: return False, "Nội dung quá ngắn."
    return True, ""

# ==============================================================================
# 5. YCCĐ & CLASS HELPER
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
# 6. MODULE UI: LESSON PLAN (ĐÃ SỬA GỌI HÀM)
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
    st.markdown("### 📘 Trợ lý Soạn bài")
    
    with st.form(key=_lp_key("form_settings")):
        c1, c2 = st.columns(2)
        with c1:
            grade = st.selectbox("Lớp", ["Lớp 1", "Lớp 2", "Lớp 3", "Lớp 4", "Lớp 5"], key=_lp_key("grade"))
            subject = st.selectbox("Môn", ["Toán", "Tiếng Việt", "Đạo đức", "TN&XH", "Khoa học"], key=_lp_key("subject"))
            book = st.selectbox("Sách", BOOKS_LIST, key=_lp_key("book"))
        with c2:
            lesson = st.text_input("Tên bài", key=_lp_key("lesson_title_input"))
            duration = st.number_input("Thời lượng (phút)", 35, 90, 35, key=_lp_key("duration"))
            class_size = st.number_input("Sĩ số", 20, 50, 35, key=_lp_key("class_size"))
        
        teacher_note = st.text_area("Ghi chú thêm", key=_lp_key("note"))
        gen_btn = st.form_submit_button("⚡ TẠO GIÁO ÁN", type="primary")

    if gen_btn:
        api_key = _lp_api_key()
        if not api_key:
            st.error("Thiếu API Key")
            st.stop()
            
        meta_ppct = {
            "cap_hoc": "Tiểu học", "mon": subject, "lop": grade, 
            "ten_bai": lesson, "tuan": 1, "tiet": 1, "bai_id": "AUTO"
        }
        
        try:
            with st.spinner("Đang tạo giáo án..."):
                # [ĐÃ SỬA LỖI GỌI HÀM: TRUYỀN THAM SỐ RỜI]
                data = generate_lesson_plan_locked(
                    api_key=api_key,
                    meta_ppct=meta_ppct,
                    bo_sach=book,
                    thoi_luong=int(duration),
                    si_so=int(class_size),
                    teacher_note=teacher_note,
                    model_name="gemini-2.0-flash"
                )
                
                if "renderHtml" in data and "sections" not in data: 
                     st.error(data["renderHtml"])
                else:
                    html = render_lesson_plan_html(data)
                    ok, feedback = quality_check_lesson_html(html)
                    if not ok: st.warning(f"Lưu ý: {feedback}")

                    st.session_state[_lp_key("last_title")] = lesson
                    st.session_state[_lp_key("last_html")] = html
                    _lp_set_active("6) Xem trước & Xuất")
                    st.success("Thành công!")
                    st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")

    # Tabs
    pages = ["1) Thiết lập & Mục tiêu", "6) Xem trước & Xuất"]
    active = _lp_get_active(pages[0])
    nav = st.radio("Điều hướng", pages, index=pages.index(active) if active in pages else 0, key="lp_nav")
    st.session_state["lp_active_page_admin_state"] = nav
    
    if nav == "6) Xem trước & Xuất":
        html_content = st.session_state.get(_lp_key("last_html"), "")
        if html_content:
            st.markdown(f"<div class='paper-view'>{html_content}</div>", unsafe_allow_html=True)
            st.download_button("Tải Word", create_word_doc(html_content, "GA"), "GA.doc")
        else:
            st.info("Chưa có giáo án.")

# ==============================================================================
# 7. CÁC MODULE KHÁC & ROUTER
# ==============================================================================
def dashboard_screen():
    st.title("🏠 Dashboard AI Giáo Viên")

def login_screen():
    st.title("Đăng nhập")
    if st.button("Vào ngay (Demo)"):
        st.session_state["user"] = {"email": "demo@vn", "role": "pro"}
        st.rerun()

def module_digital(): st.info("Module Năng lực số")
def module_advisor(): st.info("Module Tư vấn")

# --- MAIN ENTRY ---
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "dashboard"

if "user" not in st.session_state:
    login_screen()
else:
    with st.sidebar:
        st.title("AI EXAM")
        menu = st.radio("Menu", ["Dashboard", "Trợ lý Soạn bài", "Năng lực số", "Thoát"])
        if menu == "Thoát":
            st.session_state.pop("user")
            st.rerun()
            
    if menu == "Dashboard": dashboard_screen()
    elif menu == "Trợ lý Soạn bài": module_lesson_plan()
    elif menu == "Năng lực số": module_digital()
    else: dashboard_screen()
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
                model_name="gemini-2.0-flash-exp"
            )
        else:
            module_lesson_plan()
    elif page == "digital":
        module_digital()
    elif page == "advisor":
        module_advisor()
    else:
        main_app()
        
