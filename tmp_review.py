import re

yccd = "Đếm, đọc, viết được các số trong phạm vi 100."


def norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower(), flags=re.UNICODE)


yccd_norm = norm(yccd)
keywords = [term for term in yccd_norm.split() if len(term) >= 4][:8]
print(keywords)
