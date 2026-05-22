# -*- coding: utf-8 -*-
"""
Email OTP utilities — chống abuse đăng ký nhiều account miễn phí.

Cung cấp 4 hàm:
    is_valid_email_format(email)  — Tầng 1: regex check
    is_disposable_email(email)    — Tầng 3: blocklist disposable domain
    generate_otp(digits=6)        — sinh OTP 6 số
    send_otp_email(to, otp)       — Tầng 2: gửi qua Gmail SMTP

Cấu hình Gmail SMTP qua biến môi trường (Streamlit secrets hoặc OS env):
    SMTP_HOST       (mặc định: smtp.gmail.com)
    SMTP_PORT       (mặc định: 587)
    SMTP_USER       (email gửi đi, vd: aiexam.vn@gmail.com)
    SMTP_PASSWORD   (Gmail App Password, KHÔNG phải mật khẩu thường)
    SMTP_FROM_NAME  (mặc định: AIEXAM)

Hướng dẫn lấy Gmail App Password: SETUP_EMAIL.md
"""

from __future__ import annotations

import os
import re
import secrets
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except Exception:
    _HAS_STREAMLIT = False


# ============================================================================
# Tầng 1 — Email format validation
# ============================================================================

# Regex pragmatic — không phải full RFC 5322, nhưng bắt 99% lỗi nhập thực tế.
_EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


def is_valid_email_format(email: str) -> bool:
    """True nếu chuỗi có dạng email hợp lệ. Không check tồn tại thật."""
    if not isinstance(email, str):
        return False
    email = email.strip()
    if not email or len(email) > 254:
        return False
    return bool(_EMAIL_REGEX.match(email))


# ============================================================================
# Tầng 3 — Disposable email blocklist
# ============================================================================

# Danh sách top ~200 domain disposable phổ biến tính tới 2025.
# Nguồn: ivolo/disposable-email-domains + thủ công bổ sung domain VN.
_DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    # === Top disposable services ===
    "10minutemail.com", "10minutemail.net", "10minemail.com",
    "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmailo.com",
    "mailinator.com", "mailinator.net", "mailinator2.com",
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "guerrillamail.biz", "guerrillamail.de", "grr.la", "sharklasers.com",
    "yopmail.com", "yopmail.net", "yopmail.fr",
    "throwawaymail.com", "throwaway-mail.com",
    "trashmail.com", "trashmail.de", "trashmail.io", "trashmail.net",
    "fakeinbox.com", "fakemail.net", "fakemailgenerator.com",
    "maildrop.cc", "mailcatch.com", "mailnesia.com", "mailtemp.info",
    "getairmail.com", "getnada.com", "nada.email", "nada.ltd",
    "mohmal.com", "emailondeck.com", "discard.email",
    "burnermail.io", "mintemail.com", "spam4.me", "spamgourmet.com",
    "dispostable.com", "wegwerf-email-addresse.de", "wegwerfemail.de",
    "boun.cr", "spambox.us", "spambog.com", "spambog.net",
    "tempinbox.com", "tempemail.com", "tempemail.net", "tempemailaddress.com",
    "tempr.email", "deadaddress.com", "33mail.com",
    "anonbox.net", "moakt.com", "moakt.cc", "moakt.ws",
    "instaeyl.com", "instamail.in", "instant-mail.de",
    "tmpmail.org", "tmpmail.net", "tmpeml.com", "tmpbox.net",
    "1secmail.com", "1secmail.org", "1secmail.net",
    "esiix.com", "wwjmp.com", "linshiyouxiang.net",
    "minutemail.com", "5ymail.com", "incognitomail.org",
    "mailtothis.com", "mvrht.net", "tafmail.com", "snapmail.cc",
    "armyspy.com", "cuvox.de", "dayrep.com", "einrot.com",
    "fleckens.hu", "gustr.com", "jourrapide.com", "rhyta.com",
    "superrito.com", "teleworm.us",
    # === Việt Nam-specific / phổ biến local ===
    "fakemail.io", "spamsalad.in", "mailde.de",
    "moburl.com", "boximail.com",
    # === Aggressive aliasing (số đếm domains) ===
    "20mail.it", "20minutemail.com", "30minutemail.com", "60minutemail.com",
})


def is_disposable_email(email: str) -> bool:
    """True nếu domain thuộc danh sách disposable. Case-insensitive."""
    if not isinstance(email, str) or "@" not in email:
        return False
    domain = email.strip().rsplit("@", 1)[-1].lower()
    return domain in _DISPOSABLE_DOMAINS


# ============================================================================
# OTP generation
# ============================================================================

def generate_otp(digits: int = 6) -> str:
    """Sinh OTP n chữ số dùng secrets (cryptographically secure).

    Mặc định 6 số → 1 triệu khả năng → đủ chống brute force trong 10 phút TTL.
    """
    if digits < 4 or digits > 10:
        raise ValueError("digits phải 4-10.")
    rng_max = 10 ** digits
    return str(secrets.randbelow(rng_max)).zfill(digits)


# ============================================================================
# Tầng 2 — Gửi OTP qua Gmail SMTP
# ============================================================================

def _get_smtp_config() -> dict[str, str]:
    """Đọc cấu hình SMTP từ st.secrets (ưu tiên) → os.environ → default."""
    def _get(key: str, default: str = "") -> str:
        # 1) st.secrets (Streamlit Cloud)
        if _HAS_STREAMLIT:
            try:
                val = st.secrets.get(key)  # type: ignore[attr-defined]
                if val:
                    return str(val)
            except Exception:
                pass
        # 2) Env var
        return os.environ.get(key, default)

    return {
        "host": _get("SMTP_HOST", "smtp.gmail.com"),
        "port": _get("SMTP_PORT", "587"),
        "user": _get("SMTP_USER", ""),
        "password": _get("SMTP_PASSWORD", ""),
        "from_name": _get("SMTP_FROM_NAME", "AIEXAM"),
    }


def is_smtp_configured() -> bool:
    """True nếu có đủ SMTP_USER + SMTP_PASSWORD để gửi email."""
    cfg = _get_smtp_config()
    return bool(cfg["user"] and cfg["password"])


def send_otp_email(to_email: str, otp: str, app_name: str = "AIEXAM") -> tuple[bool, str]:
    """Gửi email chứa OTP. Trả về (ok, message).

    Nếu chưa cấu hình SMTP → return (False, "...") — caller cần xử lý fallback
    (vd. hiện OTP lên màn hình cho dev mode).
    """
    cfg = _get_smtp_config()
    if not cfg["user"] or not cfg["password"]:
        return (False, "Chưa cấu hình SMTP_USER / SMTP_PASSWORD trong Streamlit secrets.")

    subject = f"[{app_name}] Mã xác nhận đăng ký tài khoản"
    body_html = f"""\
<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#0f172a;background:#f8fafc;padding:24px;">
  <div style="max-width:520px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;">
    <h2 style="margin:0 0 12px;color:#1d4ed8;">Xác nhận đăng ký {app_name}</h2>
    <p>Xin chào,</p>
    <p>Bạn vừa yêu cầu tạo tài khoản trên hệ thống <b>{app_name}</b>. Mã xác nhận của bạn là:</p>
    <div style="text-align:center;margin:24px 0;">
      <div style="display:inline-block;font-size:32px;letter-spacing:8px;font-weight:800;color:#0f172a;background:#eef4ff;padding:14px 28px;border-radius:10px;border:1px solid #cbd5e1;">
        {otp}
      </div>
    </div>
    <p>Mã có hiệu lực trong <b>10 phút</b>. Vui lòng nhập mã này vào ô xác nhận trên trang đăng ký để hoàn tất tạo tài khoản.</p>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:18px 0;"/>
    <p style="font-size:13px;color:#64748b;">
      Nếu bạn KHÔNG yêu cầu tạo tài khoản, hãy bỏ qua email này.<br>
      Đây là email tự động, vui lòng không trả lời.
    </p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['user']}>"
    msg["To"] = to_email
    msg.attach(MIMEText(f"Mã xác nhận đăng ký {app_name}: {otp}\n(Hiệu lực 10 phút)", "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        port = int(cfg["port"])
        with smtplib.SMTP(cfg["host"], port, timeout=15) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], [to_email], msg.as_string())
        return (True, f"Đã gửi OTP đến {to_email}")
    except smtplib.SMTPAuthenticationError:
        return (False, "Xác thực Gmail SMTP thất bại. Kiểm tra SMTP_USER và App Password.")
    except smtplib.SMTPRecipientsRefused:
        return (False, f"Địa chỉ {to_email} bị từ chối — kiểm tra email có đúng không.")
    except Exception as e:
        return (False, f"Lỗi gửi email: {type(e).__name__}: {e}")


# ============================================================================
# Helper composite — validate đầy đủ trước khi tạo OTP
# ============================================================================

def validate_email_for_registration(email: str) -> tuple[bool, Optional[str]]:
    """Validate đầy đủ trước khi gửi OTP. Trả về (ok, error_message).

    Sequence: format → disposable → các check tương lai (rate limit IP...).
    """
    if not is_valid_email_format(email):
        return (False, "Email không hợp lệ. Phải có dạng abc@xyz.com.")
    if is_disposable_email(email):
        return (False, "Hệ thống không chấp nhận email tạm thời (disposable). Vui lòng dùng email thật.")
    return (True, None)
