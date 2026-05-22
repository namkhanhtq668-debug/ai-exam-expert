# Hướng dẫn cấu hình Gmail SMTP cho Email OTP

Module `email_otp.py` cần SMTP để gửi mã OTP xác nhận đăng ký. Hệ thống đang dùng **Gmail SMTP free** (giới hạn 500 email/ngày — đủ cho đăng ký mới).

## 1. Tạo Gmail App Password

Gmail không cho dùng mật khẩu thường để login SMTP — phải tạo **App Password** riêng.

### Yêu cầu
- Tài khoản Gmail (khuyến nghị tạo email mới chuyên cho dịch vụ: `aiexam.no-reply@gmail.com`)
- **Bật 2-Step Verification** (bắt buộc để tạo App Password)

### Các bước
1. Truy cập [https://myaccount.google.com/security](https://myaccount.google.com/security)
2. Mục **"2-Step Verification"** → bật nếu chưa bật (cần SĐT để xác minh)
3. Sau khi bật xong, vào [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. **App name**: gõ `AIEXAM` → click **Create**
5. Google hiện 1 chuỗi 16 ký tự (kiểu `abcd efgh ijkl mnop`) — **COPY ngay** (không xem lại được)
6. Đây là `SMTP_PASSWORD` của bạn — KHÔNG phải mật khẩu Gmail thường

## 2. Cấu hình trên Streamlit Cloud

Vào **Manage app** → **Settings** → **Secrets** → paste:

```toml
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USER = "aiexam.no-reply@gmail.com"
SMTP_PASSWORD = "abcd efgh ijkl mnop"
SMTP_FROM_NAME = "AIEXAM"
```

> Chú ý: `SMTP_PASSWORD` paste **NGUYÊN dạng có space** như Google hiển thị (Gmail xử lý cả 2 dạng).

Bấm **Save** → **Reboot app**.

## 3. Cấu hình trên VPS Linux (sau này)

Set biến môi trường trước khi chạy:

```bash
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="aiexam.no-reply@gmail.com"
export SMTP_PASSWORD="abcd efgh ijkl mnop"
export SMTP_FROM_NAME="AIEXAM"
streamlit run app.py
```

Hoặc thêm vào systemd service file. Hoặc dùng `.env` + `python-dotenv`.

## 4. Test gửi email cục bộ

```bash
.venv/Scripts/python.exe -c "
import os
os.environ['SMTP_USER'] = 'YOUR@gmail.com'
os.environ['SMTP_PASSWORD'] = 'YOUR_APP_PASSWORD'
from email_otp import send_otp_email
ok, msg = send_otp_email('test_receive@gmail.com', '123456')
print(ok, msg)
"
```

Kết quả `(True, 'Đã gửi OTP đến ...')` = OK.

## 5. Behavior khi chưa cấu hình SMTP

- Form đăng ký sẽ hiện warning vàng: *"Hệ thống chưa cấu hình SMTP..."*
- Khi user click "Gửi mã xác nhận", OTP sẽ hiển thị **TRÊN MÀN HÌNH** (dev mode)
- Đây là fallback an toàn để dev test, KHÔNG dùng cho production

## 6. Giới hạn Gmail SMTP free

| Hạn mức | Số liệu |
|---|---|
| Email/ngày | 500 (rolling 24h) |
| Recipients/email | 500 |
| Connection limit | 100 connections/24h |

Nếu hết quota, Gmail trả lỗi `SMTP-Server busy` → user sẽ thấy thông báo "Lỗi gửi email". Lúc đó cần:
- Đợi 24h cho quota reset, hoặc
- Chuyển sang dịch vụ khác (SendGrid free 100/day, Resend free 100/day, Mailgun free 5000/month)

## 7. Bảo mật

- **KHÔNG commit** SMTP_PASSWORD vào git
- App Password đã commit nhầm → revoke ngay tại [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- Khuyến nghị **tạo Gmail riêng** chỉ dùng cho hệ thống — không dùng email cá nhân
- Định kỳ rotate App Password (3-6 tháng/lần)
