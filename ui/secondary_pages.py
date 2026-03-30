from __future__ import annotations

from html import escape as html_escape
from typing import Callable

import streamlit as st

from services.ui_helpers import render_module_hero, render_module_section


def module_help() -> None:
    render_module_hero("📘 Hướng dẫn sử dụng", "Các module chính và luồng sử dụng được giữ ổn định, dễ theo dõi.")
    st.caption("Tài liệu hướng dẫn nhanh cho giáo viên.")
    tab1, tab2 = st.tabs(["🧠 Hướng dẫn sử dụng module", "💎 Hướng dẫn nạp VIP / PRO"])

    with tab1:
        items = [
            ("💬 Chat AI", "Dùng để hỏi đáp, soạn câu hỏi, gợi ý hoạt động dạy học và viết nhận xét."),
            ("📄 Doc AI", "Tải PDF / DOCX / TXT để tóm tắt, rút ý chính hoặc hỏi theo tài liệu."),
            ("🧠 Mindmap AI", "Tạo sơ đồ tư duy cho bài học, chương, ôn tập hoặc trình chiếu."),
            ("📝 Ra đề – KTĐG", "Sinh đề kiểm tra, ma trận đề và đáp án theo mức độ."),
            ("📘 Trợ lý Soạn bài", "Tạo giáo án theo môn, lớp, bộ sách và mục tiêu dạy học."),
            ("💻 Năng lực số", "Tích hợp hoạt động số, công cụ số và tiêu chí đánh giá vào bài dạy."),
            ("🧩 Nhận xét – Tư vấn", "Viết nhận xét học sinh hoặc gợi ý cải tiến hoạt động dạy học."),
        ]
        for idx, (title, body) in enumerate(items, start=1):
            render_module_section(f"{idx}. {title}")
            st.write(body)

    with tab2:
        render_module_section("Kích hoạt VIP / PRO")
        st.write("Đăng nhập, nạp điểm và xác minh thanh toán theo hướng dẫn trên website.")


def module_profile(
    *,
    go: Callable[[str], None],
    ensure_nav_state: Callable[[], None],
    require_login: Callable[[str], None],
) -> None:
    ensure_nav_state()
    user = st.session_state.get("user") or {}
    if not user:
        require_login("profile")
        return

    st.markdown("## 👤 Profile")
    st.caption("Thông tin tài khoản và trạng thái gói/điểm.")
    col1, col2 = st.columns([1.2, 1], vertical_alignment="top")

    with col1:
        st.markdown(
            f"""
<div class="card">
  <div style="display:flex;gap:12px;align-items:center;">
    <div style="width:46px;height:46px;border-radius:16px;background:rgba(91,92,246,.14);display:flex;align-items:center;justify-content:center;font-weight:900;color:#3b5bff;">
      {html_escape((user.get("fullname") or "U")[:1].upper())}
    </div>
    <div>
      <div style="font-weight:900;font-size:18px;line-height:1.1;">{html_escape(user.get("fullname") or "Chưa đặt tên")}</div>
      <div class="small-muted">{html_escape(user.get("email") or "")}</div>
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(
            f"""
<div class="card soft">
  <b>Gói:</b> {(user.get("role") or "free").upper()}<br/>
  <b>Điểm:</b> {user.get("points", 0)}
</div>
""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
<div class="card">
  <b>⚙️ Tác vụ</b>
  <div class="small-muted" style="margin-top:6px;">Bạn có thể quay về Trang chủ hoặc đăng xuất tại đây.</div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("🏡 Về Trang chủ", use_container_width=True, key="pf_home"):
            go("dashboard")
        if st.button("🚪 Đăng xuất", use_container_width=True, key="pf_logout"):
            st.session_state.pop("user", None)
            st.toast("👋 Bạn đã đăng xuất.", icon="✅")
            go("dashboard")
