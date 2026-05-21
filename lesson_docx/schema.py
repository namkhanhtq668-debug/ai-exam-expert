# -*- coding: utf-8 -*-
"""
JSON Schema cho Kế hoạch bài dạy tiểu học — khớp 100% mẫu PDF chuẩn 2025-2026.

Cấu trúc 7 mục La Mã (I-VII):
    I.   YÊU CẦU CẦN ĐẠT         (1. NL đặc thù / 2. NL chung / 3. Phẩm chất)
    II.  ĐỒ DÙNG DẠY HỌC          (1. Giáo viên / 2. Học sinh)
    III. CÁC HOẠT ĐỘNG DẠY HỌC CHỦ YẾU  (3-5 hoạt động, mỗi hoạt động bảng 3 cột)
    IV.  ĐIỀU CHỈNH, HỖ TRỢ VÀ PHÂN HÓA
    V.   ĐÁNH GIÁ THƯỜNG XUYÊN TRONG BÀI HỌC  (bảng 4 cột)
    VI.  PHIẾU HỌC TẬP THAM KHẢO  (danh sách bài tập)
    VII. ĐIỀU CHỈNH SAU BÀI DẠY   (3 mục con để GV ghi tay)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# ============================================================================
# I. YÊU CẦU CẦN ĐẠT
# ============================================================================

class Objectives(TypedDict):
    intro: str                          # "Sau bài học, học sinh đạt được các yêu cầu sau:"
    specificCompetencies: List[str]     # 1. Năng lực đặc thù môn [subject]
    generalCompetencies: List[str]      # 2. Năng lực chung (Tự chủ / Giao tiếp / Giải quyết VĐ)
    qualities: List[str]                # 3. Phẩm chất (Chăm chỉ / Trung thực / Trách nhiệm)


# ============================================================================
# II. ĐỒ DÙNG DẠY HỌC
# ============================================================================

class TeachingMaterials(TypedDict):
    teacher: List[str]      # Đồ dùng giáo viên
    students: List[str]     # Đồ dùng học sinh


# ============================================================================
# III. CÁC HOẠT ĐỘNG DẠY HỌC CHỦ YẾU (3-5 hoạt động linh hoạt)
# Bảng 3 cột: Hoạt động GV | Hoạt động HS | Sản phẩm/đánh giá (gộp 1 cột)
# ============================================================================

class ActivityRow(TypedDict):
    """Một dòng trong bảng 3 cột của 1 hoạt động."""
    teacherActivities: str          # Cột 1: Hoạt động của giáo viên
    studentActivities: str          # Cột 2: Hoạt động của học sinh
    productAndAssessment: str       # Cột 3: Sản phẩm/đánh giá (gộp)


class Activity(TypedDict):
    """Một hoạt động trong mục III."""
    title: str          # VD: "Mở đầu - Khởi động", "Luyện tập, thực hành - Ôn đọc, viết..."
    duration: str       # VD: "5 phút", "10 phút"
    objective: str      # Mục tiêu của hoạt động (1 câu)
    rows: List[ActivityRow]     # 1 hoặc nhiều dòng trong bảng


# ============================================================================
# IV. ĐIỀU CHỈNH, HỖ TRỢ VÀ PHÂN HÓA (3 nhóm HS)
# ============================================================================

class Differentiation(TypedDict):
    weakerStudents: str         # HS còn hạn chế
    advancedStudents: str       # HS hoàn thành tốt
    limitedResources: str       # Lớp thiếu thiết bị


# ============================================================================
# V. ĐÁNH GIÁ THƯỜNG XUYÊN — bảng 4 cột
# ============================================================================

class AssessmentRow(TypedDict):
    content: str        # Cột 1: Nội dung đánh giá
    criteria: str       # Cột 2: Mức cần đạt
    method: str         # Cột 3: Phương pháp
    tool: str           # Cột 4: Công cụ/minh chứng


# ============================================================================
# VI. PHIẾU HỌC TẬP THAM KHẢO
# ============================================================================

class WorksheetItem(TypedDict):
    title: str          # VD: "Bài 1. Viết số thích hợp vào chỗ chấm:"
    body: str           # Nội dung bài tập (có thể nhiều dòng, dùng \n để xuống dòng)


# ============================================================================
# Thông tin trên cùng văn bản
# ============================================================================

class DocumentInfo(TypedDict):
    department: str         # PHÒNG GD&ĐT (VD: "GD&ĐT Quận 1") — có thể "..." nếu trống
    school: str             # TRƯỜNG (VD: "Tiểu học Hồng Thái")
    schoolYear: str         # Năm học (VD: "2025 - 2026")


class LessonInfo(TypedDict):
    subject: str            # Môn (VD: "Toán")
    grade: str              # Lớp (VD: "4")
    lessonNumber: str       # Số bài (VD: "Bài 1") — có thể rỗng
    lessonTitle: str        # Tên bài (VD: "ÔN TẬP CÁC SỐ ĐẾN 100 000")
    textbookSeries: str     # Bộ sách (VD: "Kết nối tri thức với cuộc sống")
    duration: str           # Thời lượng (VD: "01 tiết (35 phút)")
    week: str               # Tuần (VD: "1") — có thể "..."
    period: str             # Tiết PPCT (VD: "1") — có thể "..."
    teachingDate: str       # Ngày dạy (VD: "20/05/2026")
    teacherName: str        # Giáo viên (VD: "Tuấn")
    sgkPages: str           # Trang SGK/Học liệu (VD: "Trang 5-8") — có thể "..."


# ============================================================================
# Toàn bộ JSON cho 1 giáo án
# ============================================================================

class LessonPlan(TypedDict):
    documentInfo: DocumentInfo
    lessonInfo: LessonInfo
    objectives: Objectives                              # Mục I
    teachingMaterials: TeachingMaterials                # Mục II
    teachingProcess: List[Activity]                     # Mục III (3-5 hoạt động)
    differentiation: Differentiation                    # Mục IV
    assessment: List[AssessmentRow]                     # Mục V
    worksheet: List[WorksheetItem]                      # Mục VI
    # Mục VII = chỗ trống cho GV ghi tay → renderer tự tạo dòng kẻ chấm,
    # không cần AI sinh dữ liệu.


# ============================================================================
# Yêu cầu tối thiểu để JSON được coi là HỢP LỆ
# ============================================================================

# Các trường BẮT BUỘC không được rỗng (renderer sẽ raise nếu thiếu)
REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "documentInfo",
    "lessonInfo",
    "objectives",
    "teachingMaterials",
    "teachingProcess",
    "differentiation",
    "assessment",
)

REQUIRED_DOCUMENT_INFO: tuple[str, ...] = ("school", "schoolYear")
# Chỉ yêu cầu các field NỘI DUNG bài học. Các field cá nhân (teachingDate, teacherName,
# week, period, sgkPages) cho phép rỗng — reviewer sẽ fill '......' để GV tự điền.
REQUIRED_LESSON_INFO: tuple[str, ...] = (
    "subject", "grade", "lessonTitle", "textbookSeries", "duration",
)

# Số lượng hoạt động cho phép trong mục III (linh hoạt theo kiểu bài)
MIN_ACTIVITIES: int = 3
MAX_ACTIVITIES: int = 5

# Phrase cấm trong file giáo án nộp tổ chuyên môn
BANNED_PHRASES: tuple[str, ...] = (
    "AIEXAM",
    "GV bổ sung",
    "bổ sung sau",
    "theo ảnh SGK",
    "Chưa nhập",
    "GV kiểm tra sau",
    "GV kiểm tra SGK",
    "[GV bổ sung]",
)

# Placeholder lịch sự thay phrase cấm
SAFE_PLACEHOLDER: str = "..."


def empty_lesson_plan() -> Dict[str, Any]:
    """Trả về 1 LessonPlan rỗng (mọi trường giá trị mặc định an toàn).
    Hữu ích cho test/fixture và làm fallback khi AI fail toàn bộ.
    """
    return {
        "documentInfo": {
            "department": SAFE_PLACEHOLDER,
            "school": SAFE_PLACEHOLDER,
            "schoolYear": SAFE_PLACEHOLDER,
        },
        "lessonInfo": {
            "subject": "",
            "grade": "",
            "lessonNumber": "",
            "lessonTitle": "",
            "textbookSeries": "Kết nối tri thức với cuộc sống",
            "duration": "",
            "week": SAFE_PLACEHOLDER,
            "period": SAFE_PLACEHOLDER,
            "teachingDate": "",
            "teacherName": SAFE_PLACEHOLDER,
            "sgkPages": SAFE_PLACEHOLDER,
        },
        "objectives": {
            "intro": "Sau bài học, học sinh đạt được các yêu cầu sau:",
            "specificCompetencies": [],
            "generalCompetencies": [],
            "qualities": [],
        },
        "teachingMaterials": {"teacher": [], "students": []},
        "teachingProcess": [],
        "differentiation": {
            "weakerStudents": "",
            "advancedStudents": "",
            "limitedResources": "",
        },
        "assessment": [],
        "worksheet": [],
    }
