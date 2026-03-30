# AI Exam Expert

Streamlit multi-agent app for lesson generation, chat, documents, mindmaps, and exam workflows.

## Local setup

1. Create a clean Python 3.12 virtual environment:

```powershell
C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe -m venv --clear .venv
```

2. Install dependencies:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Copy env example and fill local secrets:

```powershell
copy .env.example .env
```

4. Run the app:

```powershell
streamlit run app.py
```

## Streamlit Cloud setup

1. Push the repo with `requirements.txt` and `app.py` at the root.
2. Set Python version to 3.10-3.12 in Streamlit Cloud if configurable.
3. Add secrets in the Cloud dashboard instead of committing `.env`.
4. Keep the following keys configured:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `GOOGLE_API_KEY`
   - `OPENAI_API_KEY`
   - `SEPAY_API_TOKEN`
   - `AI_EXAM_LLM_PROVIDER`
   - `AI_EXAM_AUDIT_ENABLED`
   - `AI_EXAM_AUDIT_LOG_FILE`
   - `AI_EXAM_SMALL_MODEL`
   - `AI_EXAM_LARGE_MODEL`
   - `AI_EXAM_LLM_TIMEOUT_SECONDS`

## Notes

- `app.py` loads `.env` locally and falls back to `st.secrets` in Streamlit Cloud.
- `orchestrator.orchestrator.MultiAgentOrchestrator` is the canonical import path.
- `agents.orchestrator` remains as a compatibility shim for older imports.
- `flask` is not imported anywhere in the repo, so it is not required in `requirements.txt`.
