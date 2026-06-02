"""Test access to a specific Gemini model using your API key.

Usage:
- Set `GEMINI_API_KEY` in your environment, or pass it interactively.
- Run: `python tools/test_gemini_model.py`

The script will attempt a minimal text generation call to the given model and print the outcome.
"""
import os
import sys

try:
    import google.generativeai as genai
except Exception as e:
    print("google.generativeai (genai) client is not installed or import failed:", e)
    sys.exit(1)

MODEL_NAME = os.environ.get("TEST_GEMINI_MODEL", "gemini-3.5-flash-lite")
API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    API_KEY = input("Enter GEMINI/Google API key (won't be stored): ").strip()
    if not API_KEY:
        print("No API key provided. Aborting.")
        sys.exit(1)

# configure client (guarded)
cfg = getattr(genai, "configure", None)
if callable(cfg):
    try:
        cfg(api_key=API_KEY)
    except TypeError:
        try:
            cfg(API_KEY)
        except Exception:
            pass

print(f"Testing access to model: {MODEL_NAME}")

# Minimal test call (guarded against different client APIs)
# Try genai.generate, genai.create, or genai.client.predict variants.
success = False
errors = []

# Strategy 1: genai.generate (newer API may use genai.generate)
try:
    fn = getattr(genai, "generate", None)
    if callable(fn):
        try:
            resp = fn(model=MODEL_NAME, input="Trả về duy nhất chữ: OK")
            print("Response (generate):", getattr(resp, 'content', resp))
            success = True
        except Exception as e:
            errors.append(("generate", str(e)))
except Exception:
    pass

# Strategy 2: genai.create() on text generation
if not success:
    try:
        fn = getattr(genai, "create", None)
        if callable(fn):
            try:
                resp = fn(model=MODEL_NAME, prompt="OK")
                print("Response (create):", resp)
                success = True
            except Exception as e:
                errors.append(("create", str(e)))
    except Exception:
        pass

# Strategy 3: client-based predict
if not success:
    try:
        client = getattr(genai, "client", None)
        if client is not None:
            fn = getattr(client, "predict", None) or getattr(client, "generate", None)
            if callable(fn):
                try:
                    resp = fn(model=MODEL_NAME, input="OK")
                    print("Response (client):", resp)
                    success = True
                except Exception as e:
                    errors.append(("client", str(e)))
    except Exception:
        pass

if success:
    print("SUCCESS: The API key can access the model (or returned a response).")
else:
    print("FAILED: Could not get a successful response from the model.")
    print("Errors encountered:")
    for k, v in errors:
        print(f" - {k}: {v}")
    print('\nIf you see 404 or permission errors, your key likely cannot access this model.\n')
