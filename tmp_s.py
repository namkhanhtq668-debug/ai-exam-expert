from pathlib import Path

text = Path("app.py").read_text(encoding="utf-8")
needle = 'with st.spinner("🤖 AI đang soạn giáo án..."):'
start = text.index(needle)
print(text[start:start+600].encode("unicode_escape"))
