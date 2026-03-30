from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from typing import Any, Callable

import hashlib
import streamlit as st

from services.chat_service import ChatService
from services.doc_service import DocService
from services.mindmap_service import MindmapService
from services.schema_service import SchemaService
from services.ui_helpers import CHAT_EDUCATION_SYSTEM_PROMPT, render_module_hero, render_module_section, render_result_shell


@dataclass(frozen=True)
class PageDeps:
    go: Callable[[str], None]
    ensure_nav_state: Callable[[], None]
    require_login: Callable[[str], None]
    render_chat_history: Callable[[list[dict]], None]
    detect_chat_module_intent: Callable[[str], dict | None]
    build_limited_chat_context: Callable[[list[dict], str, int], str]
    gemini_generate: Callable[..., str]
    chunk_text: Callable[[str], list[str]]
    simple_retrieve: Callable[[str, list[str], int], list[str]]
    extract_text_from_upload: Callable[..., str]
    init_supabase: Callable[[], Any]
    log_usage_event: Callable[..., bool]
    chat_service: ChatService | None = None
    doc_service: DocService | None = None
    mindmap_service: MindmapService | None = None


_TEXT_OUTPUT_SCHEMA = {"type": "string", "minLength": 1}
_text_output_validator = SchemaService(_TEXT_OUTPUT_SCHEMA)


def _validate_text_output(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    valid, _ = _text_output_validator.validate(text)
    return text if valid else ""


def module_chat(deps: PageDeps) -> None:
    deps.ensure_nav_state()
    user = st.session_state.get("user")
    render_module_hero("💬 Chat AI", "Trao đổi nhanh theo ngữ cảnh giáo dục, giữ cùng shell với các module khác.")
    st.caption("AI chỉ hỗ trợ gợi ý nội dung giáo dục; giáo viên là người kiểm tra và quyết định nội dung sử dụng.")
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("chat_intent_hint", None)
    render_module_section("1. Nhập dữ liệu")
    prompt = st.chat_input("Nhập câu hỏi của bạn…")
    render_module_section("2. Hành động")
    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("🧹 Xóa chat", key="chat_clear", use_container_width=True):
            st.session_state["chat_messages"] = []
            st.rerun()
    with cols[1]:
        if st.button("⬅️ Về Home", key="chat_home", use_container_width=True):
            deps.go("dashboard")
    if prompt:
        if (not user) and st.session_state.get("demo_used"):
            deps.require_login("chat")
            return
        intent = deps.detect_chat_module_intent(prompt)
        st.session_state["chat_intent_hint"] = intent
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("AI đang trả lời…"):
                limited_context = deps.build_limited_chat_context(
                    st.session_state["chat_messages"][:-1],
                    prompt,
                    max_turns=4,
                )
                username = (st.session_state.get("user") or {}).get("email")
                if deps.chat_service is not None:
                    reply = deps.chat_service.ask(
                        limited_context,
                        CHAT_EDUCATION_SYSTEM_PROMPT,
                        username=username,
                    )
                else:
                    reply = deps.gemini_generate(
                        limited_context,
                        system=CHAT_EDUCATION_SYSTEM_PROMPT,
                    )
                reply = _validate_text_output(reply)
                if intent and reply:
                    reply = f"{reply}\n\nGợi ý: Có sẵn **{intent['module_label']}** trên website."
                st.markdown(reply if reply else "…")
        st.session_state["chat_messages"].append({"role": "assistant", "content": reply})
        if not user:
            st.session_state["demo_used"] = True
            st.info("Bạn vừa dùng thử 1 câu. Đăng nhập để tiếp tục sử dụng đầy đủ.")
    render_module_section("3. Kết quả")
    render_result_shell("Lịch sử & phản hồi gần nhất")
    st.caption("Khung dưới là lịch sử chat, bắt đầu từ phần trả lời gần nhất.")
    deps.render_chat_history(st.session_state["chat_messages"])
    render_module_section("4. Secondary actions")
    st.caption("Dùng nút bên trên để xóa cuộc trò chuyện hoặc quay về trang chủ.")


def module_doc_ai(deps: PageDeps) -> None:
    deps.ensure_nav_state()
    if not st.session_state.get("user"):
        deps.require_login("doc_ai")
        return
    def _compact_scope(label: str, expanded: bool = False):
        expander = getattr(st, "expander", None)
        if callable(expander):
            return expander(label, expanded=expanded)
        return nullcontext()

    render_module_hero("📄 Doc AI", "Tải tài liệu (PDF/DOCX/ảnh) → tóm tắt → hỏi theo nội dung tài liệu.")
    st.caption("RAG nhẹ, ổn định Cloud.")
    render_module_section("1. Nhập dữ liệu")
    doc_file = st.file_uploader("Tải tài liệu", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"], key="docai_upload")
    cols = st.columns([1.1, 1.2])
    with cols[0]:
        max_pages = st.slider("Giới hạn số trang xử lý (PDF)", 1, 20, 6, key="docai_pages")
    with cols[1]:
        try_ocr = st.checkbox("Thử OCR nếu PDF scan/ảnh", value=True, key="docai_ocr")
    if doc_file:
        with st.spinner("Đang đọc tài liệu…"):
            raw = deps.extract_text_from_upload(doc_file, max_pages=max_pages, ocr_if_needed=try_ocr)
            raw = (raw or "").strip()
            if not raw:
                st.error("Không đọc được nội dung. Thử bật OCR hoặc dùng bản PDF có text.")
            else:
                st.session_state["docai_text"] = raw[:20000]
                st.session_state["docai_chunks"] = deps.chunk_text(st.session_state["docai_text"])
                st.success(f"Đã nạp tài liệu: {getattr(doc_file, 'name', 'file')}")
                docai_ready = bool((st.session_state.get("docai_text") or "").strip()) or len(st.session_state.get("docai_chunks") or []) > 0
                if docai_ready:
                    try:
                        file_bytes = b""
                        try:
                            file_bytes = doc_file.getvalue() or b""
                        except Exception:
                            file_bytes = b""
                        doc_sig = hashlib.sha256(file_bytes).hexdigest() if file_bytes else f"{getattr(doc_file, 'name', 'file')}|{len(raw)}|{max_pages}|{int(bool(try_ocr))}"
                        last_sig = st.session_state.get("docai_last_logged_sig")
                        if doc_sig != last_sig:
                            client = deps.init_supabase()
                            username = st.session_state.get("user", {}).get("email", "")
                            if client and username:
                                ok = deps.log_usage_event(
                                    module_name="doc_ai",
                                    action_name="process_document",
                                    username=username,
                                    success=True,
                                    client=client,
                                    meta={
                                        "filename": getattr(doc_file, "name", ""),
                                        "max_pages": int(max_pages),
                                        "try_ocr": bool(try_ocr),
                                        "text_len": len(raw),
                                    },
                                )
                                if ok:
                                    st.session_state["docai_last_logged_sig"] = doc_sig
                    except Exception:
                        pass
    render_module_section("2. Hành động")
    if st.session_state.get("docai_text"):
        st.markdown(
            """
<div class="card soft">
  <b>📎 Đã tải tài liệu, chọn cách xử lý</b>
  <div class="small-muted" style="margin-top:6px;">
    Ba tab bên dưới là 3 cách xử lý cùng một tài liệu: tóm tắt, hỏi đáp và xem nội dung trích xuất.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.info("Chưa có tài liệu. Hãy tải file ở phần trên, sau đó chọn cách xử lý bên dưới.")
    tabs = st.tabs(["🧾 Tóm tắt cùng tài liệu", "💬 Hỏi đáp trên tài liệu", "👁️ Xem nội dung đã tải"])
    with tabs[0]:
        st.caption("Kết quả tóm tắt sẽ xuất hiện ngay bên dưới sau khi bấm nút.")
        if st.button("✨ Tạo tóm tắt", type="primary", key="docai_sum", use_container_width=True):
            txt = (st.session_state.get("docai_text") or "").strip()
            if not txt:
                st.warning("Hãy tải tài liệu trước.")
            else:
                with st.spinner("AI đang tóm tắt…"):
                    username = (st.session_state.get("user") or {}).get("email")
                    out = deps.doc_service.summarize(txt, username=username)
                    out = _validate_text_output(out)
                render_module_section("3. Kết quả")
                render_result_shell("Tóm tắt tài liệu")
                st.markdown(out)
    with tabs[1]:
        st.caption("Kết quả hỏi đáp sẽ xuất hiện ngay bên dưới sau khi bấm nút.")
        txt = (st.session_state.get("docai_text") or "").strip()
        if not txt:
            st.info("Tải tài liệu trước để chat theo tài liệu.")
        q = st.text_input("Nhập câu hỏi về tài liệu…", key="docai_q")
        if st.button("Hỏi tài liệu", key="docai_ask", type="primary", use_container_width=True):
            if not txt:
                st.warning("Chưa có tài liệu.")
            else:
                ctx_chunks = deps.simple_retrieve(q, st.session_state.get("docai_chunks") or [], k=4)
                ctx = "\n\n---\n\n".join(ctx_chunks)
                with st.spinner("AI đang trả lời theo tài liệu…"):
                    username = (st.session_state.get("user") or {}).get("email")
                    out = deps.doc_service.answer(ctx, q, username=username)
                    out = _validate_text_output(out)
                render_module_section("3. Kết quả")
                render_result_shell("Trả lời theo tài liệu")
                st.markdown(out)
    with tabs[2]:
        st.caption("Đây là nội dung trích xuất từ tài liệu đã tải, dùng để kiểm tra nhanh trước khi xử lý.")
        txt = (st.session_state.get("docai_text") or "").strip()
        render_module_section("3. Kết quả")
        render_result_shell("Nội dung trích xuất")
        st.text_area("Nội dung trích xuất (đã rút gọn)", value=txt[:16000], height=220, key="docai_preview")
    render_module_section("4. Secondary actions")
    with _compact_scope("Thu gọn thao tác phụ", expanded=False):
        cols = st.columns([1, 1])
        with cols[0]:
            if st.button("🧹 Xóa tài liệu", key="docai_clear", use_container_width=True):
                st.session_state.pop("docai_text", None)
                st.session_state.pop("docai_chunks", None)
                st.session_state.pop("docai_last_logged_sig", None)
                st.rerun()
        with cols[1]:
            st.button("ℹ️ Giữ nguyên luồng xử lý", key="docai_lock", disabled=True, use_container_width=True)


def module_mindmap(deps: PageDeps) -> None:
    deps.ensure_nav_state()
    if not st.session_state.get("user"):
        deps.require_login("mindmap")
        return
    render_module_hero("🧠 Mindmap AI", "Nhập chủ đề hoặc nội dung → AI tạo mindmap dạng cây (Markdown).")
    st.caption("Dùng cho soạn bài, ôn tập, trình chiếu.")
    render_module_section("1. Nhập dữ liệu")
    inp = st.text_area("Nội dung / chủ đề", height=200, key="mm_in")
    st.caption("Gợi ý: thêm từ khóa như 'soạn bài', 'ôn tập', 'trình chiếu' hoặc 'hoạt động nhóm' để AI chọn đúng style.")

    def _detect_mindmap_style(text: str) -> tuple[str, str]:
        q = (text or "").strip().lower()
        if any(k in q for k in ("trình chiếu", "slide", "thuyết trình", "powerpoint", "ppt")):
            return ("trình chiếu", "cực ngắn, dễ nhìn")
        if any(k in q for k in ("hoạt động nhóm", "nhóm", "thảo luận", "giao nhiệm vụ", "trạm")):
            return ("hoạt động nhóm", "chia ý rõ, giao nhiệm vụ")
        if any(k in q for k in ("ôn tập", "củng cố", "nhắc lại", "review", "revision")):
            return ("ôn tập", "ngắn gọn, trọng tâm")
        if any(k in q for k in ("soạn bài", "giáo án", "kế hoạch bài dạy", "bài dạy", "chuẩn bị bài")):
            return ("soạn bài", "đầy đủ cấu trúc nội dung")
        return ("soạn bài", "đầy đủ cấu trúc nội dung")

    render_module_section("2. Hành động")
    if st.button("✨ Tạo Mindmap", type="primary", key="mm_go", use_container_width=True):
        if not inp.strip():
            st.warning("Nhập nội dung trước.")
        else:
            topic = inp.strip().splitlines()[0][:80]
            mindmap_style, mindmap_goal = _detect_mindmap_style(inp)
            with st.spinner("AI đang tạo mindmap…"):
                username = (st.session_state.get("user") or {}).get("email")
                out = deps.mindmap_service.create(
                    inp,
                    style=mindmap_style,
                    goal=mindmap_goal,
                    username=username,
                )
                out = _validate_text_output(out)
            def _mindmap_is_valid(markdown_text: str) -> bool:
                lines = [ln.strip() for ln in (markdown_text or "").splitlines() if ln.strip()]
                if not lines:
                    return False
                if not lines[0].startswith("# "):
                    return False
                branch_lines = [ln for ln in lines if ln.startswith("- ")]
                sub_lines = [ln for ln in lines if ln.startswith("  - ")]
                return len(branch_lines) >= 2 and len(sub_lines) >= 4

            if not _mindmap_is_valid(out):
                topic_line = topic or "Mindmap"
                if mindmap_style == "trình chiếu":
                    fallback = f"# {topic_line}\n\n- {topic_line}\n  - Ý 1\n  - Ý 2\n  - Ý 3\n\nGợi ý sử dụng: Dùng trên slide."
                elif mindmap_style == "hoạt động nhóm":
                    fallback = f"# {topic_line}\n\n- {topic_line}\n  - Nhiệm vụ 1\n  - Nhiệm vụ 2\n  - Nhiệm vụ 3\n  - Nhiệm vụ 4\n\nGợi ý sử dụng: Giao nhóm thảo luận."
                elif mindmap_style == "ôn tập":
                    fallback = f"# {topic_line}\n\n- {topic_line}\n  - Trọng tâm 1\n  - Trọng tâm 2\n  - Trọng tâm 3\n\nGợi ý sử dụng: Ôn nhanh trước giờ học."
                else:
                    fallback = f"# {topic_line}\n\n- {topic_line}\n  - Ý chính 1\n  - Ý chính 2\n  - Ý chính 3\n  - Ý chính 4\n\nGợi ý sử dụng: Dùng trực tiếp trên lớp."
                out = fallback
            render_module_section("3. Kết quả")
            render_result_shell("Mindmap")
            st.markdown(out)
            st.download_button("⬇️ Tải mindmap (.md)", data=out.encode("utf-8"), file_name="mindmap.md", mime="text/markdown", use_container_width=True)
