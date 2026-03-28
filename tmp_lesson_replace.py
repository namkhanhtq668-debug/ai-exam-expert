from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")
start = text.index("                html = generate_lesson_plan_html_simple(")
end = text.index("                ui.set_html", start)
new_block = '''                service = _lesson_plan_generation_service()
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
'''
text = text[:start] + new_block + text[end:]
path.write_text(text, encoding="utf-8")
