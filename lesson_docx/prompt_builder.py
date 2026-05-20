# -*- coding: utf-8 -*-
"""
Prompt builder — yêu cầu AI trả về JSON THUẦN theo schema, KHÔNG kèm HTML/markdown.

Nguyên tắc:
- AI chỉ tạo NỘI DUNG. AI không được quyết định bố cục.
- AI KHÔNG trả markdown, code fence, HTML, hay bất kỳ layout nào.
- AI chỉ trả 1 JSON object hợp lệ, parse được bằng json.loads().
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from .schema import BANNED_PHRASES, MIN_ACTIVITIES, MAX_ACTIVITIES


@dataclass
class LessonContext:
    """Tham số đầu vào để build prompt — do CODE cấp, không phải AI."""
    subject: str                # "Toán"
    grade: str                  # "4"
    lesson_title: str           # "Ôn tập các số đến 100 000"
    lesson_number: str = ""     # "Bài 1" — optional
    textbook_series: str = "Kết nối tri thức với cuộc sống"
    duration_minutes: int = 35  # Tổng thời lượng tiết học (phút)
    school: str = ""
    department: str = ""        # Tổ chuyên môn / Phòng GD&ĐT (tuỳ ngữ cảnh)
    teacher_name: str = ""
    school_year: str = "2025 - 2026"
    teaching_date: str = ""     # "DD/MM/YYYY"
    week: str = ""
    period: str = ""
    sgk_pages: str = ""
    extra_notes: str = ""       # Ghi chú thêm từ GV (nếu có)
    source_text: str = ""       # Trích nội dung SGK/tài liệu nếu có (giúp AI bám sát)


# JSON schema mô tả ngắn gọn để nhét vào prompt — viết bằng tiếng Việt cho AI hiểu
_SCHEMA_DESCRIPTION = """\
{
  "documentInfo": {
    "department": "PHÒNG GD&ĐT (chuỗi, có thể '...' nếu không biết)",
    "school": "Tên trường (chuỗi, BẮT BUỘC)",
    "schoolYear": "Năm học, định dạng 'YYYY - YYYY' (BẮT BUỘC)"
  },
  "lessonInfo": {
    "subject": "Tên môn (chuỗi, BẮT BUỘC)",
    "grade": "Khối lớp dạng '4' (chuỗi, BẮT BUỘC)",
    "lessonNumber": "Ví dụ 'Bài 1' hoặc chuỗi rỗng",
    "lessonTitle": "Tên bài học, in hoa (chuỗi, BẮT BUỘC)",
    "textbookSeries": "Bộ sách (BẮT BUỘC, mặc định 'Kết nối tri thức với cuộc sống')",
    "duration": "Thời lượng kèm số tiết, vd '01 tiết (35 phút)' (BẮT BUỘC)",
    "week": "Số tuần, vd '1' hoặc '...'",
    "period": "Tiết PPCT, vd '1' hoặc '...'",
    "teachingDate": "Ngày dạy DD/MM/YYYY (BẮT BUỘC)",
    "teacherName": "Họ tên giáo viên (BẮT BUỘC)",
    "sgkPages": "Trang SGK/học liệu, vd 'Trang 5-8' hoặc '...'"
  },
  "objectives": {
    "intro": "'Sau bài học, học sinh đạt được các yêu cầu sau:'",
    "specificCompetencies": ["Mảng câu mô tả NL ĐẶC THÙ môn học — 3-5 mục, mỗi mục 1 câu, bắt đầu bằng động từ Bloom (Đọc, Viết, Xác định, So sánh, Trình bày...)"],
    "generalCompetencies": ["Mảng 3 mục: 'Tự chủ và tự học: ...', 'Giao tiếp và hợp tác: ...', 'Giải quyết vấn đề và sáng tạo: ...' — mỗi mục có biểu hiện CỤ THỂ trong bài"],
    "qualities": ["Mảng 2-3 phẩm chất, mỗi mục dạng 'Chăm chỉ: ...' / 'Trung thực: ...' / 'Trách nhiệm: ...'"]
  },
  "teachingMaterials": {
    "teacher": ["Đồ dùng GV — 2-4 mục cụ thể (SGK, phiếu HT, bảng phụ, thẻ số, máy chiếu...)"],
    "students": ["Đồ dùng HS — 1-2 mục (SGK, vở, bảng con, bút...)"]
  },
  "teachingProcess": [
    {
      "title": "Tên hoạt động — VD 'Mở đầu - Khởi động' hoặc 'Luyện tập, thực hành - Ôn đọc viết'",
      "duration": "Thời gian dạng 'X phút'",
      "objective": "Mục tiêu 1 câu",
      "rows": [
        {
          "teacherActivities": "Mô tả việc GV làm — có thể nhiều câu, dùng dấu chấm; phải có lệnh cụ thể, câu hỏi mẫu trong ngoặc kép.",
          "studentActivities": "Mô tả việc HS làm — hành động quan sát được (đọc, viết, trao đổi, trả lời...).",
          "productAndAssessment": "Sản phẩm cụ thể HS tạo ra + cách GV đánh giá (gộp 1 cột). VD: 'HS đọc và viết đúng các số. GV quan sát, hỏi đáp nhanh, tuyên dương kịp thời.'"
        }
      ]
    }
  ],
  "differentiation": {
    "weakerStudents": "1 câu mô tả hỗ trợ HS còn hạn chế",
    "advancedStudents": "1 câu mô tả nhiệm vụ thêm cho HS hoàn thành tốt",
    "limitedResources": "1 câu mô tả phương án khi lớp thiếu thiết bị"
  },
  "assessment": [
    {
      "content": "Nội dung đánh giá (VD 'Đọc, viết số đến 100 000')",
      "criteria": "Mức cần đạt (VD 'Đọc, viết đúng; không nhầm hàng')",
      "method": "Phương pháp (VD 'Hỏi đáp, quan sát')",
      "tool": "Công cụ/minh chứng (VD 'Bảng con, vở bài tập')"
    }
  ],
  "worksheet": [
    {
      "title": "Tên bài tập (VD 'Bài 1. Viết số thích hợp vào chỗ chấm:')",
      "body": "Nội dung bài tập, có thể dùng \\n để xuống dòng"
    }
  ]
}\
"""


def build_lesson_prompt(ctx: LessonContext) -> str:
    """Sinh prompt cho AI. Output AI phải là 1 JSON object hợp lệ."""
    src_block = (
        f"\n# NGUỒN HỌC LIỆU GV CUNG CẤP (BÁM SÁT):\n{ctx.source_text[:8000]}\n"
        if ctx.source_text.strip() else ""
    )
    notes_block = (
        f"\n# GHI CHÚ THÊM CỦA GIÁO VIÊN:\n{ctx.extra_notes[:2000]}\n"
        if ctx.extra_notes.strip() else ""
    )

    banned_list = ", ".join(f'"{p}"' for p in BANNED_PHRASES)

    return f"""Bạn là chuyên gia soạn kế hoạch bài dạy (KHBD) cho giáo viên tiểu học Việt Nam,
chương trình GDPT 2018, áp dụng bộ sách "{ctx.textbook_series}".

NHIỆM VỤ: Tạo dữ liệu nội dung cho 1 bài học, trả về DUY NHẤT 1 JSON object hợp lệ (UTF-8).

# THÔNG TIN BÀI HỌC (đầu vào — CODE đã cấp):
- Môn: {ctx.subject}
- Lớp: {ctx.grade}
- Bài: {ctx.lesson_number} {ctx.lesson_title}
- Bộ sách: {ctx.textbook_series}
- Thời lượng: {ctx.duration_minutes} phút
- Trường: {ctx.school or "..."}
- Phòng/Tổ chuyên môn: {ctx.department or "..."}
- Giáo viên: {ctx.teacher_name or "..."}
- Năm học: {ctx.school_year}
- Ngày dạy: {ctx.teaching_date or "..."}
- Tuần / Tiết PPCT: {ctx.week or "..."} / {ctx.period or "..."}
- Trang SGK/Học liệu: {ctx.sgk_pages or "..."}
{src_block}{notes_block}

# QUY TẮC OUTPUT (BẮT BUỘC):
1. Trả về DUY NHẤT 1 JSON object. KHÔNG kèm markdown, KHÔNG ```json```, KHÔNG giải thích.
2. JSON phải parse được bằng json.loads(). Tiếng Việt phải có dấu chuẩn UTF-8.
3. Số phần tử teachingProcess: tối thiểu {MIN_ACTIVITIES}, tối đa {MAX_ACTIVITIES} hoạt động.
4. Tổng thời gian các hoạt động ≈ {ctx.duration_minutes} phút (sai số ±2 phút).
5. KHÔNG dùng các cụm cấm: {banned_list}.
6. Nếu thiếu dữ liệu cho 1 trường text, dùng chuỗi "..." (3 dấu chấm), KHÔNG viết "GV bổ sung" / "Chưa nhập".
7. Câu lệnh GV phải CỤ THỂ: "GV nêu yêu cầu: '...'" — KHÔNG viết chung chung "GV giới thiệu bài".
8. Hoạt động HS phải QUAN SÁT ĐƯỢC: "HS đọc thầm, gạch chân từ khóa" — KHÔNG viết "HS lắng nghe".
9. Với bài ôn tập/luyện tập: dùng 3-4 hoạt động (Mở đầu / Luyện tập 1 / Luyện tập 2 / Vận dụng / Củng cố).
   Với bài học mới: dùng 4-5 hoạt động (thêm "Hình thành kiến thức mới" sau "Mở đầu").
10. KHÔNG sinh trường nào ngoài schema dưới đây. KHÔNG đổi tên trường.

# JSON SCHEMA — output PHẢI khớp 100%:
{_SCHEMA_DESCRIPTION}

# VÍ DỤ 1 HOẠT ĐỘNG ĐÚNG FORMAT (chỉ tham khảo cấu trúc, không copy nội dung):
{{
  "title": "Mở đầu - Khởi động",
  "duration": "5 phút",
  "objective": "Tạo hứng thú, kết nối kiến thức về các số đến 100 000.",
  "rows": [
    {{
      "teacherActivities": "Tổ chức trò chơi 'Ai nhanh hơn': GV nêu các câu hỏi ngắn, ví dụ: 'Số lớn hơn 99 998 và bé hơn 100 000 là số nào?'. Nhận xét, tuyên dương, dẫn dắt vào bài.",
      "studentActivities": "Tham gia trả lời cá nhân hoặc theo nhóm; nêu cách suy nghĩ ngắn gọn; chuẩn bị sách vở vào bài học.",
      "productAndAssessment": "HS trả lời được một số câu hỏi khởi động. Đánh giá bằng quan sát, hỏi đáp nhanh, tuyên dương kịp thời."
    }}
  ]
}}

BẮT ĐẦU TRẢ JSON NGAY (không lời mở đầu):"""


def parse_json_response(raw: str) -> Optional[dict]:
    """Parse JSON từ output AI. Khoan dung với markdown code fence nếu AI quên quy tắc.

    Trả về dict nếu parse được, None nếu không.
    """
    import re

    text = (raw or "").strip()
    # Bóc ```json ... ``` nếu có
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    # Tìm JSON object bao ngoài cùng
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None
