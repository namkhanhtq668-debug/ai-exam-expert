# -*- coding: utf-8 -*-
"""
Module: lesson_docx
Tạo file DOCX Kế hoạch bài dạy (KHBD) cho tiểu học theo mẫu chuẩn 2026-2027.

Nguyên tắc kiến trúc:
    AI → JSON data thuần (chỉ nội dung)
        → validator (check schema + phrase cấm)
        → normalizer (chuẩn hoá text)
        → renderer (CODE 100% quyết định layout DOCX)

AI KHÔNG được quyết định bố cục Word. Code mới là nơi quyết định
mẫu giáo án, font chữ, bảng biểu, tiêu đề, căn lề và thứ tự các mục.
"""
