from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
import random

import streamlit as st

try:
    import bcrypt  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover
    bcrypt = None


def _hash_password(raw_password: str) -> str:
    password = (raw_password or "").encode("utf-8")
    if bcrypt is None:
        return raw_password or ""
    return bcrypt.hashpw(password, bcrypt.gensalt()).decode("utf-8")


def _check_password(raw_password: str, stored_password: str) -> bool:
    raw_password = raw_password or ""
    stored_password = stored_password or ""
    if not stored_password:
        return False
    if bcrypt is None:
        return raw_password == stored_password
    try:
        return bcrypt.checkpw(raw_password.encode("utf-8"), stored_password.encode("utf-8"))
    except Exception:
        return raw_password == stored_password


def _get_user_row(client: Any, username: str) -> dict[str, Any]:
    if not client or not username:
        return {}
    try:
        res = client.table("users_pro").select("*").eq("username", username).execute()
        return res.data[0] if getattr(res, "data", None) else {}
    except Exception:
        return {}


def _authenticate_user(client: Any, username: str, password: str) -> tuple[bool, str]:
    if not client:
        return False, "Thiếu kết nối Supabase."
    row = _get_user_row(client, username)
    if not row:
        return False, "Tài khoản không tồn tại."
    if not _check_password(password, str(row.get("password") or "")):
        return False, "Mật khẩu không đúng."
    st.session_state["user"] = {
        "username": row.get("username") or username,
        "email": row.get("email") or row.get("username") or username,
        "fullname": row.get("fullname") or row.get("name") or row.get("username") or username,
        "role": row.get("role") or "free",
        "points": row.get("points", 0) or 0,
    }
    return True, "Đăng nhập thành công."


def _register_user(client: Any, fullname: str, username: str, password: str) -> tuple[bool, str]:
    if not client:
        return False, "Thiếu kết nối Supabase."
    fullname = (fullname or "").strip()
    username = (username or "").strip()
    password = (password or "").strip()
    if not fullname or not username or not password:
        return False, "Vui lòng nhập đủ họ tên, tên đăng nhập và mật khẩu."
    if _get_user_row(client, username):
        return False, "Tài khoản đã tồn tại."
    payload = {
        "username": username,
        "email": username,
        "fullname": fullname,
        "password": _hash_password(password),
        "role": "free",
        "points": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.table("users_pro").insert(payload).execute()
        st.session_state["user"] = {
            "username": username,
            "email": username,
            "fullname": fullname,
            "role": "free",
            "points": 0,
        }
        return True, "Đăng ký thành công."
    except Exception as e:
        return False, f"Không thể đăng ký: {e}"


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _create_reset_token(client: Any, username: str) -> str | None:
    if not client or not username:
        return None
    try:
        token = _generate_otp()
        expired_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        client.table("reset_tokens").insert(
            {
                "username": username,
                "token": token,
                "expired_at": expired_at.isoformat(),
                "used": False,
            }
        ).execute()
        return token
    except Exception:
        return None


def _verify_reset_token(client: Any, username: str, token: str) -> bool:
    if not client or not username or not token:
        return False
    try:
        res = (
            client.table("reset_tokens")
            .select("*")
            .eq("username", username)
            .eq("token", token)
            .eq("used", False)
            .execute()
        )
        if not getattr(res, "data", None):
            return False
        row = res.data[0]
        expired_at_raw = row.get("expired_at")
        if not expired_at_raw:
            return False
        expired_at = datetime.fromisoformat(expired_at_raw)
        if expired_at.tzinfo is None:
            expired_at = expired_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= expired_at
    except Exception:
        return False


def _update_password(client: Any, username: str, new_password: str) -> bool:
    if not client or not username or not new_password:
        return False
    try:
        client.table("users_pro").update({"password": _hash_password(new_password)}).eq("username", username).execute()
        return True
    except Exception:
        return False


def _mark_token_used(client: Any, username: str, token: str) -> None:
    if not client or not username or not token:
        return
    try:
        client.table("reset_tokens").update({"used": True}).eq("username", username).eq("token", token).execute()
    except Exception:
        pass


def login_screen(*, init_supabase: Callable[[], Any]) -> None:
    st.markdown("## 🔐 Đăng nhập / Đăng ký")
    st.caption("Đăng nhập để dùng đầy đủ các module. Nếu chưa có tài khoản, bạn có thể đăng ký ngay trong app.")
    client = init_supabase()

    tab_login, tab_register, tab_forgot = st.tabs(["Đăng nhập", "Đăng ký", "Quên mật khẩu"])

    with tab_login:
        with st.form("auth_login_form", clear_on_submit=False):
            username = st.text_input("Tên đăng nhập hoặc email", key="auth_login_username")
            password = st.text_input("Mật khẩu", type="password", key="auth_login_password")
            submitted = st.form_submit_button("Đăng nhập", type="primary", use_container_width=True)
        if submitted:
            ok, message = _authenticate_user(client, username.strip(), password)
            if ok:
                target_page = st.session_state.get("requested_page") or "dashboard"
                st.session_state["current_page"] = target_page
                st.session_state["requested_page"] = None
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with tab_register:
        with st.form("auth_register_form", clear_on_submit=False):
            fullname = st.text_input("Họ và tên", key="auth_register_fullname")
            username = st.text_input("Tên đăng nhập hoặc email", key="auth_register_username")
            password = st.text_input("Mật khẩu", type="password", key="auth_register_password")
            confirm = st.text_input("Nhập lại mật khẩu", type="password", key="auth_register_confirm")
            submitted = st.form_submit_button("Đăng ký", type="primary", use_container_width=True)
        if submitted:
            if password != confirm:
                st.error("Mật khẩu nhập lại không khớp.")
            else:
                ok, message = _register_user(client, fullname, username, password)
                if ok:
                    st.success(message)
                    st.session_state["current_page"] = st.session_state.get("requested_page") or "dashboard"
                    st.session_state["requested_page"] = None
                    st.rerun()
                else:
                    st.error(message)

    with tab_forgot:
        st.caption("Mã OTP hiển thị ngay trên màn hình để test nội bộ.")
        with st.form("auth_forgot_form", clear_on_submit=False):
            username = st.text_input("Tên đăng nhập hoặc email", key="auth_forgot_username")
            send_otp = st.form_submit_button("Gửi mã xác nhận", use_container_width=True)
        otp = st.text_input("Nhập mã OTP", key="auth_forgot_otp")
        new_password = st.text_input("Mật khẩu mới", type="password", key="auth_forgot_password")
        c1, c2 = st.columns(2)
        with c1:
            if send_otp:
                token = _create_reset_token(client, username.strip())
                if token:
                    st.success(f"Mã xác nhận của bạn: {token}")
                else:
                    st.error("Không thể tạo mã xác nhận.")
        with c2:
            if st.button("Đặt lại mật khẩu", key="auth_reset_password", use_container_width=True):
                if _verify_reset_token(client, username.strip(), otp.strip()):
                    if _update_password(client, username.strip(), new_password.strip()):
                        _mark_token_used(client, username.strip(), otp.strip())
                        st.success("Đổi mật khẩu thành công.")
                    else:
                        st.error("Lỗi cập nhật mật khẩu.")
                else:
                    st.error("OTP không hợp lệ hoặc đã hết hạn.")

