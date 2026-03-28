from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")
old = """                html = generate_lesson_plan_html_simple(
                    api_key=api_key_use,
                    cap_hoc=cap_hoc,
                    mon=mon,
                    lop=lop,
                    bo_sach=bo_sach,
                    tuan=int(tuan),
                    tiet=int(tiet),
                    ten_bai=ten_bai.strip(),
                    thoi_luong=int(thoi_luong),
                    si_so=int(si_so),
                    lesson_context=lesson_ctx,
                    teacher_note=teacher_note or "",
                    model_name="gemini-2.0-flash",
                )
                telemetry_service.record_lesson_plan_creation(
                    _current_user_email(),
                    True,
                    {"module": "lesson_plan", "ten_bai": ten_bai.strip()},
                )
                ui.set_html(html, f"GiaoAn_{mon}_{lop}_{ten_bai.strip()}")
                st.success("✔ Đã tạo giáo án!")
"""
new = """                service = _lesson_plan_generation_service()
                html = service.generate_html(
                    cap_hoc=cap_hoc,
                    mon=mon,
                    lop=lop,
                    bo_sach=bo_sach,
                    tuan=int(tuan),
                    tiet=int(tiet),
                    ten_bai=ten_bai.strip(),
                    thoi_luong=int(thoi_luong),
                    si_so=int(si_so),
                    lesson_context=lesson_ctx,
                    teacher_note=teacher_note or "",
                    username=_current_user_email(),
                )
                ui.set_html(html, f"GiaoAn_{mon}_{lop}_{ten_bai.strip()}")
                st.success("✔ Đã tạo giáo án!")
"""
if old not in text:
    raise SystemExit("lesson block not found")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
