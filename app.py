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
import urllib.parse # [BẮT BUỘC] Thư viện xử lý QR Code tránh lỗi

# [MỚI] TÍCH HỢP MODULE SOẠN BÀI HƯỚNG B (Yêu cầu 4 file đi kèm)
# Dùng try-except để không làm sập web nếu thầy chưa kịp tạo file lesson_ui.py
try:
    from lesson_ui import module_lesson_plan_B
except ImportError:
    module_lesson_plan_B = None

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG & KẾT NỐI
# ==============================================================================
# --- CẤU HÌNH GIỚI HẠN SỬ DỤNG ---
MAX_FREE_USAGE = 3
MAX_PRO_USAGE = 15

# --- CẤU HÌNH KHUYẾN MẠI & HOA HỒNG ---
BONUS_PER_REF = 0
BONUS_PRO_REF = 3
DISCOUNT_AMT = 0
COMMISSION_AMT = 10000

# --- CẤU HÌNH THANH TOÁN (SEPAY - VIETQR) ---
BANK_ID = "VietinBank"
BANK_ACC = "107878907329"
BANK_NAME = "TRAN THANH TUAN"
PRICE_VIP = 50000

# Lấy API Key từ Secrets
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
# [QUAN TRỌNG] DỮ LIỆU YCCĐ ĐƯỢC NHÚNG TRỰC TIẾP
# ==============================================================================
FULL_YCCD_DATA = [
  # --- LỚP 1 ---
  {"id": "L1-SO-01", "mon": "Toán", "lop": 1, "chu_de": "Số và Phép tính", "bai": "Các số đến 100", "yccd": "Đếm, đọc, viết được các số trong phạm vi 100. Nhận biết chục và đơn vị."},
  {"id": "L1-SO-02", "mon": "Toán", "lop": 1, "chu_de": "Số và Phép tính", "bai": "So sánh số", "yccd": "Nhận biết cách so sánh, xếp thứ tự các số trong phạm vi 100."},
  {"id": "L1-PT-01", "mon": "Toán", "lop": 1, "chu_de": "Số và Phép tính", "bai": "Phép cộng, phép trừ", "yccd": "Thực hiện được phép cộng, phép trừ (không nhớ) các số trong phạm vi 100."},
  {"id": "L1-HH-01", "mon": "Toán", "lop": 1, "chu_de": "Hình học", "bai": "Hình phẳng và hình khối", "yccd": "Nhận dạng hình vuông, tròn, tam giác, chữ nhật; khối lập phương, khối hộp chữ nhật."},
  {"id": "L1-DL-01", "mon": "Toán", "lop": 1, "chu_de": "Đo lường", "bai": "Độ dài và Thời gian", "yccd": "Đo độ dài bằng đơn vị cm. Đọc giờ đúng trên đồng hồ. Xem lịch hàng ngày."},
  
  # --- LỚP 2 ---
  {"id": "L2-SO-01", "mon": "Toán", "lop": 2, "chu_de": "Số và Phép tính", "bai": "Các số đến 1000", "yccd": "Đọc, viết, so sánh các số trong phạm vi 1000. Số tròn trăm, số liền trước, liền sau."},
  {"id": "L2-PT-01", "mon": "Toán", "lop": 2, "chu_de": "Số và Phép tính", "bai": "Phép cộng, phép trừ (có nhớ)", "yccd": "Thực hiện cộng, trừ (có nhớ) trong phạm vi 1000. Tính toán trường hợp có 2 dấu phép tính."},
  {"id": "L2-PT-02", "mon": "Toán", "lop": 2, "chu_de": "Số và Phép tính", "bai": "Phép nhân, phép chia", "yccd": "Vận dụng bảng nhân 2, 5 và bảng chia 2, 5. Hiểu ý nghĩa phép nhân, chia."},
  {"id": "L2-HH-01", "mon": "Toán", "lop": 2, "chu_de": "Hình học", "bai": "Hình phẳng và hình khối", "yccd": "Nhận biết đường thẳng, đường cong, 3 điểm thẳng hàng. Nhận dạng khối trụ, khối cầu."},
  {"id": "L2-DL-01", "mon": "Toán", "lop": 2, "chu_de": "Đo lường", "bai": "Đơn vị đo lường", "yccd": "Nhận biết kg, lít, m, km, dm. Xem đồng hồ (kim phút chỉ số 3, 6)."},

  # --- LỚP 3 ---
  {"id": "L3-SO-01", "mon": "Toán", "lop": 3, "chu_de": "Số và Phép tính", "bai": "Các số đến 100.000", "yccd": "Đọc, viết, so sánh số trong phạm vi 100.000. Làm tròn số đến hàng nghìn, chục nghìn."},
  {"id": "L3-PT-01", "mon": "Toán", "lop": 3, "chu_de": "Số và Phép tính", "bai": "Phép cộng, trừ", "yccd": "Cộng trừ các số có đến 5 chữ số (có nhớ không quá 2 lượt)."},
  {"id": "L3-PT-02", "mon": "Toán", "lop": 3, "chu_de": "Số và Phép tính", "bai": "Phép nhân, chia", "yccd": "Nhân chia số có nhiều chữ số với số có 1 chữ số. Tính giá trị biểu thức."},
  {"id": "L3-HH-01", "mon": "Toán", "lop": 3, "chu_de": "Hình học", "bai": "Góc và Hình phẳng", "yccd": "Nhận biết góc vuông, không vuông. Tính chu vi tam giác, tứ giác, hình chữ nhật, hình vuông."},
  {"id": "L3-DL-01", "mon": "Toán", "lop": 3, "chu_de": "Đo lường", "bai": "Diện tích", "yccd": "Làm quen diện tích. Đơn vị cm2. Tính diện tích hình chữ nhật, hình vuông."},

  # --- LỚP 4 ---
  {"id": "L4-SO-01", "mon": "Toán", "lop": 4, "chu_de": "Số tự nhiên", "bai": "Số lớp triệu", "yccd": "Đọc, viết, so sánh số đến lớp triệu. Nhận biết giá trị theo vị trí."},
  {"id": "L4-PT-01", "mon": "Toán", "lop": 4, "chu_de": "Số tự nhiên", "bai": "4 Phép tính", "yccd": "Nhân chia với số có 2 chữ số. Tính trung bình cộng."},
  {"id": "L4-PS-01", "mon": "Toán", "lop": 4, "chu_de": "Phân số", "bai": "Khái niệm Phân số", "yccd": "Đọc viết phân số. Rút gọn, quy đồng mẫu số. So sánh phân số."},
  {"id": "L4-PS-02", "mon": "Toán", "lop": 4, "chu_de": "Phân số", "bai": "Phép tính Phân số", "yccd": "Cộng, trừ, nhân, chia hai phân số. Giải toán tìm phân số của một số."},
  {"id": "L4-HH-01", "mon": "Toán", "lop": 4, "chu_de": "Hình học", "bai": "Góc và đường thẳng", "yccd": "Góc nhọn, tù, bẹt. Hai đường thẳng vuông góc, song song."},
  {"id": "L4-HH-02", "mon": "Toán", "lop": 4, "chu_de": "Hình học", "bai": "Hình bình hành, Hình thoi", "yccd": "Nhận biết và tính diện tích hình bình hành, hình thoi."},

  # --- LỚP 5 ---
  {"id": "L5-STP-01", "mon": "Toán", "lop": 5, "chu_de": "Số thập phân", "bai": "Khái niệm Số thập phân", "yccd": "Đọc, viết, so sánh số thập phân. Viết số đo đại lượng dưới dạng số thập phân."},
  {"id": "L5-STP-02", "mon": "Toán", "lop": 5, "chu_de": "Số thập phân", "bai": "Phép tính Số thập phân", "yccd": "Cộng, trừ, nhân, chia số thập phân. Giải toán liên quan tỉ số phần trăm."},
  {"id": "L5-HH-01", "mon": "Toán", "lop": 5, "chu_de": "Hình học", "bai": "Tam giác, Hình thang, Hình tròn", "yccd": "Tính diện tích hình tam giác, hình thang. Chu vi và diện tích hình tròn."},
  {"id": "L5-HH-02", "mon": "Toán", "lop": 5, "chu_de": "Hình học", "bai": "Hình hộp", "yccd": "Tính diện tích xung quanh, toàn phần, thể tích hình hộp chữ nhật, hình lập phương."},
  {"id": "L5-DL-01", "mon": "Toán", "lop": 5, "chu_de": "Đo lường", "bai": "Toán chuyển động", "yccd": "Giải bài toán về vận tốc, quãng đường, thời gian (chuyển động đều)."}
]

# ==============================================================================
# 2. KHO DỮ LIỆU TRI THỨC (GIỮ NGUYÊN)
# ==============================================================================
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
       - THPT từ 2025: Cấu trúc 3 phần (TN Nhiều lựa chọn, TN Đúng/Sai, Trả lời ngắn)."""
}

PRACTICAL_SUBJECTS = ["Tin học", "Công nghệ", "Mĩ thuật", "Âm nhạc", "Khoa học", "Khoa học tự nhiên", "Vật lí", "Hóa học", "Sinh học", "Tin học và Công nghệ"]

SUBJECT_STRUCTURE_DATA = {
    "THPT_2025": "Phần I: TN Nhiều lựa chọn (0.25đ) | Phần II: TN Đúng/Sai (Max 1đ) | Phần III: Trả lời ngắn (0.5đ)",
    "TieuHoc_TV": "A. Kiểm tra Đọc (10đ) [Đọc tiếng + Đọc hiểu văn bản mới] + B. Kiểm tra Viết (10đ) [Chính tả + TLV].",
    "TieuHoc_Chung": "Trắc nghiệm (60-70%) + Tự luận (30-40%). Mức độ: M1-M2-M3",
    "Toán": "Trắc nghiệm (70%) + Vận dụng (30%)",
    "Ngữ văn": "Đọc hiểu (6.0đ) + Viết (4.0đ)",
    "Tiếng Anh": "Listening (2.5) - Language (2.5) - Reading (2.5) - Writing (2.5)",
    "Mặc định": "NB (40%) - TH (30%) - VD (20%) - VDC (10%)"
}

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

BOOKS_LIST = [
    "Kết nối tri thức với cuộc sống", "Chân trời sáng tạo", "Cánh Diều", "Cùng khám phá",
    "Vì sự bình đẳng và dân chủ trong giáo dục", "Tin học: Đại học Vinh (Tiểu học)",
    "Tiếng Anh: Global Success", "Tiếng Anh: Family and Friends", "Tiếng Anh: Friends Plus",
    "Tiếng Anh: i-Learn Smart Start", "Tiếng Anh: Explore English",
    "Tin học: Kết nối tri thức", "Tin học: Chân trời sáng tạo", "Tin học: Cánh Diều",
    "Tài liệu Giáo dục địa phương tỉnh Tuyên Quang", "Chuyên đề học tập (THPT)"
]

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

CURRICULUM_DATA = {
    "Toán": {
        "Lớp 6": {"Kiểm tra giữa kì 1": "Tập hợp số tự nhiên; Phép tính; Số nguyên tố."},
        "Lớp 12": {"Kiểm tra cuối kì 1": "Nguyên hàm; Tích phân; Phương trình mặt phẳng."}
    }
}

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
# 3. GIAO DIỆN & CSS
# ==============================================================================
st.markdown("""
<style>
    /* ===== Dashboard KPI ===== */
.kpi-card{
  background:#FFFFFF;
  border:1px solid #E2E8F0;
  border-radius:12px;
  padding:16px 18px;
  box-shadow:0 4px 8px rgba(0,0,0,0.04);
  margin-bottom:12px;
}
.kpi-title{ font-size:12px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.5px;}
.kpi-value{ font-size:22px; font-weight:900; color:#0F172A; margin-top:6px;}
.kpi-sub{ font-size:12px; color:#64748B; margin-top:4px;}

/* ===== Module Cards ===== */
.module-card{
  background:#FFFFFF;
  border:1px solid #E2E8F0;
  border-radius:14px;
  padding:18px 18px 14px 18px;
  box-shadow:0 10px 18px rgba(2,6,23,0.05);
  margin-bottom:12px;
}
.module-card.highlight{
  border:1px solid #BFDBFE;
  box-shadow:0 14px 24px rgba(37,99,235,0.12);
}
.module-badge{
  display:inline-block;
  font-size:11px;
  font-weight:800;
  padding:4px 10px;
  border-radius:999px;
  background:#EFF6FF;
  border:1px solid #BFDBFE;
  color:#1D4ED8;
  margin-bottom:10px;
}
.module-title{
  font-size:18px;
  font-weight:900;
  color:#0F172A;
  margin:4px 0 6px 0;
}
.module-desc{
  font-size:13px;
  color:#334155;
  line-height:1.55;
  margin-bottom:8px;
}
.module-meta{
  font-size:12px;
  color:#64748B;
  border-top:1px dashed #E2E8F0;
  padding-top:10px;
}
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

# [FIX] HÀM LÀM SẠCH JSON CHUẨN (KHÔNG ĐƯỢC XÓA)
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
    <body>
        <div class="WordSection1">
            {html}
        </div>
    </body>
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
# [MỚI - ĐÃ SỬA LỖI JSON] MODULE QUẢN LÝ YÊU CẦU CẦN ĐẠT (KHÔNG CẦN FILE JSON)
# ==============================================================================
class YCCDManager:
    def __init__(self):
        # Đọc trực tiếp từ biến trong code, không đọc file nữa
        self.data = FULL_YCCD_DATA 

    def get_grades(self):
        grades = set([item['lop'] for item in self.data])
        return sorted(list(grades))

    def get_topics_by_grade(self, grade):
        topics = set([item['chu_de'] for item in self.data if item['lop'] == grade])
        return sorted(list(topics))

    def get_yccd_list(self, grade, topic):
        return [item for item in self.data if item['lop'] == grade and item['chu_de'] == topic]

class QuestionGeneratorYCCD:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # [SỬA LỖI 404] Dùng gemini-3-pro-preview theo yêu cầu
        self.model = genai.GenerativeModel('gemini-3-pro-preview')

    def generate(self, yccd_item, muc_do="Thông hiểu"):
        prompt = f"""
        VAI TRÒ: Giáo viên Toán Tiểu học (Chương trình GDPT 2018).
        NHIỆM VỤ: Soạn 01 câu hỏi trắc nghiệm Toán.
        THÔNG TIN BẮT BUỘC:
        - Lớp: {yccd_item['lop']} (Câu hỏi phải phù hợp tâm lý lứa tuổi lớp {yccd_item['lop']})
        - Chủ đề: {yccd_item['chu_de']}
        - Bài học: {yccd_item['bai']}
        - YÊU CẦU CẦN ĐẠT: "{yccd_item['yccd']}"
        - Mức độ: {muc_do}
        
        YÊU CẦU ĐẦU RA (JSON format):
        {{
            "question": "Nội dung câu hỏi (ngắn gọn, dễ hiểu)",
            "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
            "answer": "A, B, C hoặc D",
            "explanation": "Giải thích chi tiết (Dành cho học sinh tự học)"
        }}
        """
        try:
            # [FIX LỖI] Tắt bộ lọc an toàn để tránh AI chặn nội dung đề thi
            safe_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            res = self.model.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"},
                safety_settings=safe_settings
            )
            # Dùng clean_json để tránh lỗi định dạng
            return json.loads(clean_json(res.text))
        except Exception as e:
            return None

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

    # --- CẬP NHẬT TAB MỚI: THÊM '🎯 ĐỀ CHUẨN YCCĐ' (TAB SỐ 8) ---
    tabs = st.tabs(["🚀 THIẾT LẬP", "📄 XEM ĐỀ", "✅ ĐÁP ÁN", "⚖️ PHÁP LÝ", "💎 NÂNG CẤP VIP", "💰 ĐỐI TÁC", "📂 HỒ SƠ", "🎯 ĐỀ CHUẨN YCCĐ"])

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
                                # 3. NẾU ĐƯỢC PHÉP -> CHẠY AI
                                api_key = st.session_state.get('api_key', '')
                                
                                # [QUAN TRỌNG] Tự động lấy Key của Admin nếu user không nhập
                                if not api_key: api_key = SYSTEM_GOOGLE_KEY 
                                
                                if not api_key: st.toast("⚠️ Vui lòng nhập API Key ở Tab Hồ Sơ!", icon="❌")
                                else:
                                    with st.spinner(f"🔮 AI đang soạn đề... (Lần thứ: {usage_count + 1})"):
                                        txt_mt = read_file_content(mt_file, 'matrix')
                                        txt_dt = read_file_content(dt_file, 'spec')
                                        knowledge_context = get_knowledge_context(subject, grade, book, scope)
                                        
                                        # [NÂNG CẤP] SYSTEM PROMPT THEO ĐÚNG INSTRUCTION GỐC
                                        special_prompt = ""
                                        
                                        # 1. NẾU LÀ CẤP TIỂU HỌC (Áp dụng "Luật thép" thầy vừa đưa)
                                        if curr_lvl == "tieu_hoc":
                                            special_prompt = f"""
                                            🔥 VAI TRÒ TUYỆT ĐỐI: CHUYÊN GIA KHẢO THÍ GIÁO DỤC TIỂU HỌC.
                                            
                                            I. TUÂN THỦ PHÁP LÝ (BẮT BUỘC):
                                            - Thông tư 27/2020/TT-BGDĐT
                                            - Công văn 7791/BGDĐT-GDTH
                                            - Chương trình GDPT 2018
                                            
                                            II. QUY ĐỊNH CẤM KỴ (VI PHẠM LÀ HỦY KẾT QUẢ):
                                            1. CẤM dùng mức độ "Vận dụng cao".
                                            2. CẤM dùng các thuật ngữ cấp 2,3: Phân tích, Đánh giá, Sáng tạo.
                                            3. CHỈ SỬ DỤNG 3 MỨC: Nhận biết - Thông hiểu - Vận dụng.
                                            
                                            III. PHÂN BỐ ĐIỂM VÀ CÂU HỎI (TỔNG 10đ):
                                            - Nhận biết: 40-50%
                                            - Thông hiểu: 30-40%
                                            - Vận dụng: 20-30%
                                            - KHÔNG dồn điểm vào câu khó, KHÔNG đánh đố học sinh.
                                            
                                            IV. QUY ĐỊNH MA TRẬN & ĐẶC TẢ:
                                            - Ma trận phải có đúng 5 cột: Chủ đề, NB, TH, VD, Tổng.
                                            - Bản đặc tả phải khớp 100% với ma trận và đề thi.
                                            - Yêu cầu cần đạt phải rõ ràng, bám sát CT 2018.
                                            """
                                            
                                            # Logic riêng từng môn Tiểu học
                                            if subject == "Toán":
                                                special_prompt += """
                                                V. MÔN TOÁN: 
                                                - Nội dung: Số và phép tính, Đại lượng, Hình học, Giải toán có lời văn.
                                                - KHÔNG dùng toán mẹo, toán Olympic, Violympic. Vận dụng gắn với đời sống.
                                                """
                                            elif subject == "Tiếng Việt":
                                                special_prompt += f"""
                                                V. MÔN TIẾNG VIỆT (Tách 2 phần):
                                                A. KIỂM TRA ĐỌC (10đ):
                                                    1. Đọc thành tiếng.
                                                    2. Đọc hiểu: Sử dụng văn bản MỚI (ngoài SGK) phù hợp lứa tuổi + {num_choice} câu hỏi (M1-M2-M3).
                                                B. KIỂM TRA VIẾT (10đ):
                                                    1. Chính tả (Nghe-viết đoạn ngắn).
                                                    2. Tập làm văn: {num_essay} câu (Viết đoạn/bài văn theo chủ điểm đã học).
                                                """
                                            elif "Tin học" in subject:
                                                special_prompt += f"""
                                                V. MÔN TIN HỌC:
                                                - Nội dung: Máy tính, Dữ liệu, An toàn thông tin, Phần mềm học tập.
                                                - Trắc nghiệm ({num_choice} câu) + Thực hành ({num_essay} câu).
                                                - KHÔNG lập trình phức tạp.
                                                """
                                            else:
                                                special_prompt += """
                                                V. CÁC MÔN KHÁC (Khoa học, LS&ĐL, Đạo đức...): Gắn với đời sống, không dùng thuật ngữ hàn lâm.
                                                """

                                        # 2. NẾU LÀ CẤP 2, 3 (Giữ nguyên logic cũ)
                                        else:
                                            special_prompt = """
                                            YÊU CẦU TRUNG HỌC (Theo Thông tư 22 & CV 7791):
                                            - Ma trận 4 mức độ: Nhận biết (40%) - Thông hiểu (30%) - Vận dụng (20%) - Vận dụng cao (10%).
                                            """
                                            if curr_lvl == "thpt":
                                                special_prompt += """
                                                - Cấu trúc THPT 2025: Phần I (TN nhiều lựa chọn), Phần II (Đúng/Sai), Phần III (Trả lời ngắn).
                                                """

                                        SYSTEM_PROMPT = f"""
                                        {APP_CONFIG['context']}
                                        
                                        I. THÔNG TIN ĐẦU VÀO:
                                        - Năm học: {school_year} | Cấp: {level_key} | Môn: {subject} | Lớp: {grade} 
                                        - Bộ sách: "{book}" | Phạm vi: {scope}
                                        - {knowledge_context}
                                        
                                        II. HƯỚNG DẪN CHUYÊN GIA (TUÂN THỦ TUYỆT ĐỐI):
                                        {special_prompt}
                                        
                                        III. CƠ CHẾ TỰ KIỂM TRA & TỪ CHỐI (SELF-REFLECTION):
                                        - Trước khi xuất kết quả, hãy tự kiểm tra: Tổng điểm có đúng 10 không? Có xuất hiện mức độ sai quy định không?
                                        - Nếu người dùng yêu cầu ra đề vượt chuẩn (Ví dụ: Lớp 3 mà đòi Vận dụng cao) -> HÃY TỪ CHỐI LỊCH SỰ và đề xuất phương án đúng luật.
                                        
                                        IV. ĐỊNH DẠNG OUTPUT (JSON RAW):
                                        {{
                                            "title": "Tên đề thi",
                                            "content": "Nội dung đề thi HTML (Trình bày đẹp, chuẩn font)",
                                            "matrixHtml": "Bảng ma trận HTML (Phải khớp 100% với đề)",
                                            "specHtml": "Bảng đặc tả HTML",
                                            "answers": "Đáp án & Hướng dẫn chấm HTML"
                                        }}
                                        V. QUAN TRỌNG: CHỈ TRẢ VỀ JSON. KHÔNG GIẢI THÍCH GÌ THÊM.
                                        """

                                        try:
                                            genai.configure(api_key=api_key)
                                            # [SỬA LỖI 404] Dùng gemini-3-pro-preview
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

    # --- TAB 2: XEM & XUẤT (CLASS paper-view ĐÃ CHUẨN HÓA FONT) ---
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
    
    # --- [NÂNG CẤP] TAB 5: NÂNG CẤP VIP & THANH TOÁN (LOGIC SEVQR) ---
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
        # [QUAN TRỌNG] THÊM TIỀN TỐ "SEVQR" VÀO NỘI DUNG ĐỂ SEPAY NHẬN DIỆN
        final_content_ck = f"SEVQR NAP VIP {user.get('email')}"
        show_qr = True
        
        # [LOGIC MỚI] CHECK MÃ GIỚI THIỆU ĐỂ ẨN/HIỆN QR (KHÔNG GIẢM GIÁ)
        if ref_code_input:
            client = init_supabase()
            if client:
                check_ref = client.table('users_pro').select("*").eq('username', ref_code_input).execute()
                if check_ref.data and ref_code_input != user.get('email'):
                    st.success(f"✅ Mã hợp lệ! Bạn sẽ được tặng thêm {BONUS_PRO_REF} lượt khi kích hoạt Pro.")
                    final_content_ck = f"SEVQR NAP VIP {user.get('email')} REF {ref_code_input}"
                    show_qr = True
                elif ref_code_input == user.get('email'):
                    st.warning("Bạn không thể tự giới thiệu chính mình.")
                    show_qr = True # Vẫn hiện QR gốc
                else:
                    st.error("❌ Mã giới thiệu không tồn tại! (Vui lòng nhập đúng hoặc xóa đi để thanh toán).")
                    show_qr = False # Ẩn QR

        if show_qr:
            # [FIX LỖI] URL ENCODE CHO NỘI DUNG CHUYỂN KHOẢN ĐỂ TRÁNH LỖI MEDIA STORAGE
            import urllib.parse
            encoded_content = urllib.parse.quote(final_content_ck)
            qr_url = f"https://img.vietqr.io/image/{BANK_ID}-{BANK_ACC}-compact.png?amount={current_price}&addInfo={encoded_content}&accountName={BANK_NAME}"
            
            c_qr1, c_qr2 = st.columns([1, 2])
            with c_qr1: 
                # [FIX LỖI] TRY-EXCEPT ĐỂ TRÁNH SẬP APP NẾU LỖI ẢNH
                try:
                    st.image(qr_url, caption=f"Mã QR ({current_price:,.0f}đ)", width=300)
                except:
                    st.error("Không tải được QR. Vui lòng chuyển khoản thủ công.")
            
            with c_qr2: 
                st.info(f"**Nội dung chuyển khoản:** `{final_content_ck}`\n\n1. Quét mã QR.\n2. Bấm nút **'KÍCH HOẠT NGAY'** bên dưới sau khi chuyển khoản.")
                
                # [NÂNG CẤP] NÚT KÍCH HOẠT TỰ ĐỘNG (CHECK SEPAY)
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

    # --- [NÂNG CẤP] TAB 6: ĐỐI TÁC (AFFILIATE) ---
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
                else: st.info("Bạn chưa giới thiệu được ai. Hãy chia sẻ Mã giới thiệu ngay!")
            except: st.error("Lỗi tải dữ liệu đối tác.")

    # --- TAB 7: HỒ SƠ & LỊCH SỬ ---
    with tabs[6]:
        c1, c2 = st.columns([2, 1])
        with c1: 
            st.write(f"**👤 Xin chào: {user.get('fullname')}**")
            st.write("---")
            st.subheader("🗂️ KHO ĐỀ CỦA BẠN (Đã lưu vĩnh viễn)")
            
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

    # ==============================================================================
    # [MỚI - ĐÃ SỬA] TAB 8: TẠO ĐỀ CHUẨN YCCĐ (DÙNG DỮ LIỆU NHÚNG)
    # ==============================================================================
    with tabs[7]:
        st.title("🎯 Ngân hàng đề Toán Tiểu học (Chuẩn GDPT 2018)")
        st.caption("Dữ liệu bám sát Yêu cầu cần đạt - Đã tích hợp sẵn.")
        
        mgr = YCCDManager()
        current_api_key = st.session_state.get('api_key', '')
        if not current_api_key: current_api_key = SYSTEM_GOOGLE_KEY
        gen = QuestionGeneratorYCCD(current_api_key)

        with st.container():
            col1, col2, col3 = st.columns(3)
            with col1:
                # 1. Chọn Lớp (Tự động lấy từ file json)
                grades = mgr.get_grades()
                selected_grade = st.selectbox("1️⃣ Chọn Khối Lớp:", grades, index=len(grades)-1) # Mặc định chọn lớp 5

            with col2:
                # 2. Chọn Chủ đề tương ứng với Lớp
                topics = mgr.get_topics_by_grade(selected_grade)
                selected_topic = st.selectbox("2️⃣ Mạch kiến thức:", topics)

            with col3:
                # 3. Cấu hình số lượng
                num_q = st.number_input("Số câu hỏi:", 1, 20, 5, key="num_q_yccd")

        # 4. Chọn Yêu cầu cần đạt chi tiết
        if selected_topic:
            yccd_list = mgr.get_yccd_list(selected_grade, selected_topic)
            yccd_map = {f"{item['bai']}": item for item in yccd_list}
            
            selected_bai = st.selectbox("3️⃣ Chọn Bài học / Yêu cầu cụ thể:", list(yccd_map.keys()))
            target_item = yccd_map[selected_bai]
            
            st.info(f"📌 **Chuẩn kiến thức:** {target_item['yccd']}")
            
            muc_do = st.select_slider("Độ khó:", options=["Nhận biết", "Thông hiểu", "Vận dụng"])

            # --- NÚT TẠO ĐỀ ---
            if st.button("🚀 BẮT ĐẦU SOẠN ĐỀ", type="primary", key="btn_yccd"):
                if not current_api_key:
                    st.error("Chưa có API Key.")
                else:
                    st.divider()
                    my_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i in range(num_q):
                        status_text.markdown(f"**⏳ AI đang tư duy câu {i+1}/{num_q}...**")
                        data = gen.generate(target_item, muc_do)
                        my_bar.progress((i + 1) / num_q)
                        
                        if data:
                            with st.expander(f"✅ Câu {i+1}: {data.get('question', '...')}", expanded=True):
                                st.write(f"**Đề bài:** {data.get('question','')}")
                                if 'options' in data:
                                    cols = st.columns(4)
                                    for idx, opt in enumerate(data['options'][:4]):
                                        cols[idx].write(opt)
                                
                                st.success(f"**Đáp án:** {data.get('answer','')}")
                                st.warning(f"💡 **HD:** {data.get('explanation','')}")
                        else:
                            st.error(f"Câu {i+1}: AI gặp lỗi, đang thử lại...")
                    
                    status_text.success("🎉 Hoàn thành!")
                    my_bar.empty()
    
    st.markdown("---")
    st.markdown("""<div style="text-align: center; color: #64748b; font-size: 14px; padding: 20px;"><strong>AI EXAM EXPERT v10</strong> © Tác giả: <strong>Trần Thanh Tuấn</strong> – Trường Tiểu học Hồng Thái – Năm 2026.<br>SĐT: 0918198687</div>""", unsafe_allow_html=True)            

# ==============================================================================
# 7A. MODULE: TRỢ LÝ SOẠN GIÁO ÁN (TỔNG QUÁT TẤT CẢ MÔN/CẤP/BỘ SÁCH)
# ==============================================================================

def _lp_safe_key(prefix: str) -> str:
    """Sinh prefix key theo session để tránh trùng key giữa các module."""
    uid = st.session_state.get("user", {}).get("email", "guest")
    return f"{prefix}__{uid}"

def _lp_get_api_key():
    # Ưu tiên key người dùng nhập, fallback key hệ thống
    k = st.session_state.get("api_key", "")
    if not k:
        k = SYSTEM_GOOGLE_KEY
    return k

def _lp_build_lesson_system_prompt(level_key: str, subject: str, grade: str, book: str, scope: str, school_year: str):
    """
    SYSTEM PROMPT "cứng" để giáo án luôn đúng cấu trúc, đúng chuẩn.
    """
    # Khung giáo án chuẩn tiểu học/trung học (tối giản nhưng đủ hồ sơ)
    base_constraints = f"""
VAI TRÒ: Trợ lý soạn GIÁO ÁN (Kế hoạch bài dạy) theo CT GDPT 2018.
NGUYÊN TẮC BẮT BUỘC:
- Viết đúng chuẩn văn phong hồ sơ giáo viên Việt Nam.
- Nội dung phù hợp cấp học, đúng tâm lý lứa tuổi.
- Không bịa "văn bản pháp lý" mới. Chỉ viện dẫn chung: CT GDPT 2018; TT 27/2020 (Tiểu học); TT 22/2021 (THCS/THPT) nếu cần.
- Giáo án phải có đủ các mục: 
  (1) Thông tin bài dạy
  (2) Mục tiêu (phẩm chất, năng lực, yêu cầu cần đạt/chuẩn đầu ra)
  (3) Chuẩn bị (GV/HS)
  (4) Tiến trình dạy học theo hoạt động (Khởi động – Hình thành – Luyện tập – Vận dụng)
  (5) Đánh giá (trong giờ + sau giờ)
- Nếu người dùng không cung cấp tên bài cụ thể, phải soạn theo CHỦ ĐỀ/PHẠM VI (scope) và nêu rõ "Bài/Chủ đề: theo phân phối chương trình".
- Luôn tạo hoạt động học tập rõ: mục tiêu hoạt động, cách tiến hành, sản phẩm/tiêu chí.
- Ưu tiên phương pháp: dạy học tích cực, hợp tác nhóm, trò chơi học tập, hỏi đáp gợi mở, phân hóa.
- Định dạng output: HTML (Times New Roman), có tiêu đề, mục rõ ràng.
"""

    # Ràng buộc riêng theo cấp
    if level_key == "Tiểu học":
        level_constraints = """
RÀNG BUỘC TIỂU HỌC:
- Bám Thông tư 27/2020: nhận xét, động viên; đánh giá thường xuyên; không nặng kiến thức hàn lâm.
- Hoạt động ngắn, rõ, có hỗ trợ học sinh yếu và mở rộng cho học sinh khá giỏi.
"""
    else:
        level_constraints = """
RÀNG BUỘC TRUNG HỌC:
- Bám định hướng phát triển phẩm chất, năng lực; có kiểm tra đánh giá quá trình.
- Hoạt động có sản phẩm học tập; có tiêu chí đánh giá.
"""

    # Ràng buộc riêng theo môn (có thể mở rộng)
    subject_constraints = ""
    if subject == "Tiếng Việt":
        subject_constraints = """
RÀNG BUỘC MÔN TIẾNG VIỆT:
- Nếu là Tiểu học: cấu trúc hoạt động ưu tiên ĐỌC/VIẾT/NGHE-NÓI theo tiết học.
- Có luyện đọc (đọc đúng, đọc trôi chảy/diễn cảm tùy lớp), đọc hiểu (câu hỏi gợi mở), luyện từ/câu (nếu phù hợp), viết/chính tả (nếu phù hợp).
- Tuyệt đối tránh thuật ngữ học thuật cao.
"""
    elif subject == "Toán":
        subject_constraints = """
RÀNG BUỘC MÔN TOÁN:
- Hoạt động có ví dụ minh họa, bài tập luyện tập, vận dụng gắn thực tế.
- Có phân hóa: cơ bản – nâng cao nhẹ.
"""
    elif "Tin học" in subject:
        subject_constraints = """
RÀNG BUỘC MÔN TIN HỌC:
- Có mục tiêu năng lực số phù hợp.
- Nếu có thực hành: nêu rõ thiết bị, phần mềm, quy trình thao tác, tiêu chí đánh giá sản phẩm.
- An toàn thông tin nếu phù hợp chủ đề.
"""
    else:
        subject_constraints = """
RÀNG BUỘC CHUNG:
- Hoạt động rõ ràng, có sản phẩm, có đánh giá.
"""

    # Nội dung nền chương trình (tận dụng mapping hiện có)
    knowledge_context = get_knowledge_context(subject, grade, book, scope)

    sys_prompt = f"""
{base_constraints}
{level_constraints}
{subject_constraints}

THÔNG TIN ĐẦU VÀO:
- Năm học: {school_year}
- Cấp học: {level_key}
- Môn: {subject}
- Lớp: {grade}
- Bộ sách: {book}
- Phạm vi/Thời điểm: {scope}
- Gợi ý nội dung: {knowledge_context}

ĐỊNH DẠNG OUTPUT (JSON RAW - CHỈ TRẢ JSON):
{{
  "title": "Tên giáo án",
  "planHtml": "Nội dung giáo án dạng HTML chuẩn Times New Roman (in ấn được)",
  "checklist": ["Danh sách tự kiểm (đủ mục/đúng cấu trúc/không sai cấp học)"],
  "notes": "Gợi ý điều chỉnh nhanh cho GV (ngắn gọn)"
}}

QUAN TRỌNG:
- planHtml phải đầy đủ các mục 1→5 như yêu cầu.
- Không trả lời ngoài JSON.
"""
    return sys_prompt.strip()

def _lp_generate_lesson_plan(api_key: str, system_prompt: str, user_note: str, lesson_name: str, duration_min: int, class_size: int):
    """
    Gọi Gemini để sinh giáo án (JSON).
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        'gemini-3-pro-preview',
        system_instruction=system_prompt
    )

    safe_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    req = f"""
YÊU CẦU SOẠN GIÁO ÁN:
- Tên bài/chủ đề GV nhập: {lesson_name if lesson_name else "(Không cung cấp tên bài cụ thể)"}
- Thời lượng: {duration_min} phút
- Sĩ số lớp: {class_size} học sinh
- Ghi chú GV: {user_note}

HÃY TRẢ VỀ JSON THEO ĐÚNG SCHEMA.
"""

    res = model.generate_content(
        req,
        generation_config={"response_mime_type": "application/json"},
        safety_settings=safe_settings
    )
    data = json.loads(clean_json(res.text))
    return data

# ==============================================================================
# MODULE: TRỢ LÝ SOẠN BÀI – TẠO GIÁO ÁN TỰ ĐỘNG (UI PRO + ANTI DUP KEY)
# ==============================================================================

def _lp_uid():
    return st.session_state.get("user", {}).get("email", "guest")

def _lp_key(name: str) -> str:
    # key duy nhất theo user + module để chống DuplicateElementKey
    return f"lp_{name}_{_lp_uid()}"

def _lp_api_key():
    return st.session_state.get("api_key") or SYSTEM_GOOGLE_KEY

def _lp_init_state():
    if _lp_key("history") not in st.session_state:
        st.session_state[_lp_key("history")] = []   # lưu nhiều giáo án
    if _lp_key("last_html") not in st.session_state:
        st.session_state[_lp_key("last_html")] = ""
    if _lp_key("last_title") not in st.session_state:
        st.session_state[_lp_key("last_title")] = "GiaoAn"

# [FIX] Thêm 2 hàm này vào để xử lý lỗi NameError
def _lp_get_active(default_page):
    return st.session_state.get("lp_active_page_admin_state", default_page)

def _lp_set_active(page: str):
    st.session_state["lp_active_page_admin_state"] = page

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

        # =========================
        # CHỌN BỘ SÁCH (KHÔNG CÓ SCOPE)
        # =========================
        r2c1 = st.columns([1])[0]
        with r2c1:
            book = st.selectbox(
                "Bộ sách",
                BOOKS_LIST,
                key=_lp_key("book")
            )

        # =========================
        # PPCT (Bước A - nhanh): Chọn tuần/tiết bằng số
        # =========================
        r2c3, r2c4 = st.columns([1, 1])
        with r2c3:
            ppct_week = st.number_input(
                "Tuần (PPCT)",
                min_value=1, max_value=40,
                value=1, step=1,
                key=_lp_key("ppct_week")
            )
        with r2c4:
            ppct_period = st.number_input(
                "Tiết (PPCT)",
                min_value=1, max_value=10,
                value=1, step=1,
                key=_lp_key("ppct_period")
            )
        
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
    ppct_text = f"PPCT: Tuần {ppct_week_val}, Tiết {ppct_period_val}"
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
        st.text_input(
            "Tên bài/Chủ đề",
            key=_lp_key("lesson_title"),
            placeholder="Ví dụ: Các số đến 10 / Luyện từ và câu / Bài 5 ..."
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
            st.markdown(f"<div class='paper-view'>{last_html}</div>", unsafe_allow_html=True)

            cdl1, cdl2 = st.columns([1, 1])
            with cdl1:
                st.download_button(
                    "⬇️ Tải Word giáo án",
                    create_word_doc(last_html, st.session_state.get(_lp_key("last_title"), "GiaoAn")),
                    file_name="GiaoAn.doc",
                    mime="application/msword",
                    type="primary",
                    key=_lp_key("dl_word")
                )
            with cdl2:
                if st.button("📌 Lưu vào danh sách", key=_lp_key("btn_save")):
                    st.session_state[_lp_key("history")].insert(0, {
                        "title": st.session_state.get(_lp_key("last_title"), "GiaoAn"),
                        "html": last_html
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
    # XỬ LÝ NÚT BẤM
    # ===============================
    if generate_btn or regen_btn:
        api_key = _lp_api_key()
        if not api_key:
            st.error("❌ Chưa có API Key.")
            st.stop()

        # Lấy dữ liệu người dùng đã nhập (các tab)
        lesson_title = st.session_state.get(_lp_key("lesson_title"), "").strip()
        objectives = st.session_state.get(_lp_key("objectives"), "").strip()
        yccd = st.session_state.get(_lp_key("yccd"), "").strip()

        # PPCT
        ppct_week_val = st.session_state.get(_lp_key("ppct_week"), 1)
        ppct_period_val = st.session_state.get(_lp_key("ppct_period"), 1)
        ppct_text = f"PPCT: Tuần {ppct_week_val}, Tiết {ppct_period_val}"

        # Gom ghi chú GV để AI bám sát (từ các ô đã có)
        teacher_note = f"""
{ppct_text}
Mẫu: {template} | Mức chi tiết: {detail_level}
Ưu tiên phương pháp: {", ".join(method_focus) if method_focus else "Chuẩn"}

Mục tiêu GV nhập:
{objectives if objectives else "(trống)"}

YCCĐ GV nhập:
{yccd if yccd else "(trống)"}

Gợi ý hoạt động GV:
- Khởi động: {st.session_state.get(_lp_key("a1"), "")}
- Hình thành: {st.session_state.get(_lp_key("a2"), "")}
- Luyện tập: {st.session_state.get(_lp_key("a3"), "")}
- Vận dụng: {st.session_state.get(_lp_key("a4"), "")}

Phân hoá: {st.session_state.get(_lp_key("diff"), "")}
Hỗ trợ đặc thù: {st.session_state.get(_lp_key("support"), "")}

Đánh giá trong giờ: {st.session_state.get(_lp_key("assess"), "")}
Rubric: {st.session_state.get(_lp_key("rubric"), "")}

Đồ dùng: {st.session_state.get(_lp_key("materials"), "")}
Học liệu số/CNTT: {st.session_state.get(_lp_key("digital"), "")}
"""

        # 1) Tạo system_prompt CHUẨN MẪU (khóa cấu trúc)
        system_prompt = _lp_build_lesson_system_prompt(
            level_key=level_key,
            subject=subject,
            grade=grade,
            book=book,
            scope=scope,
            school_year=school_year
        )

        # 2) Gọi AI theo chuẩn JSON
        try:
            with st.spinner("🔄 Đang tạo giáo án chuẩn mẫu..."):
                data = _lp_generate_lesson_plan(
                    api_key=api_key,
                    system_prompt=system_prompt,
                    user_note=teacher_note,
                    lesson_name=lesson_title if lesson_title else f"{subject} {grade} ({ppct_text})",
                    duration_min=int(duration),
                    class_size=int(class_size)
                )

            # 3) Lưu kết quả
            st.session_state[_lp_key("last_title")] = data.get("title", f"Giáo án - {ppct_text}")
            st.session_state[_lp_key("last_html")] = data.get("planHtml", "")

            # 4) Tự nhảy sang Xem trước & Xuất (KHÔNG đụng key widget)
            _lp_set_active("6) Xem trước & Xuất")

            st.success("✅ Tạo giáo án thành công!")
            st.rerun()

        except Exception as e:
            st.error(f"Lỗi AI: {e}")

    # ===============================
    # NÚT XOÁ (PHẢI Ở NGOÀI if TRÊN)
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
        <p class="dash-sub">Khung giáo án tích hợp năng lực số (mở rộng sau).</p>
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
    st.markdown("<div class='css-card'>", unsafe_allow_html=True)
    st.markdown("## 💻 AI EXAM – Soạn giáo án Năng lực số")
    st.info("Mô-đun đang hoàn thiện. (Sẽ tích hợp sau)")
    st.markdown("</div>", unsafe_allow_html=True)

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
