"""Các hành động AI cấp cao cho dự án Scratch.

Mọi hành động trả về DỮ LIỆU ĐỀ XUẤT (proposal), KHÔNG tự ghi vào project.
UI nhận proposal, hiển thị diff, người dùng duyệt rồi mới áp dụng.

Nguyên tắc an toàn:
- Không động vào blocks, broadcast id, asset md5, toạ độ sprite.
- Chỉ sửa: text trong list, giá trị biến (tuỳ chọn), tên hiển thị sprite/biến/list.
- Mọi prompt yêu cầu Gemini trả JSON đúng schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.ai import GeminiClient
from core.normalizer import normalize_text, normalize_list_items
from core.project_model import ProjectModel


# ---------------- Proposal dataclasses ----------------

@dataclass
class ListEditProposal:
    target_name: str
    list_id: str
    list_name: str
    old_items: list[str]
    new_items: list[str]
    note: str = ""


@dataclass
class RenameProposal:
    kind: str  # "sprite" | "variable" | "list"
    target_name: str
    old_name: str
    new_name: str
    object_id: str = ""  # var_id / list_id (rỗng với sprite)


@dataclass
class QBankProposal:
    target_name: str
    columns: dict[str, str]   # column -> list_id
    rows: list[dict[str, str]]  # mỗi row là dict column->value
    mode: str = "append"  # "append" | "replace"


@dataclass
class ProjectReview:
    summary: str
    suggestions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


# ---------------- Actions ----------------

SYS_VN_EDITOR = (
    "Bạn là biên tập viên tiếng Việt cho phần mềm giáo dục (Scratch). "
    "Sửa chính tả, dấu câu, viết hoa đầu câu, chuẩn Unicode tiếng Việt. "
    "TUYỆT ĐỐI giữ nguyên ý nghĩa, không thêm/bớt nội dung. "
    "Luôn trả lời bằng JSON đúng schema yêu cầu, không kèm giải thích."
)


def clean_list_items(client: GeminiClient, items: list[str],
                     capitalize: bool = True) -> list[str]:
    """Yêu cầu AI sửa chính tả + chuẩn hoá cho từng dòng. Giữ nguyên số dòng."""
    if not items:
        return []
    # Tiền chuẩn hoá để giảm việc của AI
    pre = normalize_list_items([str(x) for x in items], capitalize=False)
    prompt = (
        "Sửa chính tả và chuẩn hoá tiếng Việt cho mảng sau. "
        "Trả về JSON dạng {\"items\": [..]} với CÙNG SỐ PHẦN TỬ theo đúng thứ tự. "
        f"Mảng: {pre!r}"
    )
    data = client.generate_json(prompt, system=SYS_VN_EDITOR)
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError("AI không trả về schema {items: [...]}")
    out = [normalize_text(str(x)) for x in data["items"]]
    # nếu AI làm lệch độ dài, pad/cắt để khớp
    if len(out) < len(items):
        out.extend(pre[len(out):])
    elif len(out) > len(items):
        out = out[:len(items)]
    if capitalize:
        out = [s[0].upper() + s[1:] if s and s[0].islower() else s for s in out]
    return out


def rewrite_options_consistent(client: GeminiClient,
                               questions: list[str],
                               options_a: list[str], options_b: list[str],
                               options_c: list[str], options_d: list[str]
                               ) -> dict[str, list[str]]:
    """Đồng văn phong 4 đáp án A-D cho mỗi câu hỏi, giữ đáp án đúng nguyên nghĩa."""
    n = min(len(questions), len(options_a), len(options_b),
            len(options_c), len(options_d))
    payload = [
        {"q": questions[i], "A": options_a[i], "B": options_b[i],
         "C": options_c[i], "D": options_d[i]}
        for i in range(n)
    ]
    prompt = (
        "Với mỗi câu, viết lại 4 đáp án A-D cho ĐỒNG văn phong và độ dài tương đương, "
        "KHÔNG đổi đáp án đúng, không thêm thông tin mới. "
        "Trả JSON: {\"items\":[{\"A\":..,\"B\":..,\"C\":..,\"D\":..}, ...]} "
        "đúng thứ tự câu hỏi.\n\n"
        f"Dữ liệu:\n{payload}"
    )
    data = client.generate_json(prompt, system=SYS_VN_EDITOR)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) != n:
        raise ValueError("AI không trả đúng số dòng.")
    A = options_a.copy(); B = options_b.copy()
    C = options_c.copy(); D = options_d.copy()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        A[i] = normalize_text(str(it.get("A", A[i])))
        B[i] = normalize_text(str(it.get("B", B[i])))
        C[i] = normalize_text(str(it.get("C", C[i])))
        D[i] = normalize_text(str(it.get("D", D[i])))
    return {"A": A, "B": B, "C": C, "D": D}


def generate_explanations(client: GeminiClient,
                          questions: list[str],
                          options_by_letter: dict[str, list[str]],
                          correct: list[str],
                          existing_explanations: list[str]
                          ) -> list[str]:
    """Điền giải thích cho ô trống, giữ nguyên ô đã có nội dung."""
    n = len(questions)
    items = []
    for i in range(n):
        if existing_explanations[i] and existing_explanations[i].strip():
            items.append({"i": i, "skip": True})
            continue
        items.append({
            "i": i,
            "q": questions[i],
            "A": options_by_letter["A"][i] if i < len(options_by_letter["A"]) else "",
            "B": options_by_letter["B"][i] if i < len(options_by_letter["B"]) else "",
            "C": options_by_letter["C"][i] if i < len(options_by_letter["C"]) else "",
            "D": options_by_letter["D"][i] if i < len(options_by_letter["D"]) else "",
            "correct": correct[i] if i < len(correct) else "",
        })
    todo = [it for it in items if not it.get("skip")]
    if not todo:
        return existing_explanations[:]
    prompt = (
        "Viết giải thích NGẮN GỌN (1-2 câu, tiếng Việt) cho mỗi câu trắc nghiệm sau, "
        "nêu rõ vì sao đáp án đúng là đúng. KHÔNG nhắc lại nguyên văn câu hỏi. "
        "Trả JSON: {\"items\":[{\"i\":..,\"explain\":\"...\"}, ...]}.\n\n"
        f"Dữ liệu:\n{todo}"
    )
    data = client.generate_json(prompt, system=SYS_VN_EDITOR)
    out = existing_explanations[:]
    for entry in (data.get("items") or []):
        idx = entry.get("i")
        text = entry.get("explain", "")
        if isinstance(idx, int) and 0 <= idx < n:
            out[idx] = normalize_text(str(text))
    return out


def generate_questions(client: GeminiClient, topic: str, n: int,
                       columns: list[str], grade_hint: str = "") -> list[dict]:
    """Sinh n câu hỏi trắc nghiệm theo cấu trúc cột cho trước.

    `columns` phải bao gồm ít nhất: cau_hoi, dap_an_a, dap_an_b, dap_an_c,
    dap_an_d, dap_an_dung. Có thể có thêm giai_thich.
    """
    required = {"cau_hoi", "dap_an_a", "dap_an_b", "dap_an_c",
                "dap_an_d", "dap_an_dung"}
    missing = required - set(c.lower() for c in columns)
    if missing:
        raise ValueError(
            "Mapping ngân hàng câu hỏi thiếu cột: " + ", ".join(sorted(missing))
            + "\nCần đủ: cau_hoi, dap_an_a, dap_an_b, dap_an_c, dap_an_d, dap_an_dung"
        )
    has_explain = any(c.lower() in ("giai_thich", "giai_thich_dap_an") for c in columns)
    grade = f" ({grade_hint})" if grade_hint else ""
    prompt = (
        f"Tạo {n} câu hỏi trắc nghiệm 4 đáp án về chủ đề: \"{topic}\"{grade}.\n"
        "Mỗi câu có một đáp án đúng duy nhất. Đáp án đúng ghi 'A'/'B'/'C'/'D'.\n"
        + ("Kèm cột giai_thich (1-2 câu) cho mỗi câu.\n" if has_explain else "")
        + "Trả JSON: {\"items\":[{\"cau_hoi\":..,\"dap_an_a\":..,\"dap_an_b\":..,"
        "\"dap_an_c\":..,\"dap_an_d\":..,\"dap_an_dung\":..,\"giai_thich\":..}, ...]}"
    )
    data = client.generate_json(prompt, system=SYS_VN_EDITOR)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("AI không trả mảng items.")
    cleaned = []
    for it in items:
        if not isinstance(it, dict):
            continue
        row = {}
        for c in columns:
            key = c.lower()
            val = it.get(key) or it.get(c) or ""
            row[c] = normalize_text(str(val))
        # chuẩn hoá đáp án đúng: 1/2/3/4 -> A/B/C/D
        for c in columns:
            if c.lower() == "dap_an_dung":
                v = row[c].strip().upper()
                mapping = {"1": "A", "2": "B", "3": "C", "4": "D"}
                row[c] = mapping.get(v, v)
        cleaned.append(row)
    return cleaned[:n]


def suggest_renames(client: GeminiClient, model: ProjectModel) -> list[RenameProposal]:
    """AI đề xuất tên tiếng Việt dễ hiểu cho sprite/biến/list."""
    sprites = [t.get("name", "") for t in model.sprites()]
    variables = [(v.target_name, v.var_id, v.name)
                 for v in model.iter_variables()
                 if not v.name.startswith("_")]
    lists = [(le.target_name, le.list_id, le.name) for le in model.iter_lists()]
    prompt = (
        "Đề xuất tên tiếng Việt rõ nghĩa cho các đối tượng Scratch dưới đây. "
        "Tên mới phải ngắn, không dấu phụ thừa, không chứa ký tự đặc biệt ngoài chữ/số/dấu gạch dưới. "
        "Chỉ đề xuất khi tên cũ KHÔNG đủ rõ; giữ nguyên những tên đã tốt (bằng cách bỏ ra ngoài kết quả).\n"
        "Trả JSON: {\"sprites\":[{\"old\":..,\"new\":..}], "
        "\"variables\":[{\"target\":..,\"id\":..,\"old\":..,\"new\":..}], "
        "\"lists\":[{\"target\":..,\"id\":..,\"old\":..,\"new\":..}]}.\n\n"
        f"sprites={sprites}\nvariables={variables}\nlists={lists}"
    )
    data = client.generate_json(prompt, system=SYS_VN_EDITOR)
    out: list[RenameProposal] = []
    for s in (data.get("sprites") or []):
        old = str(s.get("old", "")); new = normalize_text(str(s.get("new", "")))
        if old and new and old != new:
            out.append(RenameProposal("sprite", "", old, new))
    for v in (data.get("variables") or []):
        old = str(v.get("old", "")); new = normalize_text(str(v.get("new", "")))
        if old and new and old != new:
            out.append(RenameProposal(
                "variable", str(v.get("target", "")), old, new,
                object_id=str(v.get("id", ""))))
    for l in (data.get("lists") or []):
        old = str(l.get("old", "")); new = normalize_text(str(l.get("new", "")))
        if old and new and old != new:
            out.append(RenameProposal(
                "list", str(l.get("target", "")), old, new,
                object_id=str(l.get("id", ""))))
    return out


def review_project(client: GeminiClient, model: ProjectModel,
                   qbank_sample: list[dict] | None = None) -> ProjectReview:
    sprites = [t.get("name", "") for t in model.sprites()]
    stage = model.stage()
    backdrops = ([c.get("name", "") for c in stage.get("costumes", [])]
                 if stage else [])
    vars_ = [v.name for v in model.iter_variables() if not v.name.startswith("_")]
    lists_ = [(le.name, len(le.items)) for le in model.iter_lists()]
    bcasts = [b.name for b in model.iter_broadcasts()]
    qb_text = ""
    if qbank_sample:
        qb_text = f"\nMẫu câu hỏi (tối đa 5 dòng đầu): {qbank_sample[:5]}"
    prompt = (
        "Đánh giá tổng thể dự án Scratch dùng cho dạy/thi với góc nhìn sư phạm + "
        "kỹ thuật. Đưa ra summary 2-3 câu, danh sách suggestions (mỗi mục 1 câu), "
        "và issues (vấn đề cần sửa). "
        "Trả JSON: {\"summary\":\"...\",\"suggestions\":[..],\"issues\":[..]}.\n\n"
        f"Sprites: {sprites}\nBackdrops: {backdrops}\nVariables: {vars_}\n"
        f"Lists: {lists_}\nBroadcasts: {bcasts}{qb_text}"
    )
    data = client.generate_json(prompt, system=SYS_VN_EDITOR)
    return ProjectReview(
        summary=str(data.get("summary", "")),
        suggestions=[str(x) for x in (data.get("suggestions") or [])],
        issues=[str(x) for x in (data.get("issues") or [])],
    )


# ---------------- Apply ----------------

def apply_list_edit(model: ProjectModel, p: ListEditProposal) -> bool:
    return model.update_list_items(p.target_name, p.list_id, p.new_items)


def apply_rename(model: ProjectModel, p: RenameProposal) -> bool:
    if p.kind == "sprite":
        t = model.target_by_name(p.old_name)
        if not t:
            return False
        t["name"] = p.new_name
        return True
    if p.kind == "variable":
        t = model.target_by_name(p.target_name)
        if not t:
            return False
        v = (t.get("variables") or {}).get(p.object_id)
        if not v:
            return False
        v[0] = p.new_name
        return True
    if p.kind == "list":
        t = model.target_by_name(p.target_name)
        if not t:
            return False
        lst = (t.get("lists") or {}).get(p.object_id)
        if not lst:
            return False
        lst[0] = p.new_name
        return True
    return False


def apply_qbank_proposal(model: ProjectModel, p: QBankProposal) -> dict[str, int]:
    """Ghi các dòng câu hỏi mới vào các list trong target. mode=append/replace."""
    t = model.target_by_name(p.target_name)
    if not t:
        raise ValueError(f"Không tìm thấy target '{p.target_name}'")
    lists = t.setdefault("lists", {})
    written: dict[str, int] = {}
    for col, lid in p.columns.items():
        payload = lists.get(lid)
        if not payload:
            lists[lid] = [col, []]
            payload = lists[lid]
        new_values = [row.get(col, "") for row in p.rows]
        if p.mode == "replace":
            payload[1] = new_values
        else:
            payload[1] = list(payload[1]) + new_values
        written[col] = len(new_values)
    return written
