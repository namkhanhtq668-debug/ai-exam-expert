import streamlit as st
import os

# Attempt to import the genai client used in your repo (google.generativeai)
try:
    import google.generativeai as genai
except Exception as e:
    genai = None


def _genai_list_models(api_key: str) -> list:
    """Try multiple strategies to enumerate available models for the provided API key.
    Returns a list of model names (strings)."""
    if not genai:
        return []

    names = []

    # Try configuring the client if available
    try:
        # some versions expose configure or configure(api_key=...)
        if hasattr(genai, "configure"):
            try:
                genai.configure(api_key=api_key)
            except TypeError:
                # older signature
                genai.configure(api_key)
    except Exception:
        pass

    # Strategy 1: genai.list_models()
    try:
        if hasattr(genai, "list_models"):
            res = genai.list_models()
            # res may be list or object
            if isinstance(res, (list, tuple)):
                for m in res:
                    if isinstance(m, dict) and "name" in m:
                        names.append(m["name"])
                    else:
                        names.append(getattr(m, "name", str(m)))
            elif hasattr(res, "models"):
                for m in getattr(res, "models"):
                    names.append(getattr(m, "name", str(m)))
    except Exception:
        pass

    # Strategy 2: genai.get_models()
    try:
        if hasattr(genai, "get_models"):
            res = genai.get_models()
            if isinstance(res, (list, tuple)):
                for m in res:
                    names.append(getattr(m, "name", str(m)))
            elif hasattr(res, "models"):
                for m in getattr(res, "models"):
                    names.append(getattr(m, "name", str(m)))
    except Exception:
        pass

    # Strategy 3: inspect client attribute
    try:
        client = getattr(genai, "client", None)
        if client is not None:
            # Try list_models on client
            if hasattr(client, "list_models"):
                try:
                    res = client.list_models()
                    # Try to extract
                    for item in getattr(res, "models", []) or res:
                        names.append(getattr(item, "name", str(item)))
                except Exception:
                    pass
            # Try get_models
            if hasattr(client, "get_models"):
                try:
                    res = client.get_models()
                    for item in getattr(res, "models", []) or res:
                        names.append(getattr(item, "name", str(item)))
                except Exception:
                    pass
    except Exception:
        pass

    # Strategy 4: check constants or attributes in genai module
    try:
        for attr in dir(genai):
            if attr.lower().startswith("model"):
                val = getattr(genai, attr)
                if isinstance(val, str) and "gemini" in val.lower():
                    names.append(val)
    except Exception:
        pass

    # Deduplicate and sort
    clean = []
    for n in names:
        if not n:
            continue
        s = str(n)
        if s not in clean:
            clean.append(s)
    return clean


st.title("Gemini Model Probe — AIEXAM helper")
st.markdown("Use this small helper to check which Gemini model names your API key can access.")

api_key = st.text_input("GEMINI / GOOGLE API key", value=os.environ.get("GEMINI_API_KEY", ""), type="password")
if st.button("List available models"):
    if not api_key:
        st.error("Please provide an API key (or set GEMINI_API_KEY in env).")
    else:
        with st.spinner("Querying client for available models..."):
            try:
                names = _genai_list_models(api_key)
                if not names:
                    st.warning("Không tìm thấy mô hình nào — thử kiểm tra quyền/SDK hoặc dùng model name bạn biết.")
                else:
                    st.success(f"Tìm thấy {len(names)} mô hình")
                    st.write(names)
            except Exception as e:
                st.error(f"Lỗi khi truy vấn mô hình: {e}")

st.markdown("If you get an empty list but your key works, try passing a known model name like 'gemini-3.1-flash-lite' when calling the API.")
