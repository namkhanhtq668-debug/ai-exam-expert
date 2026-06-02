import os
import streamlit as st  # pyright: ignore[reportMissingImports]

try:
    import google.generativeai as genai
except Exception:
    genai = None


def _get_api_key_effective() -> str:
    """Return API key from session or environment."""
    try:
        k = (st.session_state.get("api_key") or "").strip()
    except Exception:
        k = ""
    if not k:
        k = os.environ.get("GEMINI_API_KEY", "")
    return k


def _genai_list_models(api_key: str) -> list:
    """Guarded model discovery similar to tools/list_gemini_models.py."""
    if not genai:
        return []
    names = []
    # try configure if available
    try:
        cfg = getattr(genai, "configure", None)
        if callable(cfg):
            try:
                cfg(api_key=api_key)
            except Exception:
                try:
                    cfg(api_key)
                except Exception:
                    pass
    except Exception:
        pass

    def _push(res):
        if not res:
            return
        if isinstance(res, (list, tuple)):
            for m in res:
                if isinstance(m, dict) and "name" in m:
                    names.append(m["name"])
                else:
                    names.append(getattr(m, "name", str(m)))
        else:
            for m in getattr(res, "models", []) or []:
                names.append(getattr(m, "name", str(m)))

    for fn_name in ("list_models", "get_models"):
        fn = getattr(genai, fn_name, None)
        if callable(fn):
            try:
                _push(fn())
            except Exception:
                pass

    client = getattr(genai, "client", None)
    if client is not None:
        for fn_name in ("list_models", "get_models"):
            fn = getattr(client, fn_name, None)
            if callable(fn):
                try:
                    _push(fn())
                except Exception:
                    pass

    # dedupe
    out = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def module_help_intro():
    st.markdown("## 📘 Hướng dẫn sử dụng")
    st.caption("Tài liệu hướng dẫn nhanh dành cho thầy/cô – dễ hiểu – dùng được ngay.")
    tab1, tab2 = st.tabs(["🧠 Hướng dẫn sử dụng module", "💎 Hướng dẫn nạp VIP / PRO"])

    with tab1:
        st.markdown("AIEXAM là nền tảng AI hỗ trợ giáo viên trong dạy học và kiểm tra đánh giá.")
        st.markdown("- Nhập rõ: **Môn – Lớp – Nội dung – Mục tiêu – Thời lượng** để có kết quả tốt hơn.")
        st.divider()
        st.markdown("### Các tính năng chính")
        st.markdown("• Chat AI — hỏi đáp, soạn câu hỏi, sửa văn bản")
        st.markdown("• Doc AI — xử lý PDF/DOCX/TXT, tóm tắt, tạo câu hỏi")
        st.markdown("• Mindmap AI — tạo sơ đồ tư duy ngắn gọn")
        st.markdown("• Ra đề / Soạn giáo án — tạo đề/khung giáo án và xuất DOCX")
        st.divider()

        if st.button("Kiểm tra mô hình Gemini khả dụng"):
            api_key = _get_api_key_effective()
            if not api_key:
                st.error("Chưa cấu hình API key. Vui lòng nhập GEMINI_API_KEY trước.")
            else:
                with st.spinner("Đang lấy danh sách mô hình…"):
                    names = _genai_list_models(api_key)
                    if not names:
                        st.warning("Không lấy được danh sách mô hình.")
                        st.info("Bạn có thể chạy tools/list_gemini_models.py để thăm dò mô hình.")
                    else:
                        st.success(f"Tìm thấy {len(names)} mô hình")
                        st.write(names)

    with tab2:
        st.markdown("### Nạp VIP / PRO")
        st.markdown("Hướng dẫn nạp VIP/PRO: liên hệ quản trị để cấp key hoặc đặt gói dịch vụ.")


def main():
    st.set_page_config(page_title="AIEXAM", layout="wide")
    st.title("AIEXAM — Giáo viên trợ lý AI")
    module_help_intro()


if __name__ == "__main__":
    main()
