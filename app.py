import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
from flask import Flask, render_template, request, jsonify 
import pandas as pd
import docx
import json
import re
import io
import time
import datetime

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG & KẾT NỐI
# ==============================================================================
# --- [NÂNG CẤP] CẤU HÌNH GIỚI HẠN & THANH TOÁN ---
MAX_FREE_USAGE = 3   # Tài khoản Free: 3 đề
MAX_PRO_USAGE = 15   # Tài khoản Pro: 15 đề

BANK_ID = "VietinBank"   # Đã sửa lỗi chính tả VietinBabk thành VietinBank
BANK_ACC = "0918198687"  
BANK_NAME = "TRAN THANH TUAN" 
PRICE_VIP = 50000        

# Lấy API Key từ Secrets (Két sắt bảo mật)
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    # Tự động lấy Key Gemini của Admin (để khách không phải nhập)
    SYSTEM_GOOGLE_KEY = st.secrets.get("GOOGLE_API_KEY", "")
except:
    SUPABASE_URL = ""
    SUPABASE_KEY = ""
    SYSTEM_GOOGLE_KEY = ""

# Cấu hình trang
st.set_page_config(page_title="AI EXAM EXPERT v10 – 2026", page_icon="🎓", layout="wide", initial_sidebar_state="collapsed")

# ==============================================================================
# 2. KHO DỮ LIỆU TRI THỨC
# ==============================================================================

# A. APP CONFIG & CONTEXT
APP_CONFIG = {
    "name": "AI EXAM EXPERT v10 – 2026",
    "role": "Trợ lý chuyên môn Cấp Sở: Ra đề - Thẩm định - Quản trị hồ sơ.",
    "context": """🎯 1. VAI TRÒ VÀ SỨ MỆNH:
    Bạn là Trợ lý AI Chuyên môn Cấp Sở, tuân thủ tuyệt đối các quy định mới nhất của Bộ GD&ĐT.

    🟦 2. QUY ĐỊNH PHÁP LÝ (BẮT BUỘC):
    2.1. CẤP TIỂU HỌC (Thông tư 27/2020):
       - Đề thi thiết kế theo 3 MỨC ĐỘ: M1 (Nhận biết - 40%), M2 (Kết nối - 30%), M3 (Vận dụng - 30%).
       - Điểm số: Thang 10, làm tròn thành số nguyên (0.5 -> 1).
       - Môn TIẾNG VIỆT: Phần Đọc hiểu phải dùng văn bản MỚI (ngoài SGK). Phần Viết có Chính tả & TLV.

    2.2. CẤP TRUNG HỌC (Thông tư 22/2021 & QĐ 764):
       - Ma trận 4 MỨC ĐỘ: NB (40%) - TH (30%) - VD (20%) - VDC (10%).
       - THPT từ 2025: Cấu trúc 3 phần (TN Nhiều lựa chọn, TN Đúng/Sai, Trả lời ngắn).

    🟦 3. NGUYÊN TẮC:
    - Không trùng lại nội dung SGK (đối với ngữ liệu đọc hiểu).
    - Hình ảnh minh họa phải được mô tả chi tiết."""
}

# B. DANH SÁCH MÔN THỰC HÀNH
PRACTICAL_SUBJECTS = [
    "Tin học", "Công nghệ", "Mĩ thuật", "Âm nhạc", "Khoa học", "Khoa học tự nhiên", "Vật lí", "Hóa học", "Sinh học", "Tin học và Công nghệ"
]

# C. CẤU TRÚC ĐỀ THI
SUBJECT_STRUCTURE_DATA = {
    "THPT_2025": "Phần I: TN Nhiều lựa chọn (0.25đ) | Phần II: TN Đúng/Sai (Max 1đ) | Phần III: Trả lời ngắn (0.5đ)",
    "TieuHoc_TV": "A. Kiểm tra Đọc (10đ) [Đọc tiếng + Đọc hiểu văn bản mới] + B. Kiểm tra Viết (10đ) [Chính tả + TLV].",
    "TieuHoc_Chung": "Trắc nghiệm (60-70%) + Tự luận (30-40%). Mức độ: M1-M2-M3",
    "Toán": "Trắc nghiệm (70%) + Vận dụng (30%)",
    "Ngữ văn": "Đọc hiểu (6.0đ) + Viết (4.0đ)",
    "Tiếng Anh": "Listening (2.5) - Language (2.5) - Reading (2.5) - Writing (2.5)",
    "Mặc định": "NB (40%) - TH (30%) - VD (20%) - VDC (10%)"
}

# D. MENU GIÁO DỤC
EDUCATION_DATA = {
    "tieu_hoc": {
        "label": "Tiểu học",
        "grades": ["Lớp 1", "Lớp 2", "Lớp 3", "Lớp 4", "Lớp 5"],
        "subjects": ["Toán", "Tiếng Việt", "Tiếng Anh", "Đạo đức", "Tự nhiên và Xã hội", "Khoa học", "Lịch sử và Địa lí", "Tin học và Công nghệ", "Giáo dục thể chất", "Âm nhạc", "Mĩ thuật", "Hoạt động trải nghiệm", "Công nghệ", "Tin học"],
        "legal": "Thông tư 27 (3 Mức độ)"
    },
    "thcs": {
        "label": "THCS",
        "grades": ["Lớp 6", "Lớp 7", "Lớp 8", "Lớp 9"],
        "subjects": ["Ngữ văn", "Toán", "Tiếng Anh", "Giáo dục công dân", "Khoa học tự nhiên", "Lịch sử và Địa lí", "Tin học", "Công nghệ", "Giáo dục thể chất", "Âm nhạc", "Mĩ thuật", "HĐTN, HN", "Giáo dục địa phương"],
        "legal": "Thông tư 22 (4 Mức độ)"
    },
    "thpt": {
        "label": "THPT",
        "grades": ["Lớp 10", "Lớp 11", "Lớp 12"],
        "subjects": ["Ngữ văn", "Toán", "Tiếng Anh", "Lịch sử", "Địa lí", "Vật lí", "Hóa học", "Sinh học", "GDKT & PL", "Tin học", "Công nghệ", "Âm nhạc", "Mĩ thuật", "GDTC", "GDQP&AN", "HĐTN, HN"],
        "legal": "Cấu trúc 2025 (QĐ 764)"
    }
}

# E. DANH SÁCH BỘ SÁCH
BOOKS_LIST = [
    "Kết nối tri thức với cuộc sống", "Chân trời sáng tạo", "Cánh Diều", "Cùng khám phá",
    "Vì sự bình đẳng và dân chủ trong giáo dục", "Tin học: Đại học Vinh (Tiểu học)",
    "Tiếng Anh: Global Success", "Tiếng Anh: Family and Friends", "Tiếng Anh: Friends Plus",
    "Tiếng Anh: i-Learn Smart Start", "Tiếng Anh: Explore English",
    "Tin học: Kết nối tri thức", "Tin học: Chân trời sáng tạo", "Tin học: Cánh Diều",
    "Tài liệu Giáo dục địa phương tỉnh Tuyên Quang", "Chuyên đề học tập (THPT)"
]

# F. DANH SÁCH KỲ THI
FULL_SCOPE_LIST = ["Khảo sát chất lượng đầu năm", "Kiểm tra giữa kì 1", "Kiểm tra cuối kì 1", "Kiểm tra giữa kì 2", "Kiểm tra cuối kì 2", "Thi thử Tốt nghiệp THPT", "Thi học sinh giỏi cấp Trường", "Thi học sinh giỏi cấp Huyện/Tỉnh"]
LIMITED_SCOPE_LIST = ["Khảo sát chất lượng đầu năm", "Kiểm tra cuối kì 1", "Kiểm tra cuối kì 2"]

SCOPE_MAPPING = {
    "Khảo sát chất lượng đầu năm": "Ôn tập hè & Tuần 1-2",
    "Kiểm tra giữa kì 1": "Tuần 1 đến Tuần 9",
    "Kiểm tra cuối kì 1": "Tuần 10 đến Tuần 18 (Ôn tập cả HK1)",
    "Kiểm tra giữa kì 2": "Tuần 19 đến Tuần 27",
    "Kiểm tra cuối kì 2": "Tuần 28 đến Tuần 35 (Ôn tập cả HK2)",
    "Thi thử Tốt nghiệp THPT": "Toàn bộ chương trình",
    "Thi học sinh giỏi cấp Trường": "Nâng cao",
    "Thi học sinh giỏi cấp Huyện/Tỉnh": "Chuyên sâu"
}

# G. PHÂN PHỐI CHƯƠNG TRÌNH
CURRICULUM_DATA = {
    "Toán": {
        "Lớp 6": {"Kiểm tra giữa kì 1": "Tập hợp số tự nhiên; Phép tính; Số nguyên tố."},
        "Lớp 12": {"Kiểm tra cuối kì 1": "Nguyên hàm; Tích phân; Phương trình mặt phẳng."}
    }
}

# H. VĂN BẢN PHÁP LÝ
LEGAL_DOCUMENTS = [
    {"code": "CV 7791/2024", "title": "Công văn 7791 (Mới)", "summary": "Hướng dẫn kỹ thuật xây dựng ma trận, đặc tả.", "highlight": True},
    {"code": "QĐ 764/2024", "title": "Cấu trúc THPT 2025", "summary": "Định dạng đề thi mới: TN nhiều lựa chọn, Đúng/Sai, Trả lời ngắn.", "highlight": True},
    {"code": "TT 22/2021", "title": "Đánh giá Trung học", "summary": "4 mức độ: NB-TH-VD-VDC.", "highlight": True},
    {"code": "TT 27/2020", "title": "Đánh giá Tiểu học", "summary": "3 mức độ nhận thức (M1, M2, M3).", "highlight": True},
    {"code": "CV 2345", "title": "KHGD Tiểu học", "summary": "Xây dựng kế hoạch bài dạy, ma trận đề kiểm tra.", "highlight": False},
    {"code": "CV 3175", "title": "Đổi mới PPDH", "summary": "Hướng dẫn kỹ thuật biên soạn câu hỏi.", "highlight": False},
    {"code": "TT 32/2018", "title": "CT GDPT 2018", "summary": "Văn bản gốc quy định Yêu cầu cần đạt.", "highlight": False}
]

# ==============================================================================
# 3. GIAO DIỆN (THEME PRO INDIGO & ADVANCED FONT FIX)
# ==============================================================================
st.markdown("""
<style>
    /* Ẩn Menu mặc định */
    #MainMenu {visibility: hidden; display: none;} 
    header {visibility: hidden; display: none;} 
    footer {visibility: hidden; display: none;}
    div[data-testid="stDecoration"] {display: none;}
    
    /* 1. NỀN TỔNG THỂ */
    .stApp { background-color: #F8FAFC; }
    
    /* 2. HEADER TEXT */
    .header-text {
        background: linear-gradient(90deg, #1E3A8A 0%, #2563EB 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 34px;
        font-family: 'Times New Roman', serif;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 3. BUTTON CHÍNH (Gradient Blue) */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
        color: white;
        border-radius: 8px;
        height: 50px;
        border: none;
        font-weight: 700;
        box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2), 0 2px 4px -1px rgba(37, 99, 235, 0.1);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        transition: all 0.2s ease-in-out;
    }
    
    /* 4. CARD */
    .css-card {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 30px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 25px;
    }
    
    /* 5. CÁC THẺ NHỎ */
    .auto-tag {
        background: #EFF6FF; color: #1D4ED8; padding: 6px 12px; border-radius: 20px; 
        font-size: 11px; font-weight: 700; text-transform: uppercase; border: 1px solid #BFDBFE;
    }

    /* 6. THẺ PHÁP LÝ */
    .legal-card {
        background: #FFFFFF; border-radius: 10px; padding: 15px; margin-bottom: 10px;
        border-left: 4px solid #64748B; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #F1F5F9;
    }
    .highlight-card {
        background: #FEF2F2; border-left: 4px solid #EF4444; padding: 15px; margin-bottom: 10px;
        border-radius: 10px; border: 1px solid #FEE2E2;
    }

    /* 7. INPUT & SELECT BOX */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        border-radius: 8px; border: 1px solid #CBD5E1;
    }
    .struct-label { font-weight: 600; color: #334155; font-size: 0.9em; }

    /* 8. PAPER VIEW - FIX FONT WEB APP */
    @import url('https://fonts.googleapis.com/css2?family=Times+New+Roman&display=swap');
    
    .paper-view {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 14pt !important;
        line-height: 1.5 !important;
        color: #000000 !important;
        background-color: #ffffff !important;
        padding: 50px !important;
        border: 1px solid #d1d5db;
        border-radius: 4px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        text-align: justify;
    }
    .paper-view * {
        font-family: 'Times New Roman', Times, serif !important;
        color: #000000 !important;
    }
    .paper-view h1, .paper-view h2, .paper-view h3, .paper-view strong, .paper-view b {
        font-weight: bold !important;
        font-family: 'Times New Roman', Times, serif !important;
    }
    .paper-view table {
        width: 100% !important; border-collapse: collapse !important; margin: 10px 0 !important;
    }
    .paper-view td, .paper-view th {
        border: 1px solid #000000 !important; padding: 8px !important; font-size: 13pt !important;
    }
    
    /* 9. PRICING CARD (MỚI THÊM) */
    .pricing-card {
        background: white; border: 1px solid #E2E8F0; border-radius: 12px; padding: 25px;
        text-align: center; transition: all 0.3s;
    }
    .pricing-card:hover { transform: translateY(-5px); box-shadow: 0 10px 20px rgba(37,99,235,0.15); border-color: #2563EB; }
    .price-tag { font-size: 28px; font-weight: 800; color: #1E3A8A; margin: 15px 0; }
    .feature-list { text-align: left; margin: 20px 0; color: #475569; line-height: 1.8; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. HÀM XỬ LÝ LOGIC
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
        
        # Gắn nhãn chuẩn Logic React
        if file_type == 'matrix': return f"\n[DỮ LIỆU MA TRẬN TỪ NGƯỜI DÙNG]:\n{content}\n"
        if file_type == 'spec': return f"\n[DỮ LIỆU ĐẶC TẢ TỪ NGƯỜI DÙNG]:\n{content}\n"
    except: return ""
    return content

# [NÂNG CẤP] Hàm làm sạch JSON mạnh mẽ hơn để tránh lỗi Extra Data
def clean_json(text):
    text = text.strip()
    if "```" in text:
        parts = re.split(r'```(?:json)?', text)
        if len(parts) > 1: text = parts[1]
    
    start_idx = text.find('{')
    if start_idx == -1: return "{}"
    text = text[start_idx:]
    
    try:
        decoder = json.JSONDecoder()
        obj, idx = decoder.raw_decode(text)
        return json.dumps(obj)
    except:
        end_idx = text.rfind('}')
        if end_idx != -1: return text[:end_idx+1]
        return text

# --- [NÂNG CẤP] HÀM TẠO FILE WORD CHUẨN FONT XML ---
def create_word_doc(html, title):
    doc_content = f"""
    <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
    <head>
        <meta charset='utf-8'>
        <title>{title}</title>
        <xml>
            <w:WordDocument>
                <w:View>Print</w:View>
                <w:Zoom>100</w:Zoom>
                <w:DoNotOptimizeForBrowser/>
            </w:WordDocument>
        </xml>
        <style>
            @page {{ size: 21cm 29.7cm; margin: 2cm 2cm 2cm 2cm; mso-page-orientation: portrait; }}
            body {{ font-family: 'Times New Roman', serif; font-size: 13pt; line-height: 1.3; }}
            p, div, span, li, td, th {{ font-family: 'Times New Roman', serif; mso-ascii-font-family: 'Times New Roman'; mso-hansi-font-family: 'Times New Roman'; color: #000000; }}
            table {{ border-collapse: collapse; width: 100%; }}
            td, th {{ border: 1px solid black; padding: 5px; }}
        </style>
    </head>
    <body><div class="WordSection1">{html}</div></body>
    </html>
    """
    return "\ufeff" + doc_content

def get_knowledge_context(subject, grade, book, scope):
    try:
        data = CURRICULUM_DATA.get(subject, {}).get(grade, {}).get(book, {})
        key = next((k for k in data.keys() if k in scope or scope in k), None)
        if key: return f"NỘI DUNG CHƯƠNG TRÌNH ({key}): {data[key]}"
        week_info = SCOPE_MAPPING.get(scope, scope)
        return f"NỘI DUNG TỰ TRA CỨU: Bám sát chuẩn kiến thức kĩ năng môn {subject} {grade} - Bộ sách {book}. Thời điểm: {week_info}."
    except: return "NỘI DUNG: Theo chuẩn CTGDPT 2018."

# ==============================================================================
# 5. GIAO DIỆN CHÍNH
# ==============================================================================
def main_app():
    if 'dossier' not in st.session_state: st.session_state['dossier'] = []
    
    user = st.session_state.get('user', {'role': 'guest'})
    is_admin = user.get('role') == 'admin'

    # --- HEADER ---
    c1, c2, c3 = st.columns([3, 0.8, 0.8])
    with c1:
        st.markdown(f"<div class='header-text'>🎓 {APP_CONFIG['name']}</div>", unsafe_allow_html=True)
        st.caption(f"User: {user.get('fullname', user.get('email', 'Guest'))} | Role: {user.get('role', '').upper()}")
    
    # Nút RESET
    with c2:
        if st.button("🔄 LÀM MỚI", use_container_width=True): 
            st.session_state['dossier'] = [] 
            st.toast("Đã làm mới hệ thống!", icon="🧹")
            time.sleep(0.5)
            st.rerun()
            
    # Nút ĐĂNG XUẤT
    with c3:
        if st.button("ĐĂNG XUẤT", use_container_width=True):
            st.session_state.pop('user', None)
            st.rerun()

    # --- CẬP NHẬT TAB MỚI: THÊM '💎 NÂNG CẤP VIP' ---
    tabs = st.tabs(["🚀 THIẾT LẬP", "📄 XEM ĐỀ", "✅ ĐÁP ÁN", "⚖️ PHÁP LÝ", "💎 NÂNG CẤP VIP", "📂 HỒ SƠ"])

    # --- TAB 1: THIẾT LẬP ---
    with tabs[0]:
        st.markdown('<div class="css-card">', unsafe_allow_html=True)
        
        col_year, col_lvl = st.columns(2)
        with col_year: school_year = st.selectbox("Năm học", ["2024-2025", "2025-2026", "2026-2027"], index=1)
        with col_lvl: level_key = st.radio("Cấp học", ["Tiểu học", "THCS", "THPT"], horizontal=True)
        
        curr_lvl = "tieu_hoc" if level_key == "Tiểu học" else "thcs" if level_key == "THCS" else "thpt"
        edu = EDUCATION_DATA[curr_lvl]

        c1, c2, c3, c4 = st.columns(4)
        with c1: grade = st.selectbox("Khối lớp", edu["grades"])
        with c2: subject = st.selectbox("Môn học", edu["subjects"])
        with c3: book = st.selectbox("Bộ sách", BOOKS_LIST)
        
        available_scopes = FULL_SCOPE_LIST
        if curr_lvl == "tieu_hoc" and grade in ["Lớp 1", "Lớp 2", "Lớp 3"]:
            available_scopes = LIMITED_SCOPE_LIST 
        
        with c4: scope = st.selectbox("Thời điểm", available_scopes)

        if curr_lvl == "thpt":
            struct_info = SUBJECT_STRUCTURE_DATA["THPT_2025"]
        elif curr_lvl == "tieu_hoc":
            if subject == "Tiếng Việt":
                struct_info = SUBJECT_STRUCTURE_DATA["TieuHoc_TV"]
            else:
                struct_info = SUBJECT_STRUCTURE_DATA["TieuHoc_Chung"]
        else:
            struct_info = SUBJECT_STRUCTURE_DATA.get(subject, SUBJECT_STRUCTURE_DATA['Mặc định'])
            
        st.info(f"💡 **Cấu trúc:** {struct_info} | **Pháp lý:** {edu['legal']}")

        uc1, uc2 = st.columns(2)
        with uc1: mt_file = st.file_uploader("📂 Ma trận (Word/Excel)", type=['docx','xlsx'])
        with uc2: dt_file = st.file_uploader("📝 Đặc tả (Word/Excel)", type=['docx','xlsx'])
        
        auto_mode = False
        if not mt_file and not dt_file:
            auto_mode = True
            st.markdown('<div style="text-align:center;"><span class="auto-tag">✨ CHẾ ĐỘ TỰ ĐỘNG: AI SẼ TỰ XÂY DỰNG MA TRẬN & ĐẶC TẢ</span></div>', unsafe_allow_html=True)

        user_req = st.text_area("Ghi chú chuyên môn:", "Ví dụ: Đề cần phân loại học sinh giỏi...", height=80)

        # --- CÔNG CỤ CẤU HÌNH SỐ LƯỢNG ---
        st.markdown("---")
        st.markdown("##### 🛠 CẤU TRÚC ĐỀ THI MONG MUỐN")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1: 
            num_choice = st.number_input("Trắc nghiệm (Số câu)", min_value=0, max_value=100, value=10, step=1, key="num_choice")
        with col_s2: 
            num_essay = st.number_input("Tự luận (Số câu)", min_value=0, max_value=20, value=2, step=1, key="num_essay")
        with col_s3: 
            num_practice = st.number_input("Thực hành (Bài)", min_value=0, max_value=10, value=0, step=1, key="num_practice")

        st.markdown("---")
        b1, b2, b3 = st.columns([1, 1, 2])
        with b1: num_exams = st.number_input("Số lượng đề", 1, 5, 1)
        with b2: start_code = st.number_input("Mã đề từ", 101, 999, 101)
        with b3:
            st.write(""); st.write("")
            if st.button("⚡ KHỞI CHẠY (AI STUDIO ENGINE)", type="primary", use_container_width=True):
                client = init_supabase()
                if client:
                    try:
                        # 1. LẤY THÔNG TIN NGƯỜI DÙNG TỪ DB
                        current_user_db = client.table('users_pro').select("*").eq('username', user.get('email')).execute()
                        if current_user_db.data:
                            db_role = current_user_db.data[0]['role']
                            usage_count = current_user_db.data[0].get('usage_count', 0)
                            
                            is_blocked = False
                            msg_blocked = ""

                            # 2. KIỂM TRA GIỚI HẠN (CẬP NHẬT LOGIC MỚI: CHẶN CẢ PRO NẾU QUÁ 15 LẦN)
                            if db_role == 'free' and usage_count >= MAX_FREE_USAGE:
                                is_blocked = True
                                msg_blocked = f"🔒 HẾT LƯỢT DÙNG THỬ! (Bạn đã tạo {usage_count}/{MAX_FREE_USAGE} đề). Vui lòng nâng cấp PRO."
                            elif db_role == 'pro' and usage_count >= MAX_PRO_USAGE:
                                is_blocked = True
                                msg_blocked = f"🔒 HẾT LƯỢT GÓI PRO! (Bạn đã tạo {usage_count}/{MAX_PRO_USAGE} đề). Vui lòng gia hạn."

                            if is_blocked:
                                st.error(msg_blocked)
                                st.info("💎 Vào tab 'NÂNG CẤP VIP' để gia hạn.")
                            else:
                                # 3. NẾU ĐƯỢC PHÉP -> CHẠY AI
                                api_key = st.session_state.get('api_key', '')
                                
                                # [NÂNG CẤP] Tự động lấy Key của Admin nếu user không nhập
                                if not api_key: api_key = SYSTEM_GOOGLE_KEY 
                                
                                if not api_key: st.toast("⚠️ Vui lòng nhập API Key ở Tab Hồ Sơ!", icon="❌")
                                else:
                                    with st.spinner(f"🔮 AI đang soạn đề... (Lần thứ: {usage_count + 1})"):
                                        txt_mt = read_file_content(mt_file, 'matrix')
                                        txt_dt = read_file_content(dt_file, 'spec')
                                        knowledge_context = get_knowledge_context(subject, grade, book, scope)
                                        
                                        # [NÂNG CẤP] XỬ LÝ ĐẶC BIỆT CHO MÔN TIN HỌC (YCCĐ Lớp 3,4,5)
                                        special_prompt = ""
                                        if (subject == "Tin học" or subject == "Tin học và Công nghệ") and curr_lvl == "tieu_hoc":
                                            special_prompt = f"""
                                            ⚠️ YÊU CẦU ĐẶC BIỆT CHO MÔN TIN HỌC (Theo YCCĐ Chương trình GDPT 2018):
                                            CẤU TRÚC ĐỀ THI BÁM SÁT 6 CHỦ ĐỀ (A, B, C, D, E, F) VÀ NĂNG LỰC ĐẶC THÙ (NLa-NLe):
                                            
                                            1. PHẦN TRẮC NGHIỆM ({num_choice} câu):
                                               - Kiểm tra kiến thức về Máy tính (Chủ đề A), Internet (Chủ đề B), Tổ chức lưu trữ (Chủ đề C), Đạo đức số (Chủ đề D).
                                               - Lớp 3: Nhận diện chuột, bàn phím, tư thế ngồi, thông tin và xử lý thông tin.
                                               - Lớp 4: Phần cứng/phần mềm, gõ phím, thư mục, bản quyền phần mềm.
                                               - Lớp 5: Hợp tác tìm kiếm, cây thư mục, bản quyền nội dung, quy tắc ứng xử trên mạng.
                                            
                                            2. PHẦN THỰC HÀNH/TỰ LUẬN ({num_essay} câu):
                                               - Kiểm tra kỹ năng Ứng dụng (Chủ đề E) và Giải quyết vấn đề (Chủ đề F).
                                               - Lớp 3: Tạo bài trình chiếu đơn giản, thao tác chuột.
                                               - Lớp 4: Soạn thảo văn bản tiếng Việt, tạo bài trình chiếu có hiệu ứng, làm quen lập trình trực quan.
                                               - Lớp 5: Định dạng văn bản nâng cao, sử dụng biến/cấu trúc lặp trong lập trình trực quan.
                                            """

                                        SYSTEM_PROMPT = f"""
                                        {APP_CONFIG['context']}
                                        I. THÔNG TIN ĐẦU VÀO:
                                        - Năm học: {school_year} | Cấp: {level_key} | Môn: {subject} | Lớp: {grade} | Bộ sách: "{book}"
                                        - {knowledge_context}
                                        II. LUẬT RA ĐỀ:
                                        - Tiểu học: 3 mức độ. - Trung học: 4 mức độ.
                                        III. AUTO-DETECT: { "TỰ XÂY DỰNG MA TRẬN & ĐẶC TẢ" if auto_mode else "TUÂN THỦ FILE UPLOAD" }
                                        {special_prompt}
                                        IV. OUTPUT JSON: {{ "title": "...", "content": "HTML...", "matrixHtml": "...", "specHtml": "...", "answers": "HTML..." }}
                                        V. LIST FILE: De_Kiem_Tra_[CODE].docx, Ma_Tran_[CODE].docx, Ban_Dac_Ta_[CODE].docx, Dap_An_[CODE].docx
                                        V. IMPORTANT: OUTPUT RAW JSON ONLY. NO EXTRA TEXT. NO COMMENTS.
                                        """

                                        try:
                                            genai.configure(api_key=api_key)
                                            model = genai.GenerativeModel('gemini-3-pro-preview', system_instruction=SYSTEM_PROMPT)
                                            new_exams = []
                                            for i in range(num_exams):
                                                code = start_code + i
                                                prompt = SYSTEM_PROMPT.replace("[CODE]", str(code))
                                                req = f"DATA: {txt_mt} {txt_dt}\nNOTE: {user_req}\nSTRUCT: {num_choice} TN, {num_essay} TL, {num_practice} TH\nTASK: Exam {i+1} (Code {code})"
                                                res = model.generate_content(req, generation_config={"response_mime_type": "application/json"})
                                                
                                                try:
                                                    clean_text = clean_json(res.text)
                                                    data = json.loads(clean_text)
                                                    data['id'] = str(code); data['title'] = f"Đề {subject} {grade} - {scope} (Mã {code})"
                                                    
                                                    # [NÂNG CẤP] TỰ ĐỘNG LƯU VÀO KHO
                                                    save_data = {"username": user.get('email'), "title": data['title'], "exam_data": data}
                                                    client.table('exam_history').insert(save_data).execute()
                                                    
                                                    new_exams.append(data)
                                                except Exception as e:
                                                    st.error(f"Lỗi phân tích đề {code}: {e}")
                                                    continue
                                            
                                            st.session_state['dossier'] = new_exams + st.session_state['dossier']
                                            client.table('users_pro').update({'usage_count': usage_count + 1}).eq('username', user.get('email')).execute()
                                            
                                            limit_show = MAX_PRO_USAGE if db_role == 'pro' else MAX_FREE_USAGE
                                            st.success(f"✅ Tạo thành công! (Đã dùng: {usage_count + 1}/{limit_show})")
                                        except Exception as e: st.error(f"Lỗi AI: {e}")
                    except Exception as e: st.error(f"Lỗi DB: {e}")
                else: st.error("Lỗi kết nối.")
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[1]:
        if not st.session_state['dossier']: st.info("👈 Chưa có dữ liệu.")
        else:
            all_e = st.session_state['dossier']
            sel = st.selectbox("Chọn mã đề:", range(len(all_e)), format_func=lambda x: f"[{all_e[x]['id']}] {all_e[x]['title']}")
            curr = all_e[sel]
            
            st1, st2, st3 = st.tabs(["📄 NỘI DUNG ĐỀ", "📊 MA TRẬN", "📝 ĐẶC TẢ"])
            
            with st1:
                st.markdown(f"""<div class="paper-view">{curr.get('content', '')}</div>""", unsafe_allow_html=True)
                footer = f"<br/><center><p>{APP_CONFIG['name']}</p></center>"
                if is_admin or user.get('role') == 'pro': 
                    st.download_button("⬇️ Tải Đề (.doc)", create_word_doc(curr.get('content', '') + footer, curr['title']), f"De_{curr['id']}.doc", type="primary")
                else: st.warning("🔒 Nâng cấp PRO để tải file Word")
            
            with st2:
                st.markdown(curr.get('matrixHtml', 'Không có dữ liệu ma trận'), unsafe_allow_html=True)
                if is_admin or user.get('role') == 'pro': st.download_button("⬇️ Tải Ma trận", create_word_doc(curr['matrixHtml'], "MaTran"), f"MaTran_{curr['id']}.doc")

            with st3:
                st.markdown(curr.get('specHtml', 'Không có dữ liệu đặc tả'), unsafe_allow_html=True)
                if is_admin or user.get('role') == 'pro': st.download_button("⬇️ Tải Đặc tả", create_word_doc(curr['specHtml'], "DacTa"), f"DacTa_{curr['id']}.doc")

    # --- TAB 3: ĐÁP ÁN ---
    with tabs[2]:
        if st.session_state['dossier']:
            curr = st.session_state['dossier'][sel]
            if is_admin or user.get('role') == 'pro':
                st.markdown(f"""<div class="paper-view">{curr.get('answers','Chưa có đáp án')}</div>""", unsafe_allow_html=True)
                st.download_button("⬇️ Tải Đáp án (.doc)", create_word_doc(curr.get('answers',''), "DapAn"), f"DA_{curr['id']}.doc")
            else: st.info("🔒 Nâng cấp PRO để xem và tải Đáp án chi tiết.")
        else: st.info("Chưa có dữ liệu.")

    # --- TAB 4: PHÁP LÝ ---
    with tabs[3]:
        for doc in LEGAL_DOCUMENTS:
            cls = "highlight-card" if doc.get('highlight') else "legal-card"
            st.markdown(f"""<div class="{cls}" style="padding:15px; margin-bottom:10px; border-radius:10px;"><span style="background:#1e293b; color:white; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold">{doc['code']}</span><span style="font-weight:bold; color:#334155; margin-left:8px">{doc['title']}</span><p style="font-size:13px; color:#64748b; margin:5px 0 0 0">{doc['summary']}</p></div>""", unsafe_allow_html=True)
    
    # --- TAB 5: NÂNG CẤP VIP (MỚI BỔ SUNG) ---
    with tabs[4]:
        st.markdown("<h3 style='text-align: center; color: #1E3A8A;'>🚀 BẢNG GIÁ & NÂNG CẤP VIP</h3>", unsafe_allow_html=True)
        col_free, col_pro = st.columns(2)
        
        with col_free:
            st.markdown(f"""
            <div class="pricing-card">
                <h3>Gói FREE</h3>
                <div class="price-tag">0đ</div>
                <div class="feature-list">
                    ✅ Tạo thử <b>{MAX_FREE_USAGE} đề</b><br>
                    ❌ Tải file Word<br>
                    ❌ Xem đáp án chi tiết<br>
                    ❌ Hỗ trợ kỹ thuật
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_pro:
            st.markdown(f"""
            <div class="pricing-card" style="border: 2px solid #2563EB;">
                <h3 style="color: #2563EB;">Gói PRO VIP</h3>
                <div class="price-tag">{PRICE_VIP:,.0f}đ / gói</div>
                <div class="feature-list">
                    ✅ <b>Tạo tối đa {MAX_PRO_USAGE} đề</b><br>
                    ✅ <b>Tải file Word chuẩn (In được ngay)</b><br>
                    ✅ <b>Xem & Tải Đáp án/Ma trận/Đặc tả</b><br>
                    ✅ Hỗ trợ ưu tiên 24/7
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("📲 QUÉT MÃ QR ĐỂ THANH TOÁN TỰ ĐỘNG")
        
        # Tạo link VietQR động
        content_ck = f"NAP VIP {user.get('email')}"
        qr_url = f"https://img.vietqr.io/image/{BANK_ID}-{BANK_ACC}-compact.png?amount={PRICE_VIP}&addInfo={content_ck}&accountName={BANK_NAME}"
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(qr_url, caption="Mã QR VietQR", width=300)
        with c2:
            st.info(f"""
            **HƯỚNG DẪN THANH TOÁN:**
            1. Mở App Ngân hàng bất kỳ.
            2. Chọn **Quét Mã QR**.
            3. Quét mã bên cạnh (Hệ thống tự điền Số tiền & Nội dung).
            4. Bấm Chuyển khoản.
            
            **Hoặc chuyển khoản thủ công:**
            * Ngân hàng: **{BANK_ID}**
            * Số TK: **{BANK_ACC}**
            * Chủ TK: **{BANK_NAME}**
            * Số tiền: **{PRICE_VIP:,.0f}đ**
            * Nội dung: `{content_ck}`
            
            👉 *Sau khi chuyển khoản, vui lòng nhắn Zalo {BANK_ACC} để kích hoạt ngay!*
            """)

    # --- TAB 6: HỒ SƠ & LỊCH SỬ (NÂNG CẤP LOAD TỪ SUPABASE) ---
    with tabs[5]:
        c1, c2 = st.columns([2, 1])
        with c1: 
            st.write(f"**👤 Xin chào: {user.get('fullname')}**")
            st.write("---")
            st.subheader("🗂️ KHO ĐỀ CỦA BẠN (Đã lưu vĩnh viễn)")
            
            # Nút tải lại lịch sử
            if st.button("🔄 Tải lại danh sách đề đã lưu"):
                client = init_supabase()
                if client:
                    try:
                        history_res = client.table('exam_history').select("*").eq('username', user.get('email')).order('id', desc=True).execute()
                        if history_res.data:
                            saved_exams = [item['exam_data'] for item in history_res.data]
                            st.session_state['dossier'] = saved_exams
                            st.success(f"Đã tải {len(saved_exams)} đề từ kho lưu trữ!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.info("Bạn chưa lưu đề nào.")
                    except: st.error("Lỗi tải lịch sử.")
            
            if st.session_state['dossier']:
                for e in st.session_state['dossier']: st.write(f"📄 {e['title']}")
            else: st.caption("Chưa có dữ liệu hiển thị.")

        with c2: 
            k = st.text_input("🔑 API Key Gemini (Nếu có)", type="password", key="api_key_in")
            if k: st.session_state['api_key'] = k

    st.markdown("---")
    st.markdown("""<div style="text-align: center; color: #64748b; font-size: 14px; padding: 20px;"><strong>AI EXAM EXPERT v10</strong> © Tác giả: <strong>Trần Thanh Tuấn</strong> – Trường Tiểu học Hồng Thái – Năm 2026.<br>SĐT: 0918198687</div>""", unsafe_allow_html=True)

# ==============================================================================
# 6. LOGIN
# ==============================================================================
def login_screen():
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.markdown("<br><h2 style='text-align:center; color: #1E3A8A;'>🔐 HỆ THỐNG ĐĂNG NHẬP</h2>", unsafe_allow_html=True)
        tab_login, tab_signup = st.tabs(["ĐĂNG NHẬP", "ĐĂNG KÝ MỚI"])
        
        with tab_login:
            st.write("")
            u = st.text_input("Tên đăng nhập", key="l_user")
            p = st.text_input("Mật khẩu", type="password", key="l_pass")
            if st.button("ĐĂNG NHẬP NGAY", type="primary", use_container_width=True):
                client = init_supabase()
                if client:
                    try:
                        res = client.table('users_pro').select("*").eq('username', u).eq('password', p).execute()
                        if res.data:
                            user_data = res.data[0]
                            st.session_state['user'] = {"email": user_data['username'], "fullname": user_data['fullname'], "role": user_data['role']}
                            st.toast(f"Xin chào {user_data['fullname']}!", icon="🎉"); time.sleep(0.5); st.rerun()
                        else: st.error("Sai thông tin đăng nhập.")
                    except Exception as e: st.error(f"Lỗi: {e}")
        
        with tab_signup:
            st.write("")
            new_u = st.text_input("Tên đăng nhập mới", key="s_user")
            new_p = st.text_input("Mật khẩu mới", type="password", key="s_pass")
            new_name = st.text_input("Họ và tên", key="s_name")
            if st.button("TẠO TÀI KHOẢN", use_container_width=True):
                client = init_supabase()
                if client and new_u and new_p:
                    try:
                        check = client.table('users_pro').select("*").eq('username', new_u).execute()
                        if check.data: st.warning("Tên này đã có người dùng!")
                        else:
                            client.table('users_pro').insert({"username": new_u, "password": new_p, "fullname": new_name, "role": "free", "usage_count": 0}).execute()
                            st.success("Đăng ký thành công! Mời đăng nhập.")
                    except Exception as e: st.error(f"Lỗi: {e}")

if 'user' not in st.session_state: login_screen()
else: main_app()
