import streamlit as st
import os

# Attempt to import the genai client used in your repo (google.generativeai)
try:
    import google.generativeai as genai
except Exception as e:
    genai = None


def _genai_list_models(api_key: str) -> list:
    """Try multiple strategies to enumerate available models for the provided API key.
    Returns a list of model names (strings).
    Uses guarded getattr calls so static analyzers (Pylance) don't flag missing exports.
    """
    if not genai:
        return []

    names: list[str] = []

    # Attempt to configure the client if a configure function exists (guarded)
    try:
        cfg = getattr(genai, "configure", None)
        if callable(cfg):
            try:
                # try calling with keyword first, fall back to single-arg
                try:
                    cfg(api_key=api_key)
                except TypeError:
                    try:
                        cfg(api_key)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # Helper to normalize response items
    def _push_from_response(res):
        if res is None:
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

    # Strategy 1: call list_models if present (via getattr)
    try:
        lm = getattr(genai, "list_models", None)
        if callable(lm):
            try:
                _push_from_response(lm())
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 2: call get_models if present
    try:
        gm = getattr(genai, "get_models", None)
        if callable(gm):
            try:
                _push_from_response(gm())
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 3: inspect genai.client object if available
    try:
        client = getattr(genai, "client", None)
        if client is not None:
            for func_name in ("list_models", "get_models"):
                fn = getattr(client, func_name, None)
                if callable(fn):
                    try:
                        _push_from_response(fn())
                    except Exception:
                        pass
    except Exception:
        pass

    # Strategy 4: scan module attributes for model-like strings
    try:
        for attr in dir(genai):
            if attr.lower().startswith("model"):
                try:
                    val = getattr(genai, attr)
                    if isinstance(val, str) and "gemini" in val.lower():
                        names.append(val)
                except Exception:
                    continue
    except Exception:
        pass

    # Deduplicate while preserving order
    clean: list[str] = []
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
