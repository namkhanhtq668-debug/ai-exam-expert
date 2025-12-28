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
# ==============================================================================
# [MODULE NLS] DỮ LIỆU & CẤU HÌNH CHO SOẠN GIÁO ÁN NĂNG LỰC SỐ
# ==============================================================================

# 1. Khung năng lực số (Chuyển từ constants.ts)
NLS_FRAMEWORK_DATA = """
KHUNG NĂNG LỰC SỐ (DIGITAL COMPETENCE FRAMEWORK) - CẬP NHẬT MỚI NHẤT
MÔ TẢ CÁC MIỀN NĂNG LỰC VÀ YÊU CẦU CẦN ĐẠT (YCCĐ):

1. MIỀN 1: KHAI THÁC DỮ LIỆU VÀ THÔNG TIN
   1.1. Duyệt, tìm kiếm và lọc dữ liệu (CB1, CB2, TC1, NC1).
   1.2. Đánh giá dữ liệu (CB1, TC1, NC1).
   1.3. Quản lý dữ liệu (CB1, TC1).

2. MIỀN 2: GIAO TIẾP VÀ HỢP TÁC
   2.1. Tương tác qua công nghệ.
   2.4. Hợp tác qua công nghệ.
   2.5. Văn hóa mạng (Netiquette).

3. MIỀN 3: SÁNG TẠO NỘI DUNG SỐ
   3.1. Phát triển nội dung.
   3.3. Bản quyền và giấy phép.

4. MIỀN 4: AN TOÀN SỐ
   4.2. Bảo vệ dữ liệu cá nhân.
   4.3. Bảo vệ sức khỏe.

5. MIỀN 5: GIẢI QUYẾT VẤN ĐỀ
   5.2. Xác định nhu cầu và giải pháp.
   5.3. Sử dụng sáng tạo.

6. MIỀN 6: ỨNG DỤNG AI
   6.1. Hiểu biết về AI.
   6.2. Sử dụng công cụ AI.
   6.3. Đạo đức AI.
"""

# 2. Câu lệnh hệ thống cho AI (System Prompt)
SYSTEM_INSTRUCTION_NLS = f"""
Bạn là chuyên gia tư vấn giáo dục cao cấp, chuyên về chuyển đổi số và Khung Năng lực số (NLS) tại Việt Nam.

DỮ LIỆU KHUNG NĂNG LỰC SỐ:
{NLS_FRAMEWORK_DATA}

NHIỆM VỤ CỐT LÕI:
1. Phân tích sâu sắc nội dung giáo án người dùng cung cấp để tìm ra các "điểm chạm" có thể tích hợp NLS một cách tự nhiên nhất.
2. Lựa chọn các YCCĐ (Yêu cầu cần đạt) từ Khung NLS phù hợp với trình độ học sinh và đặc thù môn học.
3. Nếu có file PPCT, bạn phải ưu tiên 100% nội dung NLS trong PPCT đó.

CẤU TRÚC ĐẦU RA (MARKDOWN):
I. THÔNG TIN CHUNG (Giữ nguyên từ giáo án gốc)
II. MỤC TIÊU
   1. Kiến thức, kĩ năng... (Giữ nguyên)
   2. Năng lực chung... (Giữ nguyên)
   3. Năng lực đặc thù... (Giữ nguyên)
   4. Năng lực số (Bổ sung mới): 
      - [Mã YCCĐ]: Mô tả biểu hiện cụ thể học sinh sẽ đạt được.
III. THIẾT BỊ DẠY HỌC VÀ HỌC LIỆU SỐ (Bổ sung các công cụ cần thiết cho NLS)
IV. TIẾN TRÌNH DẠY HỌC
   - Tích hợp nội dung NLS vào các hoạt động bằng thẻ <u>...</u> hoặc in đậm. 
   - Ví dụ: "HS sử dụng máy tính *thực hiện tra cứu thông tin trên trang web chính thống [1.1.CB2]*".

QUY TẮC KỸ THUẬT:
- Giữ nguyên các định dạng **Bold**, *Italic* của bản gốc.
- Không thay đổi nội dung chuyên môn gốc, chỉ làm phong phú thêm.
"""

# 3. Hàm xử lý AI riêng cho Module này
def generate_nls_lesson_plan(api_key, lesson_content, distribution_content, textbook, subject, grade, analyze_only):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=SYSTEM_INSTRUCTION_NLS)
    
    user_prompt = f"""
    THÔNG TIN ĐẦU VÀO:
    - Bộ sách: {textbook} | Môn: {subject} | Lớp: {grade}
    - Chế độ: {"CHỈ PHÂN TÍCH (Không viết lại bài)" if analyze_only else "VIẾT LẠI GIÁO ÁN TÍCH HỢP NLS"}
    
    NỘI DUNG PPCT (Yêu cầu cứng):
    {distribution_content if distribution_content else "Không có, tự đề xuất theo khung NLS."}
    
    NỘI DUNG GIÁO ÁN GỐC:
    {lesson_content}
    """
    
    try:
        response = model.generate_content(user_prompt)
        return response.text
    except Exception as e:
        return f"Lỗi AI: {str(e)}"
from jsonschema import validate, Draft202012Validator # [MỚI] Thư viện Validate Schema

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
# [MỚI] DỮ LIỆU NĂNG LỰC SỐ (TỪ FILE constants.ts CỦA THẦY)
# ==============================================================================
NLS_FRAMEWORK_DATA = """
KHUNG NĂNG LỰC SỐ (DIGITAL COMPETENCE FRAMEWORK) - CẬP NHẬT MỚI NHẤT

MÔ TẢ CÁC MIỀN NĂNG LỰC VÀ YÊU CẦU CẦN ĐẠT (YCCĐ):

1. MIỀN 1: KHAI THÁC DỮ LIỆU VÀ THÔNG TIN
   1.1. Duyệt, tìm kiếm và lọc dữ liệu:
      - CB1: Xác định được nhu cầu thông tin cơ bản, thực hiện tìm kiếm bằng từ khóa đơn giản.
      - CB2: Biết cách lọc và sắp xếp kết quả tìm kiếm theo các tiêu chí đơn giản (thời gian, loại file).
      - TC1: Xây dựng chiến lược tìm kiếm phức tạp, sử dụng các toán tử tìm kiếm (AND, OR, "").
      - NC1: Đánh giá và điều chỉnh chiến lược tìm kiếm dựa trên độ nhiễu của thông tin.
   1.2. Đánh giá dữ liệu:
      - CB1: Nhận biết được tin giả, tin rác cơ bản dựa trên cảm tính hoặc nguồn tin không rõ ràng.
      - TC1: Phân tích được tính tin cậy, khách quan và bản quyền của nguồn dữ liệu.
      - NC1: So sánh và đối chiếu nhiều nguồn tin để xác chứng dữ liệu trước khi sử dụng.
   1.3. Quản lý dữ liệu:
      - CB1: Biết lưu trữ file vào thư mục và đặt tên gợi nhớ.
      - TC1: Sử dụng các dịch vụ lưu trữ đám mây (Drive, OneDrive) để tổ chức dữ liệu khoa học.

2. MIỀN 2: GIAO TIẾP VÀ HỢP TÁC
   2.1. Tương tác qua công nghệ:
      - CB1: Sử dụng được email, tin nhắn để gửi thông tin đơn giản.
      - TC1: Lựa chọn được công cụ giao tiếp phù hợp với mục đích và đối tượng.
   2.4. Hợp tác qua công nghệ:
      - CB1: Tham gia vào các tệp tin chia sẻ chung (Google Docs) để đóng góp ý kiến.
      - TC1: Sử dụng công nghệ để đồng sáng tạo sản phẩm, quản lý tiến độ nhóm (Trello, Planner).
   2.5. Văn hóa mạng (Netiquette):
      - CB1: Biết cách ứng xử lịch sự, không dùng ngôn từ gây hấn trên không gian mạng.
      - TC1: Hiểu và tuân thủ các quy tắc đạo đức, chuẩn mực văn hóa số.

3. MIỀN 3: SÁNG TẠO NỘI DUNG SỐ
   3.1. Phát triển nội dung:
      - CB1: Tạo được văn bản, hình ảnh, bài trình chiếu đơn giản.
      - TC1: Thiết kế được nội dung đa phương tiện (video, infographic) thẩm mỹ.
      - NC1: Tạo ra các sản phẩm số độc đáo, giải quyết vấn đề thực tế.
   3.3. Bản quyền và giấy phép:
      - CB1: Biết trích dẫn nguồn khi sử dụng tài liệu từ internet.
      - TC1: Hiểu về các loại giấy phép Creative Commons (CC).

4. MIỀN 4: AN TOÀN SỐ
   4.2. Bảo vệ dữ liệu cá nhân:
      - CB1: Biết đặt mật khẩu mạnh, không chia sẻ thông tin cá nhân.
      - TC1: Hiểu về cơ chế thu thập dữ liệu và thiết lập quyền riêng tư.
   4.3. Bảo vệ sức khỏe:
      - CB1: Nhận biết tác hại của việc sử dụng thiết bị số quá thời gian.
      - TC1: Biết tự điều chỉnh thời gian sử dụng và vận động.

5. MIỀN 5: GIẢI QUYẾT VẤN ĐỀ
   5.2. Xác định nhu cầu và giải pháp:
      - CB1: Sử dụng công cụ số hỗ trợ tính toán, tra cứu.
      - TC1: Sử dụng thành thạo phần mềm chuyên dụng (GeoGebra, mô phỏng) để giải quyết nhiệm vụ.
   5.3. Sử dụng sáng tạo:
      - NC1: Vận dụng công cụ số tạo giải pháp mới.

6. MIỀN 6: ỨNG DỤNG AI (CẬP NHẬT MỚI)
   6.1. Hiểu biết về AI:
      - CB1: Hiểu AI là gì, nhận biết ứng dụng AI.
      - TC1: Hiểu nguyên lý AI tạo sinh và hạn chế (ảo giác).
   6.2. Sử dụng công cụ AI:
      - CB1: Biết ra lệnh (prompt) đơn giản.
      - TC1: Biết viết prompt phức tạp, cung cấp ngữ cảnh (Context).
   6.3. Đạo đức AI:
      - TC1: Nhận thức về liêm chính học thuật khi dùng AI.
"""

SYSTEM_INSTRUCTION_NLS = f"""
Bạn là chuyên gia tư vấn giáo dục cao cấp, chuyên về chuyển đổi số và Khung Năng lực số (NLS) tại Việt Nam.

DỮ LIỆU KHUNG NĂNG LỰC SỐ:
{NLS_FRAMEWORK_DATA}

NHIỆM VỤ CỐT LÕI:
1. Phân tích sâu sắc nội dung giáo án người dùng cung cấp để tìm ra các "điểm chạm" có thể tích hợp NLS một cách tự nhiên nhất (không gượng ép).
2. Lựa chọn các YCCĐ (Yêu cầu cần đạt) từ Khung NLS trên phù hợp với trình độ học sinh và đặc thù môn học.
3. Nếu có nội dung PPCT (Phân phối chương trình), bạn phải ưu tiên 100% nội dung NLS trong PPCT đó.

CẤU TRÚC ĐẦU RA (MARKDOWN):
I. THÔNG TIN CHUNG (Giữ nguyên từ giáo án gốc)
II. MỤC TIÊU
   1. Kiến thức, kĩ năng... (Giữ nguyên)
   2. Năng lực chung... (Giữ nguyên)
   3. Năng lực đặc thù... (Giữ nguyên)
   4. Năng lực số (Bổ sung mới): 
      - [Mã YCCĐ]: Mô tả biểu hiện cụ thể học sinh sẽ đạt được trong bài này.
III. THIẾT BỊ DẠY HỌC VÀ HỌC LIỆU SỐ (Bổ sung các công cụ cần thiết cho NLS)
IV. TIẾN TRÌNH DẠY HỌC
   - Tích hợp nội dung NLS vào các hoạt động bằng thẻ <u>...</u> (in nghiêng hoặc đậm để làm nổi bật). 
   - Ví dụ: "HS sử dụng máy tính *thực hiện tra cứu thông tin trên trang web chính thống [1.1.CB2]*".

QUY TẮC KỸ THUẬT:
- Công thức Toán/Lý/Hóa: Sử dụng LaTeX trong $...$.
- Bảng biểu: Sử dụng Markdown Table.
- Không thay đổi nội dung chuyên môn của giáo án gốc, chỉ làm phong phú thêm bằng năng lực số.
"""

def generate_nls_lesson_plan(api_key, lesson_content, subject, grade, textbook, ppct_content, analyze_only):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=SYSTEM_INSTRUCTION_NLS)
    
    prompt = f"""
    THÔNG TIN:
    - Môn: {subject} | Lớp: {grade} | Sách: {textbook}
    - Chế độ: {"Chỉ phân tích, không sửa đổi nội dung gốc" if analyze_only else "Tích hợp và viết lại giáo án"}
    
    YÊU CẦU CỦA TRƯỜNG (PPCT):
    {ppct_content if ppct_content else "Không có, tự đề xuất theo khung NLS."}
    
    NỘI DUNG GIÁO ÁN GỐC:
    {lesson_content}
    """
    
    response = model.generate_content(prompt)
    return response.text

# ==============================================================================
# [QUAN TRỌNG] DỮ LIỆU YCCĐ CŨ (GIỮ NGUYÊN)
# ==============================================================================
FULL_YCCD_DATA = [
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
# [MỚI] 2.1. DỮ LIỆU PPCT
# ==============================================================================
PPCT_DATA = [
    # Ví dụ Toán lớp 5
    {"cap_hoc": "Tiểu học", "mon": "Toán", "lop": "Lớp 5", "bo_sach": "Kết nối tri thức với cuộc sống", "tuan": 1, "tiet": 1, "bai_id": "T5-KNTT-T1-1", "ten_bai": "Ôn tập khái niệm phân số", "ghi_chu": "Tiết 1"},
    {"cap_hoc": "Tiểu học", "mon": "Toán", "lop": "Lớp 5", "bo_sach": "Kết nối tri thức với cuộc sống", "tuan": 1, "tiet": 2, "bai_id": "T5-KNTT-T1-2", "ten_bai": "Ôn tập tính chất cơ bản của phân số", "ghi_chu": "Tiết 2"},
    # Ví dụ Tiếng Việt lớp 5
    {"cap_hoc": "Tiểu học", "mon": "Tiếng Việt", "lop": "Lớp 5", "bo_sach": "Chân trời sáng tạo", "tuan": 1, "tiet": 1, "bai_id": "TV5-CTST-T1-1", "ten_bai": "Đọc: Chiều dòng sông", "ghi_chu": "Đọc hiểu"},
]

def ppct_filter(cap_hoc, mon, lop, bo_sach):
    return [x for x in PPCT_DATA if x.get("cap_hoc") == cap_hoc and x.get("mon") == mon and x.get("lop") == lop and x.get("bo_sach") == bo_sach]

# ==============================================================================
# 2. CONSTANTS (GIỮ NGUYÊN)
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
# 3. GIAO DIỆN & CSS (CẬP NHẬT CSS CHO BẢNG)
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

/* ===== Word Preview CSS ===== */
.paper-view table { width: 100%; border-collapse: collapse; margin-bottom: 1em; }
.paper-view th, .paper-view td { border: 1px solid black; padding: 6px; text-align: left; vertical-align: top; }
.paper-view th { background-color: #f2f2f2; font-weight: bold; }

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

# [CẬP NHẬT] Hàm tạo File Word chuẩn Font XML VÀ CÓ BẢNG
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
            table {{ border-collapse: collapse; width: 100%; border: 1px solid black; }}
            td, th {{ border: 1px solid black; padding: 5px; vertical-align: top; }}
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

# ==============================================================================
# [PATCH 3/3] RENDER HTML TỪ JSON (BẢNG 2 CỘT GV/HS) - KHÓA MẪU
# ==============================================================================

def _html_escape(s: str) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def _render_ul(items) -> str:
    if not items:
        return "<ul><li>...</li></ul>"
    lis = "".join([f"<li>{_html_escape(x)}</li>" for x in items if str(x).strip()])
    return f"<ul>{lis or '<li>...</li>'}</ul>"

def render_lesson_plan_html(data: dict) -> str:
    meta = data.get("meta", {})
    sec = data.get("sections", {})

    sec_I = sec.get("I", {})
    sec_II = sec.get("II", {})
    sec_III = sec.get("III", {})
    sec_IV = sec.get("IV", {})

    cap_hoc = meta.get("cap_hoc", "")
    mon = meta.get("mon", "")
    lop = meta.get("lop", "")
    bo_sach = meta.get("bo_sach", "")
    ten_bai = meta.get("ten_bai", "")
    thoi_luong = meta.get("thoi_luong", "")
    si_so = meta.get("si_so", "")

    ppct = meta.get("ppct", {}) or {}
    tuan = ppct.get("tuan", "")
    tiet = ppct.get("tiet", "")
    bai_id = ppct.get("bai_id", "")
    ghi_chu = ppct.get("ghi_chu", "")

    # I
    yccd = sec_I.get("yeu_cau_can_dat", []) or []
    pham_chat = sec_I.get("pham_chat", []) or []
    nang_luc = sec_I.get("nang_luc", []) or []
    nang_luc_dac_thu = sec_I.get("nang_luc_dac_thu", []) or []
    nang_luc_so = sec_I.get("nang_luc_so", []) or []

    # II
    gv_tools = sec_II.get("giao_vien", []) or []
    hs_tools = sec_II.get("hoc_sinh", []) or []

    # III
    activities = sec_III.get("hoat_dong", []) or []
    table_rows = ""

    for idx, a in enumerate(activities, start=1):
        ten_hd = a.get("ten_hoat_dong", f"Hoạt động {idx}")
        tg = a.get("thoi_gian", "")
        muc_tieu = a.get("muc_tieu", []) or []
        cot_loi = a.get("noi_dung_cot_loi", []) or []
        gv_list = a.get("gv", []) or []
        hs_list = a.get("hs", []) or []

        gv_html = ""
        if muc_tieu:
            gv_html += f"<div><b>Mục tiêu:</b>{_render_ul(muc_tieu)}</div>"
        if cot_loi:
            gv_html += f"<div><b>Nội dung cốt lõi:</b>{_render_ul(cot_loi)}</div>"
        gv_html += f"<div><b>GV:</b>{_render_ul(gv_list)}</div>"

        hs_html = f"<div><b>HS:</b>{_render_ul(hs_list)}</div>"

        table_rows += f"""
        <tr>
            <td style="width:42px; text-align:center;"><b>{idx}</b></td>
            <td style="width:160px;"><b>{_html_escape(ten_hd)}</b></td>
            <td style="width:70px; text-align:center;">{_html_escape(tg)}</td>
            <td style="width:50%;">{gv_html}</td>
            <td style="width:50%;">{hs_html}</td>
        </tr>
        """

    if not table_rows.strip():
        table_rows = """
        <tr>
            <td style="text-align:center;"><b>1</b></td>
            <td><b>Khởi động</b></td>
            <td style="text-align:center;">5</td>
            <td><ul><li>Tổ chức cho HS...</li><li>Gợi mở...</li></ul></td>
            <td><ul><li>HS tham gia...</li><li>HS trả lời...</li></ul></td>
        </tr>
        """

    # IV
    dieu_chinh = sec_IV.get("dieu_chinh_sau_bai_day", "") or ""
    if not dieu_chinh.strip():
        dieu_chinh = "...................................................................................."

    html = f"""
    <div style="font-family:'Times New Roman', serif; font-size:13pt; line-height:1.3; color:#000;">
        <div style="text-align:center; font-weight:bold; font-size:14pt; margin-bottom:10px;">
            KẾ HOẠCH BÀI DẠY
        </div>

        <div style="margin-bottom:10px;">
            <b>Cấp học:</b> {_html_escape(cap_hoc)} &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Môn:</b> {_html_escape(mon)} &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Lớp:</b> {_html_escape(lop)}<br/>
            <b>Bộ sách:</b> {_html_escape(bo_sach)}<br/>
            <b>PPCT:</b> Tuần {_html_escape(tuan)} – Tiết {_html_escape(tiet)} – Mã bài {_html_escape(bai_id)} {("– " + _html_escape(ghi_chu)) if str(ghi_chu).strip() else ""}<br/>
            <b>Tên bài:</b> {_html_escape(ten_bai)}<br/>
            <b>Thời lượng:</b> {_html_escape(thoi_luong)} phút &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Sĩ số:</b> {_html_escape(si_so)} HS
        </div>

        <div style="margin:10px 0 6px 0; font-weight:bold;">I. YÊU CẦU CẦN ĐẠT</div>
        <div><b>Yêu cầu cần đạt:</b>{_render_ul(yccd)}</div>
        <div><b>Phẩm chất:</b>{_render_ul(pham_chat)}</div>
        <div><b>Năng lực chung:</b>{_render_ul(nang_luc)}</div>
        <div><b>Năng lực đặc thù:</b>{_render_ul(nang_luc_dac_thu)}</div>
        <div><b>Năng lực số (nếu có):</b>{_render_ul(nang_luc_so)}</div>

        <div style="margin:10px 0 6px 0; font-weight:bold;">II. ĐỒ DÙNG DẠY HỌC</div>
        <div><b>Giáo viên:</b>{_render_ul(gv_tools)}</div>
        <div><b>Học sinh:</b>{_render_ul(hs_tools)}</div>

        <div style="margin:10px 0 6px 0; font-weight:bold;">III. CÁC HOẠT ĐỘNG DẠY – HỌC CHỦ YẾU</div>
        <table border="1" style="width:100%; border-collapse:collapse;">
            <tr>
                <th style="width:42px; text-align:center;">STT</th>
                <th style="width:160px; text-align:center;">Hoạt động</th>
                <th style="width:70px; text-align:center;">Thời gian</th>
                <th style="text-align:center;">Hoạt động của GV</th>
                <th style="text-align:center;">Hoạt động của HS</th>
            </tr>
            {table_rows}
        </table>

        <div style="margin:10px 0 6px 0; font-weight:bold;">IV. ĐIỀU CHỈNH SAU BÀI DẠY</div>
        <div>{_html_escape(dieu_chinh)}</div>
    </div>
    """.strip()

    return html

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
        # [SỬA LỖI 404] Dùng gemini-2.0-flash theo yêu cầu
        self.model = genai.GenerativeModel('gemini-2.0-flash')

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
# [MỚI] 2.2. JSON SCHEMA KHÓA CỨNG (CÓ BẢNG)
# ==============================================================================
LESSON_PLAN_SCHEMA = {
    "type": "object",
    "required": ["meta", "sections", "renderHtml"],
    "additionalProperties": False,
    "properties": {
        "meta": {
            "type": "object",
            "required": ["cap_hoc", "mon", "lop", "bo_sach", "ppct", "ten_bai", "thoi_luong"],
            "additionalProperties": False,
            "properties": {
                "cap_hoc": {"type": "string"},
                "mon": {"type": "string"},
                "lop": {"type": "string"},
                "bo_sach": {"type": "string"},
                "ppct": {
                    "type": "object",
                    "required": ["tuan", "tiet", "bai_id"],
                    "additionalProperties": False,
                    "properties": {
                        "tuan": {"type": "integer", "minimum": 1, "maximum": 60},
                        "tiet": {"type": "integer", "minimum": 1, "maximum": 20},
                        "bai_id": {"type": "string"},
                        "ghi_chu": {"type": "string"}
                    }
                },
                "ten_bai": {"type": "string", "minLength": 2},
                "thoi_luong": {"type": "integer", "minimum": 30, "maximum": 120},
                "si_so": {"type": "integer", "minimum": 10, "maximum": 60},
                "ngay_day": {"type": "string"}
            }
        },
        "sections": {
            "type": "object",
            "required": ["I", "II", "III", "IV"],
            "additionalProperties": False,
            "properties": {
                "I": {  # Yêu cầu cần đạt
                    "type": "object",
                    "required": ["yeu_cau_can_dat"],
                    "additionalProperties": False,
                    "properties": {
                        "yeu_cau_can_dat": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"}
                        },
                        "pham_chat": {"type": "array", "items": {"type": "string"}},
                        "nang_luc": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "II": {  # Đồ dùng dạy học
                    "type": "object",
                    "required": ["giao_vien", "hoc_sinh"],
                    "additionalProperties": False,
                    "properties": {
                        "giao_vien": {"type": "array", "items": {"type": "string"}},
                        "hoc_sinh": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "III": {  # Tiến trình dạy học
                    "type": "object",
                    "required": ["hoat_dong"],
                    "additionalProperties": False,
                    "properties": {
                        "hoat_dong": {
                            "type": "array",
                            "minItems": 3,
                            "items": {
                                "type": "object",
                                "required": ["ten", "thoi_gian", "muc_tieu", "to_chuc"],
                                "additionalProperties": False,
                                "properties": {
                                    "ten": {"type": "string"},
                                    "thoi_gian": {"type": "integer", "minimum": 1, "maximum": 60},
                                    "muc_tieu": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                                    "to_chuc": {
                                        "type": "array",
                                        "minItems": 2,
                                        "items": {
                                            "type": "object",
                                            "required": ["gv", "hs", "san_pham"],
                                            "additionalProperties": False,
                                            "properties": {
                                                "gv": {"type": "string"},
                                                "hs": {"type": "string"},
                                                "san_pham": {"type": "string"}
                                            }
                                        }
                                    },
                                    "noi_dung_cot_loi": {"type": "array", "items": {"type": "string"}}
                                }
                            }
                        }
                    }
                },
                "IV": {  # Điều chỉnh sau bài dạy
                    "type": "object",
                    "required": ["dieu_chinh_sau_bai_day"],
                    "additionalProperties": False,
                    "properties": {
                        "dieu_chinh_sau_bai_day": {"type": "string"}
                    }
                }
            }
        },
        "renderHtml": {"type": "string", "minLength": 50, "description": "Toàn bộ nội dung giáo án dạng HTML. Phần III PHẢI là bảng (table) 2 cột: Hoạt động của GV và Hoạt động của HS."}
    }
}

# ==============================================================================
# [PATCH 1/3] LESSON PLAN DATA-ONLY SCHEMA (CẤP SỞ) + VALIDATOR
# - AI CHỈ TRẢ JSON DATA, KHÔNG TRẢ HTML
# - HỆ THỐNG TỰ RENDER HTML
# ==============================================================================

from jsonschema import validate, Draft202012Validator, ValidationError

LESSON_PLAN_DATA_SCHEMA = {
    "type": "object",
    "required": ["meta", "sections"],
    "additionalProperties": False,
    "properties": {
        "meta": {
            "type": "object",
            "required": ["cap_hoc", "mon", "lop", "bo_sach", "ppct", "ten_bai", "thoi_luong", "si_so"],
            "additionalProperties": False,
            "properties": {
                "cap_hoc": {"type": "string", "minLength": 2},
                "mon": {"type": "string", "minLength": 2},
                "lop": {"type": "string", "minLength": 2},
                "bo_sach": {"type": "string", "minLength": 2},
                "ppct": {
                    "type": "object",
                    "required": ["tuan", "tiet", "bai_id"],
                    "additionalProperties": False,
                    "properties": {
                        "tuan": {"type": "integer", "minimum": 1, "maximum": 60},
                        "tiet": {"type": "integer", "minimum": 1, "maximum": 30},
                        "bai_id": {"type": "string", "minLength": 2},
                        "ghi_chu": {"type": "string"}
                    }
                },
                "ten_bai": {"type": "string", "minLength": 2},
                "thoi_luong": {"type": "integer", "minimum": 30, "maximum": 120},
                "si_so": {"type": "integer", "minimum": 10, "maximum": 60},
                "ngay_day": {"type": "string"}
            }
        },
        "sections": {
            "type": "object",
            "required": ["I", "II", "III", "IV"],
            "additionalProperties": False,
            "properties": {
                "I": {
                    "type": "object",
                    "required": ["yeu_cau_can_dat"],
                    "additionalProperties": False,
                    "properties": {
                        "yeu_cau_can_dat": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "pham_chat": {"type": "array", "items": {"type": "string"}},
                        "nang_luc": {"type": "array", "items": {"type": "string"}},
                        "nang_luc_dac_thu": {"type": "array", "items": {"type": "string"}},
                        "nang_luc_so": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "II": {
                    "type": "object",
                    "required": ["giao_vien", "hoc_sinh"],
                    "additionalProperties": False,
                    "properties": {
                        "giao_vien": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "hoc_sinh": {"type": "array", "minItems": 1, "items": {"type": "string"}}
                    }
                },
                "III": {
                    "type": "object",
                    "required": ["hoat_dong"],
                    "additionalProperties": False,
                    "properties": {
                        "hoat_dong": {
                            "type": "array",
                            "minItems": 3,
                            "items": {
                                "type": "object",
                                "required": ["ten_hoat_dong", "thoi_gian", "gv", "hs"],
                                "additionalProperties": False,
                                "properties": {
                                    "ten_hoat_dong": {"type": "string", "minLength": 2},
                                    "thoi_gian": {"type": "integer", "minimum": 1, "maximum": 60},
                                    "muc_tieu": {"type": "array", "items": {"type": "string"}},
                                    "noi_dung_cot_loi": {"type": "array", "items": {"type": "string"}},
                                    "gv": {"type": "array", "minItems": 2, "items": {"type": "string"}},
                                    "hs": {"type": "array", "minItems": 2, "items": {"type": "string"}}
                                }
                            }
                        }
                    }
                },
                "IV": {
                    "type": "object",
                    "required": ["dieu_chinh_sau_bai_day"],
                    "additionalProperties": False,
                    "properties": {
                        "dieu_chinh_sau_bai_day": {"type": "string", "minLength": 1}
                    }
                }
            }
        }
    }
}

def validate_lesson_plan_data(data: dict) -> None:
    Draft202012Validator.check_schema(LESSON_PLAN_DATA_SCHEMA)
    validate(instance=data, schema=LESSON_PLAN_DATA_SCHEMA)

def _schema_error_to_text(e: Exception) -> str:
    if isinstance(e, ValidationError):
        path = " → ".join([str(p) for p in e.path]) if e.path else "(root)"
        return f"SchemaError at {path}: {e.message}"
    return str(e)

def validate_lesson_plan(data: dict) -> None:
    try:
        Draft202012Validator.check_schema(LESSON_PLAN_SCHEMA)
        validate(instance=data, schema=LESSON_PLAN_SCHEMA)
    except Exception as e:
        print(f"Schema Warning: {e}")

# ==============================================================================
# [MỚI] 2.3. HÀM TẠO PROMPT & GỌI AI (CHUẨN HÓA BẢNG 2 CỘT)
# ==============================================================================
def build_lesson_system_prompt_locked(meta: dict, teacher_note: str) -> str:
    return f"""
VAI TRÒ: Bạn là Giáo viên Tiểu học cốt cán, chuyên soạn GIÁO ÁN MẪU theo định hướng phát triển năng lực (CV 2345/BGDĐT).

THÔNG TIN BÀI DẠY:
- Cấp học: {meta.get("cap_hoc")} | Môn: {meta.get("mon")} | Lớp: {meta.get("lop")}
- Tuần: {meta.get("tuan")} | Tiết: {meta.get("tiet")}
- Tên bài: {meta.get("ten_bai")} ({meta.get("ghi_chu","")})
- Mã bài: {meta.get("bai_id")}
- Bộ sách: {meta.get("bo_sach")}

YÊU CẦU CẤU TRÚC (BẮT BUỘC GIỐNG MẪU CHUẨN):
Giáo án phải trình bày dưới dạng HTML, font Times New Roman, gồm 4 phần chính:

I. Yêu cầu cần đạt:
- Nêu rõ năng lực đặc thù, năng lực chung và phẩm chất.

II. Đồ dùng dạy học:
- Giáo viên: (Slide, tranh ảnh, thẻ từ...)
- Học sinh: (SGK, bảng con...)

III. Các hoạt động dạy – học chủ yếu:
***QUAN TRỌNG NHẤT: Phần này phải kẻ BẢNG (HTML <table>) gồm 2 cột***
- Cột 1: Hoạt động của Giáo viên
- Cột 2: Hoạt động của Học sinh
- Nội dung chia thành các hoạt động lớn (dùng dòng colspan hoặc in đậm để phân cách):
  1. Khởi động (Trò chơi, hát, kết nối...)
  2. Khám phá / Hình thành kiến thức mới (hoặc Luyện tập thực hành tùy bài)
  3. Vận dụng / Trải nghiệm
*Lưu ý văn phong:* Dùng từ ngữ sư phạm như "Tổ chức cho HS...", "Yêu cầu HS...", "Mời đại diện nhóm...", "GV chốt lại...".
*Chi tiết:* Viết rõ lời thoại, câu hỏi của GV và câu trả lời dự kiến của HS. Viết rõ các phép tính hoặc nội dung bài tập (VD: 27 - 1,2 = 25,8).

IV. Điều chỉnh sau bài dạy:
- Để trống dòng kẻ chấm (...) để GV tự ghi.

GHI CHÚ GV: {teacher_note}

OUTPUT JSON FORMAT:
Chỉ trả về JSON hợp lệ với 2 trường chính:
1. "meta": Thông tin bài học.
2. "renderHtml": Toàn bộ nội dung giáo án dạng HTML (để hiển thị và in ấn). Trong đó phần III phải là thẻ <table> có border="1".
""".strip()

# [FIX] Hàm LOCKED: chỉ làm nhiệm vụ gọi AI và trả dict (KHÔNG chứa UI, KHÔNG tự gọi lại)
def generate_lesson_plan_locked(
    api_key: str,
    meta_ppct: dict,
    bo_sach: str,
    thoi_luong: int,
    si_so: int,
    teacher_note: str,
    model_name: str = "gemini-2.0-flash"
) -> dict:
    """
    Sinh JSON data-only theo LESSON_PLAN_DATA_SCHEMA (meta + sections).
    Không render HTML ở đây. Không dùng st.spinner ở đây.
    """
    genai.configure(api_key=api_key)

    # meta chuẩn (đúng schema)
    # req_meta: always define BEFORE any reference (prevents NameError when optional fields are missing)
    req_meta = {
        "khối_lớp": str(meta_ppct.get("lop", meta_ppct.get("khối_lớp", ""))).strip(),
        "môn": str(meta_ppct.get("mon", meta_ppct.get("môn", ""))).strip(),
        "bài": str(meta_ppct.get("ten_bai", meta_ppct.get("bài", ""))).strip(),
        "chủ_đề": str(meta_ppct.get("chu_de", meta_ppct.get("chủ_đề", ""))).strip(),
        "tuần": str(meta_ppct.get("tuan", meta_ppct.get("tuần", ""))).strip(),
        "tiết": str(meta_ppct.get("tiet", meta_ppct.get("tiết", ""))).strip(),
        "thời_lượng": str(meta_ppct.get("thoi_luong", meta_ppct.get("thời_lượng", ""))).strip(),
        "yccđ": (meta_ppct.get("yccđ") if isinstance(meta_ppct, dict) else ""),
        "nls": (meta_ppct.get("nls") if isinstance(meta_ppct, dict) else ""),
        "học_liệu": (meta_ppct.get("học_liệu") if isinstance(meta_ppct, dict) else ""),
        "thiết_bị": (meta_ppct.get("thiết_bị") if isinstance(meta_ppct, dict) else ""),
        "lưu_ý": (meta_ppct.get("lưu_ý") if isinstance(meta_ppct, dict) else ""),
    }

    # prompt data-only (khuyến nghị dùng prompt data-only thay vì prompt HTML)
    system_prompt = build_lesson_system_prompt_data_only(
        meta={
            "cap_hoc": req_meta["cap_hoc"],
            "mon": req_meta["mon"],
            "lop": req_meta["lop"],
            "bo_sach": req_meta["bo_sach"],
            "tuan": req_meta["ppct"]["tuan"],
            "tiet": req_meta["ppct"]["tiet"],
            "bai_id": req_meta["ppct"]["bai_id"],
            "ten_bai": req_meta["ten_bai"],
            "thoi_luong": req_meta["thoi_luong"],
            "si_so": req_meta["si_so"],
        },
        teacher_note=teacher_note
    )

    model = genai.GenerativeModel(model_name, system_instruction=system_prompt)

    safe_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    base_req = {"meta": req_meta, "note": teacher_note}
    last_err = ""

    # thử tối đa 2 lần, nếu sai schema thì tự sửa
    for attempt in range(1, 3):
        try:
            res = model.generate_content(
                json.dumps(base_req, ensure_ascii=False),
                generation_config={"response_mime_type": "application/json"},
                safety_settings=safe_settings
            )

            raw = json.loads(clean_json(res.text))

            data = {
                "meta": req_meta,
                "sections": raw.get("sections", {})
            }

            validate_lesson_plan_data(data)  # bắt buộc đúng schema
            return data

        except Exception as e:
            last_err = _schema_error_to_text(e)
            repair_note = f"""
[SCHEMA_REPAIR]
Bạn vừa trả JSON KHÔNG đạt schema.
LỖI: {last_err}

YÊU CẦU:
- Chỉ trả JSON gồm "meta" và "sections"
- sections phải có đủ I, II, III, IV
- III.hoat_dong >= 3; mỗi hoạt động có ten_hoat_dong, thoi_gian, gv>=2, hs>=2
- Không tạo HTML
Chỉ trả JSON
"""
            base_req = {"meta": req_meta, "note": teacher_note + "\n" + repair_note}

    # fallback an toàn
    return {
        "meta": req_meta,
        "sections": {
            "I": {"yeu_cau_can_dat": [f"(Lỗi tạo dữ liệu) {last_err}"]},
            "II": {"giao_vien": ["..."], "hoc_sinh": ["..."]},
            "III": {"hoat_dong": [
                {"ten_hoat_dong": "Khởi động", "thoi_gian": 5, "gv": ["...", "..."], "hs": ["...", "..."]},
                {"ten_hoat_dong": "Hình thành kiến thức", "thoi_gian": 15, "gv": ["...", "..."], "hs": ["...", "..."]},
                {"ten_hoat_dong": "Luyện tập/Vận dụng", "thoi_gian": 15, "gv": ["...", "..."], "hs": ["...", "..."]}
            ]},
            "IV": {"dieu_chinh_sau_bai_day": "...................................................................................."}
        }
    }

# ==============================================================================
# [PATCH 2/3] PROMPT KHÓA CỨNG: DATA-ONLY JSON (ANTI-HALLUCINATION)
# ==============================================================================

def build_lesson_system_prompt_data_only(meta: dict, teacher_note: str) -> str:
    return f"""
VAI TRÒ: Bạn là giáo viên tiểu học cốt cán, soạn KẾ HOẠCH BÀI DẠY theo CTGDPT 2018, văn phong hồ sơ chuyên môn cấp Sở.

DỮ LIỆU ĐẦU VÀO (CỐ ĐỊNH):
- Cấp học: {meta.get("cap_hoc")}
- Môn: {meta.get("mon")} | Lớp: {meta.get("lop")} | Bộ sách: {meta.get("bo_sach")}
- PPCT: Tuần {meta.get("tuan")} | Tiết {meta.get("tiet")} | Mã bài {meta.get("bai_id")}
- Tên bài: {meta.get("ten_bai")}
- Thời lượng: {meta.get("thoi_luong")} phút | Sĩ số: {meta.get("si_so")} HS

GHI CHÚ GIÁO VIÊN (PHẢI ƯU TIÊN):
{teacher_note}

MỤC TIÊU KỸ THUẬT (BẮT BUỘC TUYỆT ĐỐI):
1) CHỈ TRẢ VỀ 01 JSON HỢP LỆ theo schema. KHÔNG markdown. KHÔNG giải thích.
2) JSON chỉ gồm 2 khóa cấp cao: "meta" và "sections". Không thêm khóa khác.
3) "sections.III.hoat_dong" phải có ≥ 3 hoạt động. Mỗi hoạt động phải có:
   - ten_hoat_dong (string), thoi_gian (int),
   - gv là mảng ≥ 2 ý,
   - hs là mảng ≥ 2 ý.
4) KHÔNG được tạo HTML. Hệ thống sẽ tự render HTML đúng mẫu.
5) Nếu không có YCCĐ, hãy suy luận phù hợp CTGDPT 2018 và lứa tuổi.
6) Không bịa văn bản pháp lý. Chỉ viết nội dung sư phạm.

HÃY TRẢ VỀ JSON DUY NHẤT.
""".strip()


def generate_lesson_plan_data_only(
    api_key: str,
    meta_ppct: dict,
    teacher_note: str,
    model_name: str = "gemini-2.0-flash"
) -> dict:
    """
    Sinh JSON data-only theo LESSON_PLAN_DATA_SCHEMA.
    Nếu sai schema: tự sửa tối đa 2 lần.
    """
    genai.configure(api_key=api_key)

    # req_meta: always define BEFORE any reference (prevents NameError when optional fields are missing)
    req_meta = {
        "khối_lớp": str(meta_ppct.get("lop", meta_ppct.get("khối_lớp", ""))).strip(),
        "môn": str(meta_ppct.get("mon", meta_ppct.get("môn", ""))).strip(),
        "bài": str(meta_ppct.get("ten_bai", meta_ppct.get("bài", ""))).strip(),
        "chủ_đề": str(meta_ppct.get("chu_de", meta_ppct.get("chủ_đề", ""))).strip(),
        "tuần": str(meta_ppct.get("tuan", meta_ppct.get("tuần", ""))).strip(),
        "tiết": str(meta_ppct.get("tiet", meta_ppct.get("tiết", ""))).strip(),
        "thời_lượng": str(meta_ppct.get("thoi_luong", meta_ppct.get("thời_lượng", ""))).strip(),
        "yccđ": (meta_ppct.get("yccđ") if isinstance(meta_ppct, dict) else ""),
        "nls": (meta_ppct.get("nls") if isinstance(meta_ppct, dict) else ""),
        "học_liệu": (meta_ppct.get("học_liệu") if isinstance(meta_ppct, dict) else ""),
        "thiết_bị": (meta_ppct.get("thiết_bị") if isinstance(meta_ppct, dict) else ""),
        "lưu_ý": (meta_ppct.get("lưu_ý") if isinstance(meta_ppct, dict) else ""),
    }

    system_prompt = build_lesson_system_prompt_data_only(
        meta={
            "cap_hoc": req_meta["cap_hoc"],
            "mon": req_meta["mon"],
            "lop": req_meta["lop"],
            "bo_sach": req_meta["bo_sach"],
            "tuan": req_meta["ppct"]["tuan"],
            "tiet": req_meta["ppct"]["tiet"],
            "bai_id": req_meta["ppct"]["bai_id"],
            "ten_bai": req_meta["ten_bai"],
            "thoi_luong": req_meta["thoi_luong"],
            "si_so": req_meta["si_so"],
        },
        teacher_note=teacher_note
    )

    model = genai.GenerativeModel(model_name, system_instruction=system_prompt)

    safe_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    base_req = {"meta": req_meta, "note": teacher_note}
    last_err = ""

    for attempt in range(1, 3):
        try:
            res = model.generate_content(
                json.dumps(base_req, ensure_ascii=False),
                generation_config={"response_mime_type": "application/json"},
                safety_settings=safe_settings
            )

            raw = json.loads(clean_json(res.text))

            data = {
                "meta": req_meta,
                "sections": raw.get("sections", {})
            }

            validate_lesson_plan_data(data)
            return data

        except Exception as e:
            last_err = _schema_error_to_text(e)

            repair_note = f"""
[SCHEMA_REPAIR]
Bạn vừa trả JSON KHÔNG đạt schema.
LỖI: {last_err}

YÊU CẦU:
- Chỉ trả JSON gồm "meta" và "sections"
- sections phải có đủ I, II, III, IV
- III.hoat_dong >= 3; mỗi hoạt động có ten_hoat_dong, thoi_gian, gv>=2, hs>=2.
- Không tạo HTML.
Chỉ trả JSON.
"""
            base_req = {"meta": req_meta, "note": teacher_note + "\n" + repair_note}

    # fallback an toàn
    return {
        "meta": req_meta,
        "sections": {
            "I": {"yeu_cau_can_dat": [f"(Lỗi tạo dữ liệu) {last_err}"]},
            "II": {"giao_vien": ["..."], "hoc_sinh": ["..."]},
            "III": {"hoat_dong": [
                {"ten_hoat_dong": "Khởi động", "thoi_gian": 5, "gv": ["...", "..."], "hs": ["...", "..."]},
                {"ten_hoat_dong": "Hình thành kiến thức", "thoi_gian": 15, "gv": ["...", "..."], "hs": ["...", "..."]},
                {"ten_hoat_dong": "Luyện tập/Vận dụng", "thoi_gian": 15, "gv": ["...", "..."], "hs": ["...", "..."]}
            ]},
            "IV": {"dieu_chinh_sau_bai_day": "...................................................................................."}
        }
    }

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
                                            # [SỬA LỖI 404] Dùng gemini-2.0-flash
                                            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=SYSTEM_PROMPT)
                                            
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
    # XỬ LÝ NÚT BẤM (Đoạn này nằm trong hàm module_lesson_plan)
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
                # GỌI HÀM TẠO GIÁO ÁN
                data = generate_lesson_plan_locked(
                    api_key=api_key,
                    meta_ppct=meta_ppct,         # KHÔNG nhét bo_sach/thoi_luong/si_so vào meta_ppct nữa
                    bo_sach=book,                # truyền riêng
                    thoi_luong=int(duration),    # truyền riêng
                    si_so=int(class_size),       # truyền riêng
                    teacher_note=teacher_note,
                    model_name="gemini-2.0-flash"
                )

                # [SỬA QUAN TRỌNG]: Dùng biến 'data' thay vì 'data_json'
                html = render_lesson_plan_html(data)
                
                # Lưu kết quả vào Session State
                st.session_state[_lp_key("last_title")] = f"Giáo án - {meta_ppct['ten_bai']}"
                
                # [SỬA QUAN TRỌNG]: Lưu 'html' để hiển thị, không lưu 'data' (dictionary)
                st.session_state[_lp_key("last_html")] = html 

                # Tự nhảy sang tab Xem trước
                _lp_set_active("6) Xem trước & Xuất")

                st.success("✅ Tạo giáo án thành công!")
                st.rerun()

        except Exception as e:
            st.error(f"Lỗi AI: {e}")

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



