from __future__ import annotations

import re
from typing import Callable

import streamlit as st


CHAT_EDUCATION_SYSTEM_PROMPT = (
    "Bạn là trợ lý AI dành riêng cho giáo viên Việt Nam. "
    "Ưu tiên hỗ trợ các chủ đề giáo dục và sư phạm: soạn bài, giáo án, kiểm tra đánh giá, "
    "ra đề, nhận xét học sinh, CTGDPT 2018, năng lực số, phương pháp dạy học, quản lý lớp học, "
    "hỗ trợ chuyên môn cho giáo viên. "
    "Trả lời tự nhiên, thân thiện, ngắn gọn và đúng trọng tâm. "
    "Nếu nội dung có thể liên hệ tới các chức năng sẵn có trên website, hãy trả lời bình thường rồi thêm một gợi ý ngắn ở cuối."
)

_EDU_TOPIC_KEYWORDS = (
    "giáo viên",
    "giáo dục",
    "dạy học",
    "soạn bài",
    "giáo án",
    "bài giảng",
    "ra đề",
    "đề thi",
    "kiểm tra",
    "đánh giá",
    "nhận xét",
    "học sinh",
    "lớp học",
    "ctgdpt",
    "chương trình",
    "năng lực số",
    "nls",
    "phương pháp dạy học",
    "sư phạm",
    "môn học",
    "tài liệu dạy học",
    "học liệu",
    "đặc tả",
    "ma trận",
    "rubric",
    "bài tập",
    "mục tiêu bài học",
    "kế hoạch bài dạy",
    "ppct",
    "chuyên môn",
)


def require_login(page_key: str) -> None:
    if st.session_state.get("user"):
        return
    st.session_state["requested_page"] = page_key
    st.session_state["current_page"] = "login"
    st.rerun()


def ensure_nav_state() -> None:
    st.session_state.setdefault("current_page", "dashboard")
    st.session_state.setdefault("requested_page", None)
    st.session_state.setdefault("demo_used", False)
    st.session_state.setdefault("demo_history", [])


def render_topbar(go_callback: Callable[[str], None], logo_fn: Callable[[int], str]) -> None:
    """Topbar gọn, dùng callback để tránh phụ thuộc vào app.py."""
    ensure_nav_state()
    user = st.session_state.get("user") or {}
    is_authed = bool(user)
    fullname = user.get("fullname") or user.get("email") or "Khách"

    def _quick_nav_from_query() -> None:
        query = (st.session_state.get("global_search") or "").strip().lower()
        if not query:
            return
        page_key = None
        keyword_map = [
            ("ra đề", "exam"),
            ("kiểm tra", "exam"),
            ("đề thi", "exam"),
            ("soạn bài", "lesson_plan"),
            ("giáo án", "lesson_plan"),
            ("lesson", "lesson_plan"),
            ("doc", "doc_ai"),
            ("tài liệu", "doc_ai"),
            ("mindmap", "mindmap"),
            ("sơ đồ", "mindmap"),
            ("chat", "chat"),
            ("năng lực số", "digital"),
            ("digital", "digital"),
            ("nhận xét", "advisor"),
            ("tư vấn", "advisor"),
            ("thống kê", "evidence"),
            ("dashboard", "dashboard"),
            ("hướng dẫn", "help"),
            ("profile", "profile"),
            ("đăng nhập", "login"),
        ]
        for keyword, candidate in keyword_map:
            if keyword in query:
                page_key = candidate
                break
        if page_key:
            st.session_state["global_search"] = ""
            go_callback(page_key)
        else:
            st.toast("Chưa khớp module. Thử: chat, doc, mindmap, ra đề, soạn bài, nls, nhận xét.", icon="ℹ️")

    c1, c2, c3 = st.columns([2.8, 5.2, 2.0], vertical_alignment="center", gap="small")
    with c1:
        st.markdown(
            f"""
<div style="display:flex;gap:10px;align-items:center;">
  <div style="width:52px;height:52px;border-radius:14px;background:transparent;box-shadow:none;overflow:visible;">
    {logo_fn(52)}
  </div>
  <div>
    <div style="font-weight:900;line-height:1.05;">AIEXAM.VN</div>
    <div class="small-muted">Nền tảng AI dành cho giáo viên</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    with c2:
        cc1, cc2 = st.columns([1, 1], vertical_alignment="center")
        with cc1:
            st.text_input(
                "Tìm kiếm nhanh",
                placeholder="Nhập: chat, doc, mindmap, ra đề, soạn bài, nls…",
                key="global_search",
                label_visibility="collapsed",
                on_change=_quick_nav_from_query,
            )
        with cc2:
            if st.button("📘 Hướng dẫn", use_container_width=True, key="tb_help"):
                go_callback("help")
    with c3:
        if is_authed:
            with st.popover(f"👤 {fullname}", use_container_width=True):
                role = (user.get("role") or "free").upper()
                pts = user.get("points", 0)
                st.markdown(f"**Gói:** `{role}`  \n**Điểm:** `{pts}`")
                st.write("---")
                if st.button("👤 Profile", use_container_width=True, key="tb_profile"):
                    go_callback("profile")
                if st.button("🚪 Đăng xuất", use_container_width=True, key="tb_logout"):
                    st.session_state.pop("user", None)
                    st.toast("👋 Bạn đã đăng xuất.", icon="✅")
                    go_callback("dashboard")
        else:
            if st.button("🔐 Đăng nhập", type="primary", use_container_width=True, key="tb_login"):
                st.session_state["requested_page"] = st.session_state.get("current_page", "dashboard")
                go_callback("login")


def render_module_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#0F172A 0%,#123A8F 52%,#2563EB 100%);
  border-radius:14px;padding:14px 16px;color:#fff;border:1px solid rgba(255,255,255,.16);
  box-shadow:0 12px 22px rgba(15,23,42,.18);margin:2px 0 10px 0;">
  <h2 style="margin:0;font-weight:900;line-height:1.08;font-size:1.45rem;">{title}</h2>
  <div style="opacity:.96;margin-top:4px;line-height:1.38;font-size:0.94rem;color:rgba(255,255,255,.92);">{subtitle}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_module_section(title: str) -> None:
    st.markdown(
        f"""
<div style="margin:10px 0 6px 0; padding-top:2px; border-top:1px solid rgba(37,99,235,.16);">
  <div style="font-size:12.5px; font-weight:900; letter-spacing:.05em; text-transform:uppercase; color:#0b1220;">{title}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_result_shell(title: str = "Kết quả") -> None:
    st.markdown(
        f"""
<div style="margin:8px 0 10px 0; padding:10px 12px; border-radius:14px; border:1px solid rgba(59,130,246,.14);
  background:linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(239,246,255,.96) 100%);
  box-shadow:0 8px 18px rgba(15,23,42,.06);">
  <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
    <div style="width:10px;height:10px;border-radius:999px;background:#1d4ed8;"></div>
    <div style="font-weight:900;color:#0b1220;font-size:13px;">{title}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + chunk_size)
        chunks.append(text[i:j])
        if j == n:
            break
        i = max(0, j - overlap)
    return chunks


def simple_retrieve(query: str, chunks: list[str], k: int = 4) -> list[str]:
    q = (query or "").lower()
    if not q or not chunks:
        return chunks[:k]
    q_terms = [t for t in re.split(r"[^\wÀ-ỹ]+", q) if t]
    scored = []
    for ch in chunks:
        s = 0
        low = ch.lower()
        for t in q_terms[:20]:
            if t and t in low:
                s += 1
        scored.append((s, ch))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [c for s, c in scored[:k] if s > 0]
    return top if top else chunks[:k]


def is_education_question(text: str) -> bool:
    q = (text or "").strip().lower()
    if not q:
        return True
    if any(k in q for k in _EDU_TOPIC_KEYWORDS):
        return True
    if any(k in q for k in ("lesson", "exam", "curriculum", "worksheet", "classroom", "feedback")):
        return True
    return False


def build_limited_chat_context(messages: list[dict], current_prompt: str, max_turns: int = 4) -> str:
    recent = (messages or [])[-(max_turns * 2):]
    parts = [CHAT_EDUCATION_SYSTEM_PROMPT, "", "Ngữ cảnh hội thoại gần nhất:"]
    for m in recent:
        role = "Người dùng" if m.get("role") == "user" else "Trợ lý"
        content = (m.get("content") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    parts.append("")
    parts.append(f"Câu hỏi hiện tại: {current_prompt.strip()}")
    parts.append("")
    parts.append("Yêu cầu trả lời: ngắn gọn, đúng trọng tâm, ưu tiên nội dung giáo dục cho giáo viên.")
    return "\n".join(parts)


def detect_chat_module_intent(text: str) -> dict | None:
    q = (text or "").strip().lower()
    if not q:
        return None
    intent_rules = [
        (
            "exam",
            "Ra đề – KTĐG",
            ("ra đề", "đề thi", "kiểm tra", "ma trận", "đáp án", "trắc nghiệm", "tự luận", "đặc tả", "exam"),
        ),
        (
            "lesson_plan",
            "Trợ lý Soạn bài",
            ("soạn giáo án", "soạn bài", "kế hoạch bài dạy", "giáo án", "bài dạy", "ppct", "lesson plan"),
        ),
        (
            "doc_ai",
            "Doc AI",
            ("pdf", "docx", "txt", "tóm tắt tài liệu", "hỏi theo tài liệu", "trích xuất", "tài liệu", "document"),
        ),
        ("mindmap", "Mindmap", ("mindmap", "sơ đồ tư duy", "sơ đồ", "map tư duy")),
        (
            "digital",
            "Năng lực số",
            ("năng lực số", "tích hợp công nghệ số", "chuyển đổi số", "digital", "công nghệ số"),
        ),
        (
            "advisor",
            "Nhận xét – Tư vấn",
            ("nhận xét học sinh", "nhận xét", "tư vấn", "góp ý", "khuyến nghị", "phản hồi học sinh"),
        ),
    ]
    for module_key, module_label, keywords in intent_rules:
        if any(k in q for k in keywords):
            return {
                "module_key": module_key,
                "module_label": module_label,
            }
    return None


def render_chat_history(messages: list[dict]) -> None:
    if not messages:
        st.markdown(
            """
<div style="margin:12px 0 14px 0; padding:16px 16px 14px 16px; border:1px solid rgba(91,92,246,.12); border-radius:18px;
            background: linear-gradient(135deg, rgba(255,255,255,.92), rgba(242,244,255,.92));
            box-shadow: 0 12px 24px rgba(2,6,23,.06);">
  <div style="font-weight:800; color:#0f172a; margin-bottom:8px;">Bắt đầu nhanh</div>
  <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
    <span class="hero-badge">Soạn giáo án theo CTGDPT 2018</span>
    <span class="hero-badge">Tạo ma trận đề và đặc tả</span>
    <span class="hero-badge">Nhận xét học sinh cuối kỳ</span>
  </div>
  <div class="small-muted" style="font-size:13px; line-height:1.55;">
    Khung chat sẵn sàng. Hãy nhập câu hỏi để bắt đầu trao đổi.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        return
    for m in messages:
        with st.chat_message(m.get("role", "assistant")):
            st.markdown(m.get("content", ""))
