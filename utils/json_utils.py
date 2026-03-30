import re


def clean_json(text: str) -> str:
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned

