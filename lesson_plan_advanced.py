# -*- coding: utf-8 -*-
"""
Module: Soạn giáo án AI nâng cao (chuẩn CTGDPT 2018 + CV 2345/BGDĐT-GDTH)
Tích hợp vào AIEXAM.VN — gói PRO+

Tính năng chính:
- OCR ảnh trang SGK bằng Gemini Vision
- Đọc file PDF/DOCX/TXT giáo viên upload
- Tìm bài học khớp trong kho metadata SGK nội bộ
- Đánh giá độ tin cậy nguồn (4 mức)
- Sinh giáo án HTML đầy đủ 12 mục theo CV 2345
- Quality gate 15 tiêu chí
- Xuất Word .docx + HTML A4

Cách gọi từ app.py:
    from lesson_plan_advanced import module_lesson_plan_advanced
    module_lesson_plan_advanced(
        api_key=SYSTEM_GOOGLE_KEY,
        point_check=require_points_or_block,
        point_cost=35,
    )
"""

from __future__ import annotations

import datetime as dt
import difflib
import html
import io
import json
import os
import re
import textwrap
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

# Dependencies optional — module tự degrade nếu thiếu
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import mammoth
except Exception:
    mammoth = None

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.shared import Inches, Pt
except Exception:
    Document = None


# =============================================================================
# 1. Cấu hình
# =============================================================================

APP_VERSION = "2026.05-pro"
BOOK_SERIES_DEFAULT = "Kết nối tri thức với cuộc sống"
PUBLISHER = "Nhà xuất bản Giáo dục Việt Nam"
DEFAULT_MODEL = "gemini-2.0-flash"
APP_KEY = "lp_adv"

APPROVED_DOMAINS = [
    "hoclieuso.nxbgd.vn",
    "hanhtrangso.nxbgd.vn",
    "nxbgd.vn",
    "moet.gov.vn",
    "igiaoduc.vn",
    "taphuan.csdl.edu.vn",
]

BOOK_SERIES_OPTIONS = [
    "Kết nối tri thức với cuộc sống",
    "Cánh Diều",
    "Chân trời sáng tạo",
    "Khác / Tự nhập",
]

SUBJECTS_BY_LEVEL: Dict[str, Dict[str, Any]] = {
    "Tiểu học": {
        "grades": ["1", "2", "3", "4", "5"],
        "subjects": [
            "Tiếng Việt", "Toán", "Đạo đức", "Tự nhiên và Xã hội", "Khoa học",
            "Lịch sử và Địa lí", "Tin học", "Công nghệ", "Hoạt động trải nghiệm",
            "Mĩ thuật", "Âm nhạc", "Giáo dục thể chất", "Tiếng Anh",
        ],
        "default_duration": 35,
    },
    "THCS": {
        "grades": ["6", "7", "8", "9"],
        "subjects": [
            "Ngữ văn", "Toán", "Tiếng Anh", "Khoa học tự nhiên",
            "Lịch sử và Địa lí", "Tin học", "Công nghệ", "Giáo dục công dân",
            "Hoạt động trải nghiệm, hướng nghiệp", "Mĩ thuật", "Âm nhạc",
            "Giáo dục thể chất",
        ],
        "default_duration": 45,
    },
    "THPT": {
        "grades": ["10", "11", "12"],
        "subjects": [
            "Ngữ văn", "Toán", "Tiếng Anh", "Vật lí", "Hóa học", "Sinh học",
            "Lịch sử", "Địa lí", "Giáo dục kinh tế và pháp luật", "Tin học",
            "Công nghệ", "Hoạt động trải nghiệm, hướng nghiệp",
            "Giáo dục thể chất", "Giáo dục quốc phòng và an ninh",
        ],
        "default_duration": 45,
    },
}

DIGITAL_COMPETENCIES = [
    "Khai thác dữ liệu, thông tin và nội dung số",
    "Giao tiếp và hợp tác trong môi trường số",
    "Sáng tạo nội dung số",
    "An toàn số",
    "Giải quyết vấn đề trong môi trường số",
    "Sử dụng công cụ AI/học liệu số có trách nhiệm",
]

REQUIRED_SECTIONS = [
    "thông tin chung", "nguồn học liệu", "yêu cầu cần đạt",
    "năng lực", "phẩm chất", "năng lực số", "thiết bị",
    "tiến trình dạy học", "hoạt động của giáo viên",
    "hoạt động của học sinh", "đánh giá", "phân hóa",
    "phiếu học tập", "rubric", "điều chỉnh sau tiết dạy",
]

SAMPLE_LESSONS: List[Dict[str, Any]] = [
    {
        "lesson_id": "KNTT_TINHOC_5_TIM_KIEM_DEMO",
        "book_series": BOOK_SERIES_DEFAULT,
        "grade": "5",
        "subject": "Tin học",
        "unit_name": "Chủ đề C. Tổ chức lưu trữ, tìm kiếm và trao đổi thông tin",
        "lesson_title": "Tìm kiếm thông tin trên Internet",
        "alternate_titles": ["Tìm kiếm thông tin", "Từ khóa tìm kiếm"],
        "suggested_duration": 35,
        "keywords": ["Internet", "tìm kiếm", "từ khóa", "máy tìm kiếm", "an toàn"],
        "learning_objectives": [
            "Nêu được vai trò của từ khóa khi tìm kiếm thông tin trên Internet.",
            "Thực hiện được thao tác tìm kiếm thông tin đơn giản theo yêu cầu học tập.",
            "Biết lựa chọn kết quả phù hợp, đáng tin cậy và an toàn ở mức độ phù hợp với lứa tuổi.",
        ],
        "main_content_summary": "Học sinh nhận biết nhu cầu tìm kiếm thông tin, biết sử dụng từ khóa phù hợp, thực hành tìm kiếm thông tin học tập trên Internet và bước đầu đánh giá kết quả tìm kiếm.",
        "digital_competencies": [
            "Khai thác dữ liệu, thông tin và nội dung số",
            "An toàn số",
            "Giải quyết vấn đề trong môi trường số",
        ],
        "official_url": "https://hoclieuso.nxbgd.vn/",
        "source_status": "metadata_demo",
        "last_reviewed": "2026-05-18",
    },
    {
        "lesson_id": "KNTT_TOAN_5_ON_TAP_PHAN_SO_DEMO",
        "book_series": BOOK_SERIES_DEFAULT,
        "grade": "5",
        "subject": "Toán",
        "unit_name": "Ôn tập và bổ sung",
        "lesson_title": "Ôn tập về phân số",
        "alternate_titles": ["Phân số", "Ôn tập phân số"],
        "suggested_duration": 35,
        "keywords": ["phân số", "tử số", "mẫu số", "so sánh", "rút gọn"],
        "learning_objectives": [
            "Củng cố được khái niệm phân số, tử số, mẫu số.",
            "Thực hiện được một số thao tác cơ bản với phân số ở mức độ phù hợp.",
            "Vận dụng phân số để giải quyết tình huống đơn giản trong học tập và đời sống.",
        ],
        "main_content_summary": "Bài học giúp học sinh ôn tập kiến thức trọng tâm về phân số và luyện tập vận dụng.",
        "digital_competencies": [
            "Khai thác dữ liệu, thông tin và nội dung số",
            "Giải quyết vấn đề trong môi trường số",
        ],
        "official_url": "https://hoclieuso.nxbgd.vn/",
        "source_status": "metadata_demo",
        "last_reviewed": "2026-05-18",
    },
    {
        "lesson_id": "KNTT_TIENGVIET_5_DOC_MO_RONG_DEMO",
        "book_series": BOOK_SERIES_DEFAULT,
        "grade": "5",
        "subject": "Tiếng Việt",
        "unit_name": "Đọc - Viết - Nói và nghe",
        "lesson_title": "Đọc mở rộng",
        "alternate_titles": ["Bài đọc mở rộng", "Đọc sách báo"],
        "suggested_duration": 35,
        "keywords": ["đọc mở rộng", "chia sẻ bài đọc", "cảm nhận"],
        "learning_objectives": [
            "Đọc được văn bản phù hợp với lứa tuổi theo yêu cầu đọc mở rộng.",
            "Ghi lại được thông tin chính và cảm nhận ngắn về văn bản đã đọc.",
            "Chia sẻ được bài đọc với bạn bằng lời nói rõ ràng, tự tin.",
        ],
        "main_content_summary": "Học sinh đọc, ghi chép và chia sẻ văn bản đọc mở rộng theo định hướng của giáo viên.",
        "digital_competencies": [
            "Khai thác dữ liệu, thông tin và nội dung số",
            "Giao tiếp và hợp tác trong môi trường số",
            "An toàn số",
        ],
        "official_url": "https://hoclieuso.nxbgd.vn/",
        "source_status": "metadata_demo",
        "last_reviewed": "2026-05-18",
    },
]


@dataclass
class _SourceBundle:
    metadata_matches: List[Dict[str, Any]] = field(default_factory=list)
    uploaded_text: str = ""
    uploaded_text_notes: List[str] = field(default_factory=list)
    image_context: str = ""
    image_notes: List[str] = field(default_factory=list)
    link_context: str = ""
    link_notes: List[str] = field(default_factory=list)
    teacher_note: str = ""
    trust_level: str = "Trung bình"
    trust_explanation: str = "Chưa có nguồn SGK xác thực trực tiếp."


# =============================================================================
# 2. Tiện ích
# =============================================================================

def _k(name: str) -> str:
    return f"{APP_KEY}_{name}"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().strip()
    text = re.sub(r"[​‌‍﻿]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _slugify(text: str, max_len: int = 90) -> str:
    text = _norm(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "d")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:max_len] or "giao_an"


def _safe_json_dumps(data: Any, max_chars: int = 12000) -> str:
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    if len(raw) > max_chars:
        return raw[:max_chars] + "\n... [đã rút gọn]"
    return raw


def _get_metadata_dir() -> Path:
    val = ""
    try:
        val = st.secrets.get("SGK_DATA_DIR", "")
    except Exception:
        val = ""
    return Path(os.getenv("SGK_DATA_DIR") or val or "data_sgk_ket_noi")


def _ensure_sample_metadata() -> None:
    d = _get_metadata_dir()
    d.mkdir(parents=True, exist_ok=True)
    sample = d / "lessons_sample_demo.json"
    if not sample.exists():
        sample.write_text(
            json.dumps(SAMPLE_LESSONS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _load_metadata() -> List[Dict[str, Any]]:
    _ensure_sample_metadata()
    lessons: List[Dict[str, Any]] = []
    for file in _get_metadata_dir().rglob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else (data.get("lessons") if isinstance(data, dict) else None)
            if items is None and isinstance(data, dict) and data.get("lesson_title"):
                items = [data]
            for item in items or []:
                if isinstance(item, dict) and item.get("lesson_title"):
                    item["_metadata_file"] = str(file)
                    lessons.append(item)
        except Exception:
            continue
    seen, unique = set(), []
    for item in lessons:
        key = item.get("lesson_id") or f"{item.get('grade')}|{item.get('subject')}|{item.get('lesson_title')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _score_match(lesson: Dict[str, Any], grade: str, subject: str, title: str) -> float:
    score = 0.0
    t_title = _norm(title)
    l_grade = str(lesson.get("grade", "")).strip()
    l_subj = _norm(str(lesson.get("subject", "")))
    t_subj = _norm(subject)

    if l_grade == str(grade).strip():
        score += 25
    elif l_grade:
        score -= 15

    if l_subj == t_subj:
        score += 25
    elif t_subj in l_subj or l_subj in t_subj:
        score += 15
    elif l_subj:
        score -= 10

    titles = [str(lesson.get("lesson_title", ""))] + [str(x) for x in lesson.get("alternate_titles", [])]
    best = 0.0
    for nt in titles:
        nt_n = _norm(nt)
        if not nt_n:
            continue
        r = difflib.SequenceMatcher(None, t_title, nt_n).ratio() * 35
        if t_title and t_title in nt_n:
            r += 15
        if nt_n and nt_n in t_title:
            r += 10
        best = max(best, r)
    score += best

    kw_hits = sum(1 for kw in lesson.get("keywords", []) if _norm(str(kw)) and _norm(str(kw)) in t_title)
    score += min(kw_hits * 5, 15)
    return max(0, min(score, 100))


def _search_metadata(grade: str, subject: str, title: str, limit: int = 5) -> List[Dict[str, Any]]:
    out = []
    for lesson in _load_metadata():
        s = _score_match(lesson, grade, subject, title)
        if s >= 25:
            item = dict(lesson)
            item["_match_score"] = round(s, 1)
            out.append((s, item))
    out.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in out[:limit]]


# =============================================================================
# 3. Đọc nguồn xác thực
# =============================================================================

def _extract_text_from_uploads(files) -> Tuple[str, List[str]]:
    if not files:
        return "", []
    all_text, notes = [], []
    for f in files:
        name = getattr(f, "name", "file")
        ext = Path(name).suffix.lower().strip(".")
        raw = f.getvalue()
        text = ""
        try:
            if ext == "txt":
                text = raw.decode("utf-8", errors="ignore")
            elif ext == "pdf":
                if PdfReader is None:
                    notes.append(f"{name}: cần cài pypdf (pip install pypdf).")
                else:
                    reader = PdfReader(io.BytesIO(raw))
                    pages = []
                    for i, p in enumerate(reader.pages[:20], 1):
                        try:
                            pages.append(f"[Trang {i}]\n{p.extract_text() or ''}")
                        except Exception:
                            pages.append(f"[Trang {i}] Không trích được.")
                    text = "\n\n".join(pages)
            elif ext in {"docx", "doc"}:
                if mammoth is not None:
                    text = mammoth.extract_raw_text(io.BytesIO(raw)).value or ""
                elif Document is not None and ext == "docx":
                    doc = Document(io.BytesIO(raw))
                    text = "\n".join(p.text for p in doc.paragraphs)
                else:
                    notes.append(f"{name}: cần cài mammoth hoặc python-docx.")
            else:
                notes.append(f"{name}: định dạng chưa hỗ trợ.")
        except Exception as e:
            notes.append(f"{name}: lỗi khi đọc - {e}")
        text = (text or "").strip()
        if text:
            all_text.append(f"\n--- FILE: {name} ---\n{text[:12000]}")
            notes.append(f"{name}: đã trích {len(text)} ký tự.")
        else:
            notes.append(f"{name}: không có text. Nếu là ảnh scan, hãy upload sang ô ảnh trang SGK.")
    return "\n\n".join(all_text)[:30000], notes


def _call_gemini_text(api_key: str, prompt: str, model_name: str = DEFAULT_MODEL, temperature: float = 0.25) -> str:
    try:
        import google.generativeai as genai
    except Exception as e:
        raise RuntimeError("Chưa cài google-generativeai. Chạy: pip install google-generativeai") from e
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": temperature, "top_p": 0.9, "max_output_tokens": 12000},
    )
    return getattr(resp, "text", "") or ""


def _extract_image_context(image_files, api_key: str, model_name: str) -> Tuple[str, List[str]]:
    if not image_files:
        return "", []
    if not api_key:
        return "", ["Có ảnh nhưng chưa có API key nên chưa OCR được."]
    if Image is None:
        return "", ["Chưa cài Pillow (pip install pillow)."]
    try:
        import google.generativeai as genai
    except Exception:
        return "", ["Chưa cài google-generativeai."]

    notes, pil_imgs = [], []
    for f in image_files[:8]:
        try:
            img = Image.open(io.BytesIO(f.getvalue()))
            pil_imgs.append(img)
            notes.append(f"{getattr(f, 'name', 'ảnh')}: nhận ảnh {img.size[0]}x{img.size[1]}.")
        except Exception as e:
            notes.append(f"{getattr(f, 'name', 'ảnh')}: lỗi - {e}")
    if not pil_imgs:
        return "", notes

    prompt = textwrap.dedent(f"""
        Bạn là trợ lý giáo dục Việt Nam. Hãy đọc các ảnh trang SGK/học liệu giáo viên cung cấp.
        Yêu cầu:
        1. Trích xuất tên bài, mục/chủ đề, nội dung chính, câu hỏi/bài tập, yêu cầu cần đạt nếu có.
        2. Không bịa nội dung không nhìn thấy trong ảnh.
        3. Nếu ảnh mờ/thiếu trang, ghi rõ phần chưa chắc chắn.
        4. Tóm tắt ngắn gọn để dùng làm căn cứ soạn giáo án theo bộ sách {BOOK_SERIES_DEFAULT}.
        Trả lời bằng tiếng Việt, dạng gạch đầu dòng rõ ràng.
    """).strip()
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content([prompt, *pil_imgs])
        text = getattr(resp, "text", "") or ""
        notes.append("Đã OCR ảnh bằng AI." if text.strip() else "AI không trả về nội dung.")
        return text[:20000], notes
    except Exception as e:
        notes.append(f"Lỗi khi OCR ảnh: {e}")
        return "", notes


def _is_approved_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return any(d in u for d in APPROVED_DOMAINS)


def _fetch_official_links(links_text: str, timeout: int = 12) -> Tuple[str, List[str]]:
    links = re.findall(r"https?://[^\s,;]+", links_text or "")
    if not links:
        return "", []
    if BeautifulSoup is None:
        return "", ["Chưa cài beautifulsoup4 nên chưa đọc link được."]
    ctxs, notes = [], []
    for url in links[:5]:
        if not _is_approved_url(url):
            notes.append(f"Bỏ qua link ngoài danh sách duyệt: {url}")
            continue
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 aiexam-lesson-plan-advanced",
                    "Accept-Language": "vi,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ctype = r.headers.get("content-type", "")
                if "text/html" not in ctype and "application/xhtml" not in ctype:
                    notes.append(f"{url}: không phải HTML ({ctype}).")
                    continue
                raw = r.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
            text = re.sub(r"[ \t]{2,}", " ", text).strip()
            if len(_norm(text)) < 120:
                notes.append(f"{url}: trang dạng động, chưa lấy được nội dung.")
            else:
                ctxs.append(f"\n--- LINK: {url} ---\n{text[:8000]}")
                notes.append(f"{url}: đã lấy {min(len(text), 8000)} ký tự.")
        except Exception as e:
            notes.append(f"{url}: lỗi - {e}")
    return "\n\n".join(ctxs)[:20000], notes


def _determine_trust(b: _SourceBundle) -> _SourceBundle:
    has_upload = bool(b.uploaded_text.strip() or b.image_context.strip())
    has_good_meta = bool(b.metadata_matches and b.metadata_matches[0].get("_match_score", 0) >= 70)
    has_meta = bool(b.metadata_matches)
    has_link = bool(b.link_context.strip())

    if has_upload and has_good_meta:
        b.trust_level = "Rất cao"
        b.trust_explanation = "Có ảnh/file giáo viên cung cấp và bài khớp tốt trong kho metadata."
    elif has_upload:
        b.trust_level = "Rất cao"
        b.trust_explanation = "Có ảnh/file bài học do giáo viên cung cấp."
    elif has_good_meta:
        b.trust_level = "Cao"
        b.trust_explanation = "Tìm thấy bài khớp tốt trong kho metadata SGK."
    elif has_link and has_meta:
        b.trust_level = "Cao"
        b.trust_explanation = "Có dữ liệu link chính thống và bài khớp metadata."
    elif has_meta:
        b.trust_level = "Trung bình"
        b.trust_explanation = "Có bài tương đối khớp trong metadata, cần giáo viên kiểm tra lại."
    elif has_link:
        b.trust_level = "Trung bình"
        b.trust_explanation = "Có dữ liệu từ link chính thống, chưa khớp metadata."
    else:
        b.trust_level = "Thấp"
        b.trust_explanation = "Chưa có nguồn SGK xác thực. AI tạo bản nháp theo khung, giáo viên cần rà soát."
    return b


# =============================================================================
# 4. Prompt + Sinh HTML
# =============================================================================

def _build_prompt(*, school, teacher, school_year, teaching_date, level, grade, class_name,
                  subject, book_series, lesson_title, duration, period_note, digital_level,
                  diff_level, bundle: _SourceBundle) -> str:
    meta_json = _safe_json_dumps(bundle.metadata_matches[:3], 15000)
    return textwrap.dedent(f"""
Bạn là chuyên gia giáo dục Việt Nam, chuyên thiết kế giáo án theo định hướng phát triển phẩm chất, năng lực, tích hợp năng lực số.
Hãy soạn GIÁO ÁN HOÀN CHỈNH bằng tiếng Việt, dùng ngay được cho giáo viên.

# NGUYÊN TẮC BẮT BUỘC
1. Không bịa nội dung SGK. Chỉ khẳng định nội dung bài khi có căn cứ từ metadata, ảnh/file giáo viên hoặc link chính thống.
2. Nếu thiếu nguồn xác thực, vẫn tạo giáo án theo khung chuẩn nhưng ghi rõ ở mục "Nguồn học liệu và mức tin cậy": giáo án cần giáo viên kiểm tra lại nội dung trong SGK.
3. Không trích nguyên văn SGK. Chỉ tóm tắt nội dung cần thiết.
4. Giáo án phải thực tế, giáo viên có thể tải Word và chỉnh sửa dùng ngay.
5. Tích hợp năng lực số phải tự nhiên, đúng hoạt động, không hình thức.
6. Tổng thời gian các hoạt động phải xấp xỉ {duration} phút.
7. Trả về HTML sạch, KHÔNG dùng markdown, KHÔNG bọc ```html.

# THÔNG TIN BÀI DẠY
- Trường: {school or "Chưa nhập"}
- Giáo viên: {teacher or "Chưa nhập"}
- Năm học: {school_year}
- Ngày dạy: {teaching_date.strftime('%d/%m/%Y')}
- Cấp học: {level}
- Lớp: {class_name or grade}
- Môn học: {subject}
- Bộ sách: {book_series}
- NXB: {PUBLISHER}
- Tên bài học: {lesson_title}
- Thời lượng: {duration} phút
- Tuần/tiết/PPCT: {period_note or "Không bắt buộc"}
- Mức tích hợp năng lực số: {digital_level}
- Mức phân hóa: {diff_level}
- Mức tin cậy nguồn: {bundle.trust_level} - {bundle.trust_explanation}

# NGUỒN 1 - METADATA SGK
{meta_json if meta_json.strip() else "Không có metadata khớp."}

# NGUỒN 2 - FILE GIÁO VIÊN
{bundle.uploaded_text[:18000] if bundle.uploaded_text.strip() else "Không có."}

# NGUỒN 3 - ẢNH TRANG SÁCH (AI ĐỌC)
{bundle.image_context[:15000] if bundle.image_context.strip() else "Không có."}

# NGUỒN 4 - LINK CHÍNH THỐNG
{bundle.link_context[:12000] if bundle.link_context.strip() else "Không có."}

# GHI CHÚ GIÁO VIÊN
{bundle.teacher_note or "Không có."}

# KHUNG GIÁO ÁN BẮT BUỘC
Tạo HTML có cấu trúc:
<article class="lesson-plan">
  <h1>GIÁO ÁN ...</h1>
  <section><h2>I. Thông tin chung</h2>Bảng thông tin bài dạy.</section>
  <section><h2>II. Nguồn học liệu và mức tin cậy</h2>Nêu rõ dùng nguồn nào. Cảnh báo nếu thiếu nguồn xác thực.</section>
  <section><h2>III. Yêu cầu cần đạt</h2>Chia kiến thức, kĩ năng, vận dụng. Cụ thể, đo được.</section>
  <section><h2>IV. Năng lực và phẩm chất</h2>Năng lực chung, năng lực đặc thù, phẩm chất.</section>
  <section><h2>V. Tích hợp năng lực số</h2>Chọn từ: {', '.join(DIGITAL_COMPETENCIES)}.</section>
  <section><h2>VI. Thiết bị, học liệu và chuẩn bị</h2>Có chuẩn bị của GV và HS.</section>
  <section><h2>VII. Tiến trình dạy học</h2>Bảng gồm: Hoạt động, Thời gian, Mục tiêu, Hoạt động của giáo viên, Hoạt động của học sinh, Sản phẩm, Đánh giá. Bắt buộc: Khởi động, Hình thành kiến thức, Luyện tập, Vận dụng, Củng cố.</section>
  <section><h2>VIII. Phân hóa và hỗ trợ học sinh</h2>Có HS cần hỗ trợ, HS hoàn thành tốt, điều chỉnh lớp đông/thiếu thiết bị.</section>
  <section><h2>IX. Đánh giá thường xuyên</h2>Tiêu chí, minh chứng, câu hỏi kiểm tra nhanh.</section>
  <section><h2>X. Phiếu học tập</h2>Tạo phiếu dùng được ngay.</section>
  <section><h2>XI. Rubric đánh giá</h2>Bảng 3-4 mức độ.</section>
  <section><h2>XII. Điều chỉnh sau tiết dạy</h2>Chừa dòng để GV ghi.</section>
</article>

# ĐỊNH DẠNG
- HTML rõ, có bảng, có tiêu đề, tiếng Việt chuẩn.
- Không nói "tôi là AI", không xin lỗi.
- Không có nội dung ngoài thẻ article.
    """).strip()


def _clean_html(raw: str) -> str:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:html)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"<article[\s\S]*?</article>", raw, flags=re.IGNORECASE)
    if m:
        raw = m.group(0)
    if "<article" not in raw.lower():
        raw = f"<article class='lesson-plan'><h1>GIÁO ÁN</h1><p>{html.escape(raw)}</p></article>"
    return raw.strip()


def _wrap_a4(content_html: str, title: str = "GiaoAn") -> str:
    css = """
    <style>
      * { box-sizing: border-box; }
      body { margin:0; background:#eef2f7; color:#111827; font-family:"Times New Roman",Times,serif; }
      .page { width:210mm; min-height:297mm; margin:18px auto; background:#fff; padding:18mm 16mm; box-shadow:0 10px 28px rgba(15,23,42,.16); }
      article.lesson-plan { font-size:13.5pt; line-height:1.35; }
      h1 { text-align:center; font-size:18pt; margin:0 0 12px; text-transform:uppercase; color:#0f172a; }
      h2 { font-size:14.5pt; margin:14px 0 8px; color:#0f172a; border-left:5px solid #174ea6; padding-left:8px; }
      h3 { font-size:13.8pt; margin:10px 0 6px; }
      p { margin:5px 0; }
      ul, ol { margin:6px 0 6px 24px; }
      table { width:100%; border-collapse:collapse; margin:8px 0 12px; }
      th, td { border:1px solid #4b5563; padding:6px 7px; vertical-align:top; }
      th { background:#eef4ff; text-align:center; font-weight:700; }
      .source-warning { background:#fff7ed; border:1px solid #fed7aa; padding:8px; border-radius:8px; }
      @media print { body { background:#fff; } .page { margin:0; box-shadow:none; width:auto; min-height:auto; } }
    </style>
    """
    return f"<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>{html.escape(title)}</title>{css}</head><body><div class='page'>{content_html}</div></body></html>"


def _create_docx(full_html: str) -> bytes:
    if Document is None or BeautifulSoup is None:
        raise RuntimeError("Cần cài python-docx và beautifulsoup4.")
    soup = BeautifulSoup(full_html, "html.parser")
    page = soup.find("article") or soup.find("div", class_="page") or soup.body or soup
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(0.65); sec.bottom_margin = Inches(0.65)
    sec.left_margin = Inches(0.7); sec.right_margin = Inches(0.7)
    doc.styles["Normal"].font.name = "Times New Roman"
    doc.styles["Normal"].font.size = Pt(13)

    def add_p(text: str, bold: bool = False, align=None):
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            return
        p = doc.add_paragraph()
        if align is not None:
            p.alignment = align
        run = p.add_run(text)
        run.bold = bold
        run.font.name = "Times New Roman"
        run.font.size = Pt(13)

    def handle_table(t):
        rows = t.find_all("tr")
        if not rows:
            return
        max_cols = max(len(r.find_all(["th", "td"])) for r in rows)
        if max_cols == 0:
            return
        tbl = doc.add_table(rows=len(rows), cols=max_cols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.style = "Table Grid"
        for i, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            for j in range(max_cols):
                c = tbl.cell(i, j)
                c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                c.text = cells[j].get_text(" ", strip=True) if j < len(cells) else ""
                for p in c.paragraphs:
                    for run in p.runs:
                        run.font.name = "Times New Roman"
                        run.font.size = Pt(12)
                        if j < len(cells) and cells[j].name == "th":
                            run.bold = True
        doc.add_paragraph()

    for node in page.descendants:
        if getattr(node, "name", None) is None:
            continue
        if node.find_parent("table") and node.name != "table":
            continue
        if node.name == "h1":
            add_p(node.get_text(" ", strip=True), bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif node.name in {"h2", "h3"}:
            add_p(node.get_text(" ", strip=True), bold=True)
        elif node.name == "p":
            add_p(node.get_text(" ", strip=True))
        elif node.name in {"ul", "ol"}:
            for li in node.find_all("li", recursive=False):
                add_p("• " + li.get_text(" ", strip=True))
        elif node.name == "table":
            handle_table(node)

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


def _validate(content_html: str, lesson_title: str, trust_level: str) -> Dict[str, Any]:
    if BeautifulSoup:
        text = _norm(BeautifulSoup(content_html, "html.parser").get_text(" "))
    else:
        text = _norm(re.sub(r"<[^>]+>", " ", content_html))
    checks = []
    for s in REQUIRED_SECTIONS:
        ok = _norm(s) in text
        checks.append((s, ok, "Có" if ok else "Thiếu"))
    title_ok = _norm(lesson_title)[:20] in text if lesson_title else True
    checks.append(("Tên bài học xuất hiện", title_ok, "Có" if title_ok else "Cần kiểm tra"))
    warn_ok = trust_level != "Thấp" or ("cần giáo viên kiểm tra" in text or "chưa có nguồn" in text)
    checks.append(("Cảnh báo khi thiếu nguồn", warn_ok, "Có" if warn_ok else "Thiếu"))
    ok_count = sum(1 for _, ok, _ in checks if ok)
    score = round(ok_count / len(checks) * 100)
    level = "Tốt" if score >= 90 else "Khá" if score >= 75 else "Cần rà soát" if score >= 60 else "Chưa đạt"
    return {"score": score, "level": level, "checks": checks}


# =============================================================================
# 5. UI
# =============================================================================

def _render_source_status(b: _SourceBundle) -> None:
    color = {"Rất cao": "#16a34a", "Cao": "#2563eb", "Trung bình": "#d97706", "Thấp": "#dc2626"}.get(b.trust_level, "#6b7280")
    st.markdown(
        f"""<div style="border:1px solid #e5e7eb;border-radius:12px;padding:12px;background:#fff;margin:8px 0;">
        <div style="font-weight:800;color:{color};">Mức tin cậy nguồn: {html.escape(b.trust_level)}</div>
        <div style="margin-top:4px;color:#374151;">{html.escape(b.trust_explanation)}</div></div>""",
        unsafe_allow_html=True,
    )
    if b.metadata_matches:
        st.markdown("**Bài khớp trong kho metadata:**")
        for it in b.metadata_matches[:3]:
            st.write(f"- {it.get('subject')} lớp {it.get('grade')} — **{it.get('lesson_title')}** (khớp: {it.get('_match_score')}%)")
    else:
        st.info("Chưa tìm thấy bài khớp trong kho metadata.")
    with st.expander("Nhật ký nguồn dữ liệu", expanded=False):
        for n in b.uploaded_text_notes + b.image_notes + b.link_notes:
            st.write("- " + n)


def module_lesson_plan_advanced(
    *,
    api_key: str = "",
    point_check: Optional[Callable[[int, str], bool]] = None,
    point_cost: int = 35,
    model_name: str = DEFAULT_MODEL,
) -> None:
    """Module soạn giáo án AI nâng cao — chỉ Pro/Admin được vào.
    Caller phải tự kiểm tra role trước khi gọi.
    """
    # Header
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#0F172A 0%,#1D4ED8 58%,#60A5FA 100%);
        border-radius:16px;padding:18px 20px;color:#fff;margin-bottom:14px;
        box-shadow:0 10px 24px rgba(2,6,23,.18);">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <h2 style="margin:0;font-weight:800;">✨ Soạn giáo án AI nâng cao</h2>
          <span style="background:#fbbf24;color:#0f172a;font-weight:800;padding:4px 10px;border-radius:999px;font-size:12px;">PRO+</span>
        </div>
        <div style="opacity:.94;margin-top:6px;line-height:1.45;">
          OCR ảnh trang SGK • Đánh giá độ tin cậy nguồn • Chuẩn CTGDPT 2018 + CV 2345/BGDĐT-GDTH
        </div>
        <div style="opacity:.8;margin-top:6px;font-size:13px;">Phiên bản: {APP_VERSION} • Phí: {point_cost} điểm/lượt</div></div>""",
        unsafe_allow_html=True,
    )

    with st.expander("ℹ️ Hướng dẫn dùng nhanh", expanded=False):
        st.markdown("""
        1. Nhập ngày dạy, lớp, môn, tên bài, thời lượng.
        2. (Khuyến khích) Upload ảnh trang SGK hoặc file bài học để AI bám đúng nội dung.
        3. Nếu không có, hệ thống tìm trong kho metadata `data_sgk_ket_noi/`.
        4. Bấm **Tạo giáo án bằng AI** (trừ điểm) hoặc **Tạo bản demo** (miễn phí, để xem cấu trúc).
        5. Tải Word/HTML về dùng ngay.
        """)

    current_year = dt.date.today().year
    school_years = [f"{y}-{y+1}" for y in range(current_year - 1, current_year + 3)]

    with st.form(key=_k("form"), clear_on_submit=False):
        st.markdown("### 1) Thông tin bài dạy")
        c1, c2, c3 = st.columns([1.2, 1.1, 1.1])
        with c1:
            school = st.text_input("Tên trường (tùy chọn)", key=_k("school"))
        with c2:
            teacher = st.text_input("Giáo viên (tùy chọn)", key=_k("teacher"))
        with c3:
            school_year = st.selectbox("Năm học", school_years, index=min(1, len(school_years) - 1), key=_k("year"))

        c1, c2, c3, c4 = st.columns([1.1, 1.0, 1.0, 1.25])
        with c1:
            teaching_date = st.date_input("Ngày dạy", value=dt.date.today(), key=_k("date"))
        with c2:
            level = st.selectbox("Cấp học", list(SUBJECTS_BY_LEVEL.keys()), key=_k("level"))
        with c3:
            grade = st.selectbox("Lớp", SUBJECTS_BY_LEVEL[level]["grades"], key=_k("grade"))
        with c4:
            subject = st.selectbox("Môn học", SUBJECTS_BY_LEVEL[level]["subjects"], key=_k("subject"))

        c1, c2, c3 = st.columns([1.2, 2.2, 1.0])
        with c1:
            class_name = st.text_input("Lớp cụ thể", placeholder="VD: 5A", key=_k("class"))
        with c2:
            lesson_title = st.text_input("Tên bài học", placeholder="VD: Tìm kiếm thông tin trên Internet", key=_k("title"))
        with c3:
            duration = st.number_input("Thời lượng (phút)", min_value=20, max_value=120,
                                       value=int(SUBJECTS_BY_LEVEL[level]["default_duration"]), step=5, key=_k("duration"))

        c1, c2 = st.columns([1.0, 1.0])
        with c1:
            book_series = st.selectbox("Bộ sách", BOOK_SERIES_OPTIONS, key=_k("book"))
        with c2:
            period_note = st.text_input("Tuần/tiết/PPCT (tùy chọn)", placeholder="VD: Tuần 12 - Tiết 23", key=_k("period"))

        st.markdown("### 2) Nguồn học liệu")
        s1, s2 = st.columns([1.0, 1.0])
        with s1:
            use_metadata = st.checkbox("Tự tìm trong kho metadata SGK", value=True, key=_k("use_meta"))
            uploaded_files = st.file_uploader("Upload file bài học (PDF/DOCX/TXT)",
                                              type=["pdf", "docx", "doc", "txt"],
                                              accept_multiple_files=True, key=_k("files"))
        with s2:
            image_files = st.file_uploader("Upload/chụp ảnh trang SGK (JPG/PNG/WEBP)",
                                           type=["jpg", "jpeg", "png", "webp"],
                                           accept_multiple_files=True, key=_k("images"))
            official_links = st.text_area("Link SGK/học liệu chính thống",
                                          placeholder="VD: https://hoclieuso.nxbgd.vn/...",
                                          height=90, key=_k("links"))

        st.markdown("### 3) Tùy chỉnh chuyên môn")
        c1, c2 = st.columns([1.0, 1.0])
        with c1:
            digital_level = st.selectbox("Mức tích hợp năng lực số",
                                         ["Vừa đủ, tự nhiên", "Tăng cường hoạt động số", "Tối giản"], key=_k("dlevel"))
        with c2:
            diff_level = st.selectbox("Mức phân hóa",
                                      ["Cơ bản", "Chi tiết theo 3 nhóm", "Lớp đông/thiếu thiết bị"], key=_k("diff"))
        teacher_note = st.text_area("Ghi chú riêng của giáo viên",
                                    placeholder="VD: lớp có nhiều HS yếu; cần thêm trò chơi khởi động; không có phòng máy...",
                                    height=80, key=_k("note"))

        st.markdown("### 4) Tạo giáo án")
        c1, c2, c3 = st.columns([1.2, 1.2, 1.0])
        with c1:
            submit_ai = st.form_submit_button(f"⚡ Tạo giáo án bằng AI (-{point_cost} điểm)", type="primary", use_container_width=True)
        with c2:
            submit_demo = st.form_submit_button("🧪 Tạo bản demo (miễn phí)", use_container_width=True)
        with c3:
            reset = st.form_submit_button("🧹 Xóa kết quả", use_container_width=True)

    if reset:
        for key in [_k("html_content"), _k("full_html"), _k("title_slug"), _k("validation")]:
            st.session_state.pop(key, None)
        st.success("Đã xóa kết quả.")
        return

    if submit_ai or submit_demo:
        if not lesson_title.strip():
            st.error("Vui lòng nhập tên bài học.")
            st.stop()

        # Kiểm tra điểm trước khi gọi AI
        if submit_ai and point_check is not None:
            if not point_check(point_cost, "soạn giáo án AI nâng cao"):
                st.stop()

        with st.spinner("Đang đọc nguồn học liệu và xác định bài học..."):
            meta = _search_metadata(grade, subject, lesson_title) if use_metadata else []
            upl_text, upl_notes = _extract_text_from_uploads(uploaded_files)
            link_text, link_notes = _fetch_official_links(official_links)
            img_text, img_notes = ("", [])
            if image_files:
                img_text, img_notes = _extract_image_context(image_files, api_key, model_name)

            bundle = _SourceBundle(
                metadata_matches=meta,
                uploaded_text=upl_text,
                uploaded_text_notes=upl_notes,
                image_context=img_text,
                image_notes=img_notes,
                link_context=link_text,
                link_notes=link_notes,
                teacher_note=teacher_note,
            )
            bundle = _determine_trust(bundle)

        _render_source_status(bundle)

        title_slug = f"GiaoAn_{_slugify(subject)}_lop_{_slugify(grade)}_{_slugify(lesson_title)}"

        if submit_ai:
            if not api_key:
                st.error("Chưa có Gemini API key. Bạn có thể bấm 'Tạo bản demo' để xem cấu trúc.")
                st.stop()
            prompt = _build_prompt(
                school=school, teacher=teacher, school_year=school_year,
                teaching_date=teaching_date, level=level, grade=grade, class_name=class_name,
                subject=subject, book_series=book_series, lesson_title=lesson_title.strip(),
                duration=int(duration), period_note=period_note, digital_level=digital_level,
                diff_level=diff_level, bundle=bundle,
            )
            with st.spinner("AI đang soạn giáo án..."):
                try:
                    raw = _call_gemini_text(api_key, prompt, model_name=model_name, temperature=0.22)
                    content_html = _clean_html(raw)
                except Exception as e:
                    st.error(f"Lỗi khi gọi AI: {e}")
                    st.stop()
        else:
            content_html = _demo_html(
                school=school, teacher=teacher, school_year=school_year,
                teaching_date=teaching_date, level=level, grade=grade, class_name=class_name,
                subject=subject, book_series=book_series, lesson_title=lesson_title.strip(),
                duration=int(duration), bundle=bundle,
            )

        full_html = _wrap_a4(content_html, title_slug)
        validation = _validate(content_html, lesson_title.strip(), bundle.trust_level)

        st.session_state[_k("html_content")] = content_html
        st.session_state[_k("full_html")] = full_html
        st.session_state[_k("title_slug")] = title_slug
        st.session_state[_k("validation")] = json.dumps(validation, ensure_ascii=False)
        st.success("✅ Đã tạo giáo án. Kiểm tra bên dưới.")

    full_html = st.session_state.get(_k("full_html"), "")
    content_html = st.session_state.get(_k("html_content"), "")
    title_slug = st.session_state.get(_k("title_slug"), "GiaoAn")

    if full_html and content_html:
        st.markdown("## ✅ Kiểm định chất lượng")
        validation = json.loads(st.session_state.get(_k("validation"), "{}") or "{}")
        v1, v2 = st.columns(2)
        with v1:
            st.metric("Điểm kiểm định", f"{validation.get('score', 0)}/100")
        with v2:
            st.metric("Mức đánh giá", validation.get("level", "—"))
        with st.expander("Xem chi tiết tiêu chí", expanded=False):
            for name, ok, note in validation.get("checks", []):
                st.write(("✅" if ok else "⚠️") + f" {name}: {note}")

        st.markdown("## 📄 Xem trước giáo án (A4)")
        components.html(full_html, height=820, scrolling=True)

        st.markdown("## ⬇️ Tải giáo án")
        d1, d2 = st.columns(2)
        with d1:
            try:
                docx_bytes = _create_docx(full_html)
                st.download_button("Tải Word .docx", data=docx_bytes,
                                   file_name=f"{title_slug}.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   type="primary", use_container_width=True, key=_k("dl_docx"))
            except Exception as e:
                st.warning(f"Chưa xuất được DOCX: {e}")
        with d2:
            st.download_button("Tải HTML", data=full_html.encode("utf-8"),
                               file_name=f"{title_slug}.html", mime="text/html",
                               use_container_width=True, key=_k("dl_html"))

        with st.expander("Xem HTML giáo án (kỹ thuật)", expanded=False):
            st.code(content_html, language="html")


def _demo_html(*, school, teacher, school_year, teaching_date, level, grade, class_name,
               subject, book_series, lesson_title, duration, bundle: _SourceBundle) -> str:
    best = bundle.metadata_matches[0] if bundle.metadata_matches else {}
    objs = best.get("learning_objectives") or [
        "Nhận biết được nội dung trọng tâm của bài học.",
        "Thực hiện được nhiệm vụ học tập phù hợp.",
        "Vận dụng kiến thức/kĩ năng vào tình huống đơn giản.",
    ]
    comps = best.get("digital_competencies") or DIGITAL_COMPETENCIES[:2]
    summary = best.get("main_content_summary") or "Chưa có tóm tắt; giáo viên cần kiểm tra nội dung trong SGK."

    times = [5, max(8, duration // 3), max(8, duration // 3), 7, max(3, duration - (5 + max(8, duration // 3) * 2 + 7))]
    acts = [
        ("Khởi động", times[0], "Tạo tình huống gắn bài học", "Nêu câu hỏi/tình huống", "Chia sẻ nhanh", "Câu trả lời ban đầu", "Quan sát, nhận xét"),
        ("Hình thành kiến thức", times[1], "Khám phá nội dung chính", f"Tổ chức HS tìm hiểu: {html.escape(summary[:200])}", "Đọc/quan sát/thảo luận", "Bảng ý chính", "Câu hỏi gợi mở"),
        ("Luyện tập", times[2], "Củng cố kiến thức", "Giao nhiệm vụ luyện tập theo mức độ", "Làm cá nhân/cặp đôi", "Sản phẩm luyện tập", "Đánh giá theo tiêu chí"),
        ("Vận dụng", times[3], "Vận dụng thực tế", "Đưa tình huống gần gũi", "Trao đổi, trình bày", "Cách giải quyết", "Nhận xét, bổ sung"),
        ("Củng cố - dặn dò", times[4], "Khái quát bài học", "Chốt kiến thức; giao nhiệm vụ chuẩn bị bài sau", "Nêu điều học được", "Phiếu tự đánh giá", "Tự đánh giá"),
    ]
    rows = "".join(
        f"<tr><td>{a}</td><td style='text-align:center'>{t} phút</td><td>{m}</td><td>{gv}</td><td>{hs}</td><td>{sp}</td><td>{dg}</td></tr>"
        for a, t, m, gv, hs, sp, dg in acts
    )
    obj_html = "".join(f"<li>{html.escape(x)}</li>" for x in objs)
    comp_html = "".join(f"<li>{html.escape(x)}</li>" for x in comps)

    return f"""
<article class="lesson-plan">
  <h1>GIÁO ÁN {html.escape(subject).upper()}</h1>
  <section><h2>I. Thông tin chung</h2>
    <table>
      <tr><th>Trường</th><td>{html.escape(school or 'Chưa nhập')}</td><th>Giáo viên</th><td>{html.escape(teacher or 'Chưa nhập')}</td></tr>
      <tr><th>Năm học</th><td>{html.escape(school_year)}</td><th>Ngày dạy</th><td>{teaching_date.strftime('%d/%m/%Y')}</td></tr>
      <tr><th>Cấp học</th><td>{html.escape(level)}</td><th>Lớp</th><td>{html.escape(class_name or grade)}</td></tr>
      <tr><th>Môn học</th><td>{html.escape(subject)}</td><th>Thời lượng</th><td>{duration} phút</td></tr>
      <tr><th>Bài học</th><td colspan="3"><strong>{html.escape(lesson_title)}</strong></td></tr>
      <tr><th>Bộ sách</th><td colspan="3">{html.escape(book_series)} — {PUBLISHER}</td></tr>
    </table>
  </section>
  <section><h2>II. Nguồn học liệu và mức tin cậy</h2>
    <p><strong>Mức tin cậy:</strong> {html.escape(bundle.trust_level)}. {html.escape(bundle.trust_explanation)}</p>
    <p class="source-warning">Bản này là bản demo không dùng AI. Khi tạo bằng AI, hệ thống sẽ soạn chi tiết theo nguồn đã cung cấp.</p>
  </section>
  <section><h2>III. Yêu cầu cần đạt</h2><ul>{obj_html}</ul></section>
  <section><h2>IV. Năng lực và phẩm chất</h2>
    <ul><li><strong>Năng lực chung:</strong> tự chủ và tự học; giao tiếp và hợp tác; giải quyết vấn đề và sáng tạo.</li>
    <li><strong>Năng lực đặc thù:</strong> phù hợp với đặc trưng môn {html.escape(subject)}.</li>
    <li><strong>Phẩm chất:</strong> chăm chỉ, trung thực, trách nhiệm.</li></ul></section>
  <section><h2>V. Tích hợp năng lực số</h2><ul>{comp_html}</ul></section>
  <section><h2>VI. Thiết bị, học liệu và chuẩn bị</h2>
    <ul><li>Giáo viên: SGK, học liệu số/ảnh trang bài, phiếu học tập, bảng tiêu chí đánh giá.</li>
    <li>Học sinh: SGK, vở ghi, đồ dùng học tập; thiết bị số nếu có.</li></ul></section>
  <section><h2>VII. Tiến trình dạy học</h2>
    <table><tr><th>Hoạt động</th><th>Thời gian</th><th>Mục tiêu</th><th>Hoạt động của giáo viên</th><th>Hoạt động của học sinh</th><th>Sản phẩm</th><th>Đánh giá</th></tr>{rows}</table>
  </section>
  <section><h2>VIII. Phân hóa và hỗ trợ học sinh</h2>
    <ul><li>HS cần hỗ trợ: giao nhiệm vụ ngắn, có gợi ý từng bước.</li>
    <li>HS hoàn thành tốt: giao nhiệm vụ mở rộng, yêu cầu giải thích.</li>
    <li>Lớp thiếu thiết bị: tổ chức nhóm/cặp và dùng học liệu in.</li></ul></section>
  <section><h2>IX. Đánh giá thường xuyên</h2>
    <ul><li>Minh chứng: câu trả lời, sản phẩm học tập, phiếu học tập, quan sát nhóm.</li>
    <li>Câu hỏi nhanh: Em học được điều gì? Em còn băn khoăn điều gì?</li></ul></section>
  <section><h2>X. Phiếu học tập</h2>
    <table><tr><th>Nhiệm vụ</th><th>Kết quả của em</th><th>Tự đánh giá</th></tr>
    <tr><td>Hoàn thành nhiệm vụ trọng tâm</td><td></td><td>Đạt / Cần cố gắng</td></tr>
    <tr><td>Nêu điều em vận dụng được</td><td></td><td>Đạt / Cần cố gắng</td></tr></table></section>
  <section><h2>XI. Rubric đánh giá</h2>
    <table><tr><th>Tiêu chí</th><th>Tốt</th><th>Đạt</th><th>Cần hỗ trợ</th></tr>
    <tr><td>Hiểu nội dung bài</td><td>Nêu đúng, giải thích rõ</td><td>Nêu được ý chính</td><td>Cần gợi ý</td></tr>
    <tr><td>Thực hiện nhiệm vụ</td><td>Hoàn thành chủ động</td><td>Hoàn thành cơ bản</td><td>Chưa hoàn thành</td></tr>
    <tr><td>Hợp tác</td><td>Tích cực hỗ trợ bạn</td><td>Tham gia hoạt động</td><td>Còn thụ động</td></tr></table></section>
  <section><h2>XII. Điều chỉnh sau tiết dạy</h2>
    <p>............................................................................................................................</p>
    <p>............................................................................................................................</p></section>
</article>
""".strip()
