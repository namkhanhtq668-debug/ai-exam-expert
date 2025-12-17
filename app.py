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
import requests # [THÊM] Thư viện để gọi API SePay kiểm tra tiền

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG & KẾT NỐI
# ==============================================================================
# --- CẤU HÌNH GIỚI HẠN SỬ DỤNG ---
MAX_FREE_USAGE = 3   # Tài khoản Free: 3 đề
MAX_PRO_USAGE = 15   # Tài khoản Pro: 15 đề

# --- [BỔ SUNG] CẤU HÌNH KHUYẾN MẠI & HOA HỒNG ---
BONUS_PER_REF = 0    # Đăng ký mới: Không tặng lượt (Chỉ lưu mã)
BONUS_PRO_REF = 3    # Mua Pro lần đầu có mã: Tặng 3 lượt
DISCOUNT_AMT = 0     # Không giảm giá tiền (Giữ nguyên giá gốc)
COMMISSION_AMT = 10000 # Hoa hồng cho người giới thiệu

# --- CẤU HÌNH THANH TOÁN (VIETQR) ---
BANK_ID = "VietinBank"   
BANK_ACC = "107878907329"  
BANK_NAME = "TRAN THANH TUAN" 
PRICE_VIP = 50000        

# Lấy API Key từ Secrets (Két sắt bảo mật)
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    # Tự động lấy Key Gemini của Admin (để khách không phải nhập)
    SYSTEM_GOOGLE_KEY = st.secrets.get("GOOGLE_API_KEY", "")
    # [THÊM] Token SePay để check tiền tự động
    SEPAY_API_TOKEN = st.secrets.get("SEPAY_API_TOKEN", "") 
except:
    SUPABASE_URL = ""
    SUPABASE_KEY = ""
    SYSTEM_GOOGLE_KEY = ""
    SEPAY_API_TOKEN = ""

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

# [CẬP NHẬT] Hàm làm sạch JSON mạnh mẽ hơn để tránh lỗi Extra Data
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

# [CẬP NHẬT] Hàm tạo File Word chuẩn Font XML
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

# --- [BỔ SUNG] HÀM CHECK TIỀN TỰ ĐỘNG (Dùng SePay) ---
def check_sepay_transaction(amount, content_search):
    token = st.secrets.get("SEPAY_API_TOKEN", "")
    if not token: return False
    try:
        url = "https://my.sepay.vn/userapi/transactions/list"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            for t in data.get('transactions', []):
                # Kiểm tra số tiền và nội dung
                if float(t['amount_in']) >= amount and content_search in t['transaction_content']:
                    return True
    except:
        return False
    return False

# ==============================================================================
# 5. GIAO DIỆN CHÍNH
# ==============================================================================
def main_app():
    if 'dossier' not in st.session_state: st.session_state['dossier'] = []
    
    user = st.session_state.get('user', {'role': 'guest'})
    is_admin = user.get('role') == 'admin'

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
    tabs = st.tabs(["🚀 THIẾT LẬP", "📄 XEM ĐỀ", "✅ ĐÁP ÁN", "⚖️ PHÁP LÝ", "💎 NÂNG CẤP VIP", "💰 ĐỐI TÁC", "📂 HỒ SƠ"])

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
                            user_data = current_user_db.data[0]
                            db_role = user_data['role']
                            usage_count = user_data.get('usage_count', 0)
                            
                            # [NÂNG CẤP] TÍNH TỔNG LƯỢT DÙNG (CÓ BONUS)
                            bonus_turns = user_data.get('bonus_turns', 0)
                            limit_check = MAX_PRO_USAGE if db_role == 'pro' else (MAX_FREE_USAGE + bonus_turns)

                            if usage_count >= limit_check:
                                st.error(f"🔒 HẾT LƯỢT! (Bạn đã dùng {usage_count}/{limit_check}). Vui lòng gia hạn hoặc giới thiệu bạn bè.")
                                st.info("💎 Vào tab 'NÂNG CẤP VIP' để gia hạn.")
                            else:
                                api_key = st.session_state.get('api_key', '')
                                if not api_key: api_key = SYSTEM_GOOGLE_KEY 
                                
                                if not api_key: st.toast("⚠️ Vui lòng nhập API Key ở Tab Hồ Sơ!", icon="❌")
                                else:
                                    with st.spinner(f"🔮 AI đang soạn đề... (Lần thứ: {usage_count + 1})"):
                                        txt_mt = read_file_content(mt_file, 'matrix')
                                        txt_dt = read_file_content(dt_file, 'spec')
                                        knowledge_context = get_knowledge_context(subject, grade, book, scope)
                                        
                                        # [NÂNG CẤP] XỬ LÝ ĐẶC BIỆT CHO TIẾNG VIỆT TIỂU HỌC (TÁCH 2 BÀI)
                                        special_prompt = ""
                                        if subject == "Tiếng Việt" and curr_lvl == "tieu_hoc":
                                            special_prompt = f"""
                                            ⚠️ YÊU CẦU ĐẶC BIỆT CHO MÔN TIẾNG VIỆT (Theo Thông tư 27/2020):
                                            BẮT BUỘC TÁCH ĐỀ THI THÀNH 2 BÀI KIỂM TRA RIÊNG BIỆT (A và B):
                                            
                                            -------- BÀI A: KIỂM TRA ĐỌC (10 điểm) --------
                                            1. Đọc thành tiếng: (Chỉ cần ghi hướng dẫn chung: "GV cho HS bốc thăm văn bản...").
                                            2. Đọc hiểu: Cung cấp 1 văn bản mới (ngoài SGK) và soạn {num_choice} câu hỏi (Trắc nghiệm hoặc Tự luận ngắn) để kiểm tra.
                                            
                                            -------- BÀI B: KIỂM TRA VIẾT (10 điểm) --------
                                            1. Chính tả: Cung cấp 1 đoạn văn/thơ để nghe-viết (khoảng 50-80 chữ).
                                            2. Tập làm văn: Soạn {num_essay} câu đề bài yêu cầu viết đoạn văn/bài văn theo chủ điểm.
                                            
                                            TUYỆT ĐỐI KHÔNG TRỘN LẪN CÂU HỎI. PHẢI TÁCH RÕ BÀI A VÀ BÀI B.
                                            """
                                        
                                        # [NÂNG CẤP] XỬ LÝ ĐẶC BIỆT CHO MÔN TIN HỌC (Theo CTGDPT 2018)
                                        elif (subject == "Tin học" or subject == "Tin học và Công nghệ") and curr_lvl == "tieu_hoc":
                                            special_prompt = f"""
                                            ⚠️ YÊU CẦU ĐẶC BIỆT CHO MÔN TIN HỌC (Theo CT GDPT 2018):
                                            - Bám sát Yêu cầu cần đạt của Lớp {grade}.
                                            - Cấu trúc đề phải bao gồm:
                                              + Phần 1: Trắc nghiệm ({num_choice} câu) - Kiểm tra kiến thức lý thuyết (Chủ đề A, B, C, D).
                                              + Phần 2: Thực hành/Tự luận ({num_essay} câu) - Kiểm tra kỹ năng ứng dụng (Chủ đề E, F - Soạn thảo, Trình chiếu, Lập trình trực quan).
                                            - Nội dung trọng tâm theo lớp:
                                              + Lớp 3: Các bộ phận máy tính, tư thế ngồi, bàn phím, chuột, thư mục cơ bản.
                                              + Lớp 4: Phần cứng/mềm, tìm kiếm Internet, soạn thảo văn bản, trình chiếu cơ bản.
                                              + Lớp 5: Sử dụng Internet an toàn, cây thư mục, định dạng văn bản nâng cao, lập trình trực quan (Scratch).
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
                                            
                                            # [FIX LỖI] Cấu hình tắt bộ lọc an toàn để AI không chặn đề thi
                                            safe_settings = [
                                                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                                            ]

                                            new_exams = []
                                            for i in range(num_exams):
                                                code = start_code + i
                                                prompt = SYSTEM_PROMPT.replace("[CODE]", str(code))
                                                req = f"DATA: {txt_mt} {txt_dt}\nNOTE: {user_req}\nSTRUCT: {num_choice} TN, {num_essay} TL, {num_practice} TH\nTASK: Exam {i+1} (Code {code})"
                                                
                                                # Thêm safety_settings vào đây
                                                res = model.generate_content(
                                                    req, 
                                                    generation_config={"response_mime_type": "application/json"},
                                                    safety_settings=safe_settings
                                                )
                                                
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
                                            
                                            st.success(f"✅ Tạo thành công! (Đã dùng: {usage_count + 1}/{limit_check})")
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
                st.markdown(curr.get('matrixHtml', '...'), unsafe_allow_html=True)
                if is_admin or user.get('role') == 'pro': st.download_button("⬇️ Tải Ma trận", create_word_doc(curr['matrixHtml'], "MaTran"), f"MaTran_{curr['id']}.doc")

            with st3:
                st.markdown(curr.get('specHtml', '...'), unsafe_allow_html=True)
                if is_admin or user.get('role') == 'pro': st.download_button("⬇️ Tải Đặc tả", create_word_doc(curr['specHtml'], "DacTa"), f"DacTa_{curr['id']}.doc")

    with tabs[2]:
        if st.session_state['dossier']:
            curr = st.session_state['dossier'][sel]
            if is_admin or user.get('role') == 'pro':
                st.markdown(f"""<div class="paper-view">{curr.get('answers','...')}</div>""", unsafe_allow_html=True)
                st.download_button("⬇️ Tải Đáp án (.doc)", create_word_doc(curr.get('answers',''), "DapAn"), f"DA_{curr['id']}.doc")
            else: st.info("🔒 Nâng cấp PRO để xem và tải Đáp án chi tiết.")
        else: st.info("Chưa có dữ liệu.")

    with tabs[3]:
        for doc in LEGAL_DOCUMENTS:
            cls = "highlight-card" if doc.get('highlight') else "legal-card"
            st.markdown(f"""<div class="{cls}" style="padding:15px; margin-bottom:10px; border-radius:10px;"><span style="background:#1e293b; color:white; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold">{doc['code']}</span><span style="font-weight:bold; color:#334155; margin-left:8px">{doc['title']}</span><p style="font-size:13px; color:#64748b; margin:5px 0 0 0">{doc['summary']}</p></div>""", unsafe_allow_html=True)
    
    # --- [BỔ SUNG] TAB 5: NÂNG CẤP VIP & THANH TOÁN (LOGIC MỚI) ---
    with tabs[4]:
        st.markdown("<h3 style='text-align: center; color: #1E3A8A;'>🚀 BẢNG GIÁ & NÂNG CẤP VIP</h3>", unsafe_allow_html=True)
        col_free, col_pro = st.columns(2)
        with col_free:
            st.markdown(f"""<div class="pricing-card"><h3>Gói FREE</h3><div class="price-tag">0đ</div><div class="feature-list">✅ Tạo thử <b>{MAX_FREE_USAGE} đề</b><br>❌ Tải file Word<br>❌ Xem đáp án chi tiết<br>❌ Hỗ trợ kỹ thuật</div></div>""", unsafe_allow_html=True)
        with col_pro:
            st.markdown(f"""<div class="pricing-card" style="border: 2px solid #2563EB;"><h3 style="color: #2563EB;">Gói PRO VIP</h3><div class="price-tag">{PRICE_VIP:,.0f}đ / gói</div><div class="feature-list">✅ <b>Tạo tối đa {MAX_PRO_USAGE} đề</b><br>✅ <b>Tải file Word chuẩn</b><br>✅ <b>Xem & Tải Đáp án/Ma trận</b><br>✅ Hỗ trợ ưu tiên 24/7</div></div>""", unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("📲 QUÉT MÃ QR ĐỂ THANH TOÁN TỰ ĐỘNG")
        
        c1, c2 = st.columns([1, 2])
        with c1:
            ref_code_input = st.text_input("Mã giới thiệu (Để tặng lượt khi mua Pro):")
            
        current_price = PRICE_VIP
        final_content_ck = f"NAP VIP {user.get('email')}"
        show_qr = True
        
        # [LOGIC MỚI] CHECK MÃ GIỚI THIỆU ĐỂ ẨN/HIỆN QR (KHÔNG GIẢM GIÁ)
        if ref_code_input:
            client = init_supabase()
            if client:
                check_ref = client.table('users_pro').select("*").eq('username', ref_code_input).execute()
                if check_ref.data and ref_code_input != user.get('email'):
                    st.success(f"✅ Mã hợp lệ! Bạn sẽ được tặng thêm {BONUS_PRO_REF} lượt khi kích hoạt Pro.")
                    final_content_ck = f"NAP VIP {user.get('email')} REF {ref_code_input}"
                    show_qr = True
                elif ref_code_input == user.get('email'):
                    st.warning("Bạn không thể tự giới thiệu chính mình.")
                    show_qr = True # Vẫn hiện QR gốc
                else:
                    st.error("❌ Mã giới thiệu không tồn tại! (Vui lòng nhập đúng hoặc xóa đi để thanh toán).")
                    show_qr = False # Ẩn QR

        if show_qr:
            qr_url = f"https://img.vietqr.io/image/{BANK_ID}-{BANK_ACC}-compact.png?amount={current_price}&addInfo={final_content_ck}&accountName={BANK_NAME}"
            c_qr1, c_qr2 = st.columns([1, 2])
            with c_qr1: st.image(qr_url, caption=f"Mã QR ({current_price:,.0f}đ)", width=300)
            with c_qr2: 
                st.info(f"**Nội dung chuyển khoản:** `{final_content_ck}`\n\n1. Quét mã QR.\n2. Bấm nút **'KÍCH HOẠT NGAY'** bên dưới sau khi chuyển khoản.")
                
                # [BỔ SUNG] NÚT KÍCH HOẠT TỰ ĐỘNG (CHECK SEPAY)
                if st.button("🚀 KÍCH HOẠT NGAY (Sau khi đã CK)", type="primary"):
                    if check_sepay_transaction(current_price, final_content_ck):
                        client = init_supabase()
                        if client:
                            # Lấy trạng thái hiện tại để kiểm tra có phải lần đầu không
                            curr_user_db = client.table('users_pro').select("*").eq('username', user.get('email')).execute()
                            is_first_time = False
                            if curr_user_db.data:
                                if curr_user_db.data[0]['role'] == 'free': is_first_time = True

                            # 1. Update người mua lên Pro (Reset lượt)
                            bonus_add = BONUS_PRO_REF if (ref_code_input and is_first_time) else 0
                            client.table('users_pro').update({
                                'role': 'pro',
                                'usage_count': 0,
                                'bonus_turns': bonus_add,
                                'referred_by': ref_code_input if ref_code_input else None
                            }).eq('username', user.get('email')).execute()
                            
                            # 2. Cộng hoa hồng (Chỉ khi lần đầu lên Pro)
                            if ref_code_input and is_first_time:
                                 ref_user = client.table('users_pro').select('commission_balance').eq('username', ref_code_input).execute()
                                 if ref_user.data:
                                     curr_comm = ref_user.data[0].get('commission_balance', 0)
                                     client.table('users_pro').update({
                                         'commission_balance': curr_comm + COMMISSION_AMT
                                     }).eq('username', ref_code_input).execute()

                            st.balloons()
                            st.success("🎉 CHÚC MỪNG! TÀI KHOẢN ĐÃ NÂNG CẤP LÊN PRO!")
                            time.sleep(2)
                            st.rerun()
                    else:
                        st.error("⚠️ Hệ thống chưa nhận được tiền. Vui lòng thử lại sau 30s.")

    # --- [BỔ SUNG] TAB 6: ĐỐI TÁC (AFFILIATE) ---
    with tabs[5]:
        st.subheader("💰 CHƯƠNG TRÌNH ĐỐI TÁC (AFFILIATE)")
        st.info(f"Mã giới thiệu của bạn chính là tên đăng nhập: **{user.get('email')}**")
        client = init_supabase()
        if client:
            try:
                # Thống kê số người đã giới thiệu
                ref_res = client.table('users_pro').select("*").eq('referred_by', user.get('email')).execute()
                
                # Lấy số dư hoa hồng
                me_res = client.table('users_pro').select('commission_balance').eq('username', user.get('email')).execute()
                comm_balance = me_res.data[0].get('commission_balance', 0) if me_res.data else 0

                if ref_res.data:
                    count_ref = len(ref_res.data)
                    count_pro = sum(1 for u in ref_res.data if u['role'] == 'pro')
                    c1, c2, c3 = st.columns(3)
                    with c1: st.metric("Tổng người giới thiệu", f"{count_ref} người")
                    with c2: st.metric("Đã lên PRO", f"{count_pro} người")
                    with c3: st.metric("Hoa hồng hiện có", f"{comm_balance:,.0f}đ")
                    st.write("---")
                    st.write("**Danh sách thành viên:**")
                    df_ref = pd.DataFrame(ref_res.data)
                    if not df_ref.empty:
                        st.dataframe(df_ref[['username', 'fullname', 'role', 'created_at']], use_container_width=True)
                else:
                    st.info("Bạn chưa giới thiệu được ai. Hãy chia sẻ Mã giới thiệu ngay!")
            except: st.error("Lỗi tải dữ liệu đối tác.")

    # --- TAB 7: HỒ SƠ ---
    with tabs[6]:
        c1, c2 = st.columns([2, 1])
        with c1: 
            st.write(f"**👤 Xin chào: {user.get('fullname')}**")
            st.write("---")
            st.subheader("🗂️ KHO ĐỀ CỦA BẠN (Đã lưu vĩnh viễn)")
            
            # [BỔ SUNG] Nút tải lại lịch sử từ Supabase
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
                        else: st.info("Bạn chưa lưu đề nào.")
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
            # [BỔ SUNG] Thêm ô nhập mã giới thiệu khi đăng ký
            ref_code = st.text_input("Mã người giới thiệu (Nếu có)", key="s_ref")
            
            if st.button("TẠO TÀI KHOẢN", use_container_width=True):
                client = init_supabase()
                if client and new_u and new_p:
                    try:
                        check = client.table('users_pro').select("*").eq('username', new_u).execute()
                        if check.data: st.warning("Tên này đã có người dùng!")
                        else:
                            # [BỔ SUNG] Đăng ký mới không tặng lượt, chỉ lưu mã giới thiệu
                            valid_ref = None
                            if ref_code:
                                check_ref = client.table('users_pro').select("*").eq('username', ref_code).execute()
                                if check_ref.data: valid_ref = ref_code
                                else: st.warning("Mã giới thiệu không tồn tại (Vẫn tạo tài khoản).")

                            client.table('users_pro').insert({
                                "username": new_u,
                                "password": new_p,
                                "fullname": new_name,
                                "role": "free",
                                "usage_count": 0,
                                "expiry_date": None,
                                "referred_by": valid_ref,
                                "bonus_turns": 0
                            }).execute()
                            st.success("Đăng ký thành công! Mời đăng nhập.")
                    except Exception as e: st.error(f"Lỗi đăng ký: {e}")

if 'user' not in st.session_state: login_screen()
else: main_app()

