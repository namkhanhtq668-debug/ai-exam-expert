from pathlib import Path

text = Path("app.py").read_text(encoding="utf-8")
needle = 'with st.spinner("🤖 AI đang soạn giáo án..."):'
start = text.index(needle)
end = text.index("st.success", start)
print(text[start:end].encode("unicode_escape"))
