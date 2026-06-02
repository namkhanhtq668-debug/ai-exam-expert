"""Tab 'AI Assistant' – cấu hình key, chạy các hành động AI."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from core.ai import AIConfig, GeminiClient, AIConfigError, AIRequestError, get_default_key_hint
from core.ai_actions import (
    clean_list_items, rewrite_options_consistent, generate_explanations,
    generate_questions, suggest_renames, review_project,
    apply_rename, apply_qbank_proposal,
    RenameProposal, QBankProposal,
)
from core.normalizer import diff_lists, normalize_list_items
from core.project_model import ProjectModel
from utils.paths import BACKUP_DIR

from ui.diff_dialog import DiffApproveDialog


class AIPanel(ttk.Frame):
    def __init__(self, master, app, **kw):
        super().__init__(master, **kw)
        self.app = app
        self.config = AIConfig(api_key="", model="gemini-3.1-flash-lite")
        self._client: GeminiClient | None = None

        self._build_settings()
        self._build_actions()
        self._build_log()

    # ---------- settings ----------
    def _build_settings(self):
        f = ttk.LabelFrame(self, text="Cấu hình Gemini")
        f.pack(fill="x", padx=8, pady=6)

        ttk.Label(f, text="API Key:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.var_key = tk.StringVar(value="")
        self.ent_key = ttk.Entry(f, textvariable=self.var_key, show="*", width=60)
        self.ent_key.grid(row=0, column=1, padx=4, sticky="we")
        self.var_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Hiện", variable=self.var_show,
                        command=self._toggle_show).grid(row=0, column=2, padx=4)

        hint = get_default_key_hint()
        if hint:
            ttk.Label(f, text="(phát hiện GEMINI_API_KEY trong env – có thể dán vào ô trên)",
                      foreground="#666").grid(row=1, column=1, sticky="w")

        ttk.Label(f, text="Model:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.var_model = tk.StringVar(value="gemini-3.1-flash-lite")
        cmb = ttk.Combobox(f, textvariable=self.var_model, width=30,
                   values=["gemini-3.1-flash-lite",
                       "gemini-3.5-flash", "gemini-3.5-flash-lite",
                       "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"])
        cmb.grid(row=2, column=1, padx=4, sticky="w")

        ttk.Button(f, text="Kiểm tra kết nối",
                   command=self._test_connection).grid(row=2, column=2, padx=6)
        f.columnconfigure(1, weight=1)

    def _toggle_show(self):
        self.ent_key.config(show="" if self.var_show.get() else "*")

    def _ensure_client(self) -> GeminiClient | None:
        key = self.var_key.get().strip()
        if not key:
            messagebox.showwarning("Thiếu API key",
                                   "Hãy nhập GEMINI_API_KEY ở trên rồi thử lại.")
            return None
        cfg = AIConfig(api_key=key, model=self.var_model.get().strip() or "gemini-3.1-flash-lite")
        try:
            client = GeminiClient(cfg)
        except AIConfigError as e:
            messagebox.showerror("Lỗi cấu hình AI", str(e))
            return None
        self._client = client
        self.config = cfg
        return client

    def _test_connection(self):
        client = self._ensure_client()
        if not client:
            return
        self._log("Đang kiểm tra kết nối Gemini...")
        def work():
            try:
                txt = client.generate("Trả về duy nhất từ: OK")
                self._log(f"✅ Kết nối OK. Mô hình trả lời: {txt.strip()[:80]}")
            except AIRequestError as e:
                self._log(f"❌ Lỗi gọi Gemini: {e}")
        threading.Thread(target=work, daemon=True).start()

    # ---------- actions ----------
    def _build_actions(self):
        f = ttk.LabelFrame(self, text="Hành động AI")
        f.pack(fill="x", padx=8, pady=6)

        # row 1: list
        ttk.Button(f, text="🧹 Chuẩn hoá list đang chọn (tab List)",
                   width=42, command=self.act_clean_selected_list
                   ).grid(row=0, column=0, padx=6, pady=4, sticky="we")
        ttk.Button(f, text="🧹 Chuẩn hoá TẤT CẢ list",
                   width=30, command=self.act_clean_all_lists
                   ).grid(row=0, column=1, padx=6, pady=4, sticky="we")

        # row 2: qbank
        ttk.Button(f, text="✏️ Đồng văn phong đáp án A-D (mapping hiện tại)",
                   width=42, command=self.act_rewrite_options
                   ).grid(row=1, column=0, padx=6, pady=4, sticky="we")
        ttk.Button(f, text="💡 Sinh giải thích còn trống",
                   width=30, command=self.act_generate_explanations
                   ).grid(row=1, column=1, padx=6, pady=4, sticky="we")

        # row 3: generate questions
        gen = ttk.LabelFrame(f, text="Sinh câu hỏi mới từ chủ đề")
        gen.grid(row=2, column=0, columnspan=2, sticky="we", padx=6, pady=6)
        ttk.Label(gen, text="Chủ đề:").grid(row=0, column=0, sticky="w", padx=4)
        self.var_topic = tk.StringVar()
        ttk.Entry(gen, textvariable=self.var_topic, width=50).grid(row=0, column=1, padx=4)
        ttk.Label(gen, text="Khối/Lớp:").grid(row=0, column=2, sticky="w", padx=4)
        self.var_grade = tk.StringVar()
        ttk.Entry(gen, textvariable=self.var_grade, width=12).grid(row=0, column=3, padx=4)
        ttk.Label(gen, text="Số câu:").grid(row=0, column=4, sticky="w", padx=4)
        self.var_n = tk.IntVar(value=10)
        ttk.Spinbox(gen, from_=1, to=50, textvariable=self.var_n, width=5).grid(row=0, column=5, padx=4)
        self.var_mode = tk.StringVar(value="append")
        ttk.Radiobutton(gen, text="Thêm vào sau", value="append",
                        variable=self.var_mode).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(gen, text="Thay thế toàn bộ", value="replace",
                        variable=self.var_mode).grid(row=1, column=2, sticky="w")
        ttk.Button(gen, text="🎯 Sinh & xem trước",
                   command=self.act_generate_questions
                   ).grid(row=1, column=5, padx=4, pady=4)

        # row 4: rename + review
        ttk.Button(f, text="🏷 Đề xuất đổi tên sprite/biến/list",
                   width=42, command=self.act_suggest_renames
                   ).grid(row=3, column=0, padx=6, pady=4, sticky="we")
        ttk.Button(f, text="📋 Review tổng thể dự án",
                   width=30, command=self.act_review
                   ).grid(row=3, column=1, padx=6, pady=4, sticky="we")

        f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=1)

    # ---------- log ----------
    def _build_log(self):
        f = ttk.LabelFrame(self, text="Nhật ký AI")
        f.pack(fill="both", expand=True, padx=8, pady=6)
        self.log = tk.Text(f, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.config(state="disabled")

    def _log(self, msg: str):
        def _w():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, _w)

    # =========================================================
    # Helpers
    # =========================================================
    def _backup_project_json(self):
        """Lưu snapshot project.json trước khi áp dụng đề xuất AI."""
        if not self.app.bundle:
            return
        import time
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        snap = BACKUP_DIR / f"project_{stamp}.json"
        snap.write_text(json.dumps(self.app.bundle.project, ensure_ascii=False),
                        encoding="utf-8")
        self._log(f"💾 Đã backup project.json → {snap.name}")

    def _need_project(self) -> bool:
        if not self.app.model or not self.app.bundle:
            messagebox.showinfo("Chưa mở dự án",
                                "Hãy mở file .sb3 trước khi dùng AI.")
            return False
        return True

    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    # =========================================================
    # Actions: clean list
    # =========================================================
    def act_clean_selected_list(self):
        if not self._need_project():
            return
        sel = self.app.tv_lists.selection()
        if not sel:
            messagebox.showinfo("Chưa chọn list",
                                "Mở tab 'List' và chọn 1 list trước.")
            return
        target_name, list_id = sel[0].split("|", 1)
        client = self._ensure_client()
        if not client:
            return
        model: ProjectModel = self.app.model
        t = model.target_by_name(target_name)
        payload = (t.get("lists") or {}).get(list_id) if t else None
        if not payload:
            return
        old_items = [str(x) for x in payload[1]]

        self._log(f"⏳ Chuẩn hoá list '{payload[0]}' ({len(old_items)} dòng)...")

        def work():
            try:
                new_items = clean_list_items(client, old_items, capitalize=True)
            except Exception as e:
                self._log(f"❌ {e}")
                return
            rows = [(i, a, b) for (i, a, b) in diff_lists(old_items, new_items)]
            if not rows:
                self._log("✅ Không có thay đổi cần áp dụng.")
                return
            self._log(f"📝 AI đề xuất {len(rows)} dòng đổi. Mở dialog duyệt...")

            def apply_keys(keys: list[int]):
                self._backup_project_json()
                final = old_items[:]
                idx_map = {i: b for (i, _a, b) in rows}
                for i in keys:
                    if i < len(final):
                        final[i] = idx_map[i]
                    else:
                        final.extend([""] * (i - len(final)) + [idx_map[i]])
                model.update_list_items(target_name, list_id, final)
                self.app._refresh_lists()
                self.app._refresh_qbank_preview()
                self._log(f"✅ Đã áp dụng {len(keys)} dòng vào list '{payload[0]}'.")

            self.after(0, lambda: DiffApproveDialog(
                self, f"Chuẩn hoá list: {payload[0]}",
                [(i, a, b) for (i, a, b) in rows], apply_keys,
                col_key="Dòng"))

        self._run_bg(work)

    def act_clean_all_lists(self):
        if not self._need_project():
            return
        client = self._ensure_client()
        if not client:
            return
        if not messagebox.askyesno(
                "Xác nhận",
                "Sẽ gọi Gemini cho TỪNG list trong dự án. Có thể tốn nhiều thời gian + token. "
                "Tiếp tục?"):
            return
        model: ProjectModel = self.app.model

        def work():
            proposals: list[tuple] = []  # (target, list_id, list_name, old, new)
            for le in model.iter_lists():
                old_items = [str(x) for x in le.items]
                if not old_items:
                    continue
                self._log(f"⏳ {le.target_name} / {le.name}...")
                try:
                    new_items = clean_list_items(client, old_items, capitalize=True)
                except Exception as e:
                    self._log(f"  ❌ {e}")
                    continue
                changes = diff_lists(old_items, new_items)
                if changes:
                    proposals.append((le.target_name, le.list_id, le.name,
                                      old_items, new_items, changes))
            if not proposals:
                self._log("✅ Không có thay đổi.")
                return
            # gộp tất cả thành 1 dialog
            flat_rows = []
            keymap = {}
            for p_idx, (tn, lid, lname, oi, ni, ch) in enumerate(proposals):
                for (i, a, b) in ch:
                    k = (p_idx, i)
                    flat_rows.append((k, a, b))
                    keymap[k] = (tn, lid, i, b)

            def apply_keys(keys):
                self._backup_project_json()
                # gom theo (tn,lid)
                updates: dict[tuple, dict[int, str]] = {}
                for k in keys:
                    tn, lid, i, b = keymap[k]
                    updates.setdefault((tn, lid), {})[i] = b
                for (tn, lid), changes_map in updates.items():
                    t = model.target_by_name(tn)
                    if not t:
                        continue
                    payload = (t.get("lists") or {}).get(lid)
                    if not payload:
                        continue
                    cur = list(payload[1])
                    for i, val in changes_map.items():
                        while i >= len(cur):
                            cur.append("")
                        cur[i] = val
                    payload[1] = cur
                self.app._refresh_lists()
                self.app._refresh_qbank_preview()
                self._log(f"✅ Đã áp dụng {len(keys)} thay đổi.")

            display_rows = [(f"{keymap[k][0]} / {keymap[k][1][:8]} : {keymap[k][2]}", a, b)
                            for (k, a, b) in flat_rows]
            # cần giữ key gốc cho on_apply
            self.after(0, lambda: DiffApproveDialog(
                self, "Chuẩn hoá tất cả list",
                [(flat_rows[i][0], display_rows[i][1], display_rows[i][2])
                 for i in range(len(flat_rows))],
                apply_keys, col_key="Vị trí"))

        self._run_bg(work)

    # =========================================================
    # Actions: qbank
    # =========================================================
    def _current_mapping(self):
        m = self.app._current_qbank_mapping()
        if not m:
            messagebox.showinfo("Chưa chọn ngân hàng",
                                "Vào tab 'Ngân hàng câu hỏi' và chọn mapping trước.")
            return None
        return m

    def _get_list_items(self, target_name: str, list_id: str) -> list[str]:
        t = self.app.model.target_by_name(target_name)
        if not t:
            return []
        payload = (t.get("lists") or {}).get(list_id)
        return [str(x) for x in (payload[1] if payload else [])]

    def _find_col_id(self, mapping, *candidates) -> str | None:
        for cand in candidates:
            for col, lid in mapping.columns.items():
                if col.lower() == cand.lower():
                    return lid
        return None

    def act_rewrite_options(self):
        if not self._need_project():
            return
        mapping = self._current_mapping()
        if not mapping:
            return
        ids = {k: self._find_col_id(mapping, k, f"dap_an_{k.lower()}")
               for k in ("A", "B", "C", "D")}
        q_id = self._find_col_id(mapping, "cau_hoi", "question")
        if not q_id or not all(ids.values()):
            messagebox.showerror(
                "Thiếu cột",
                "Mapping cần có: cau_hoi, dap_an_a, dap_an_b, dap_an_c, dap_an_d.")
            return
        client = self._ensure_client()
        if not client:
            return

        Q = self._get_list_items(mapping.target_name, q_id)
        A = self._get_list_items(mapping.target_name, ids["A"])
        B = self._get_list_items(mapping.target_name, ids["B"])
        C = self._get_list_items(mapping.target_name, ids["C"])
        D = self._get_list_items(mapping.target_name, ids["D"])

        self._log(f"⏳ Đồng văn phong cho {min(len(Q),len(A),len(B),len(C),len(D))} câu...")

        def work():
            try:
                res = rewrite_options_consistent(client, Q, A, B, C, D)
            except Exception as e:
                self._log(f"❌ {e}")
                return
            rows = []
            for letter in ("A", "B", "C", "D"):
                old = [A, B, C, D][("A", "B", "C", "D").index(letter)]
                new = res[letter]
                for (i, a, b) in diff_lists(old, new):
                    rows.append(((letter, i), f"{letter}#{i}: {a}", b))
            if not rows:
                self._log("✅ Không có thay đổi.")
                return

            def apply_keys(keys):
                self._backup_project_json()
                kset = set(keys)
                model = self.app.model
                for letter, lid in ids.items():
                    old = self._get_list_items(mapping.target_name, lid)
                    new_full = old[:]
                    new_vals = res[letter]
                    for i in range(min(len(old), len(new_vals))):
                        if (letter, i) in kset:
                            new_full[i] = new_vals[i]
                    model.update_list_items(mapping.target_name, lid, new_full)
                self.app._refresh_lists()
                self.app._refresh_qbank_preview()
                self._log(f"✅ Áp dụng {len(keys)} thay đổi đáp án.")

            self.after(0, lambda: DiffApproveDialog(
                self, "Đồng văn phong đáp án A-D", rows, apply_keys, col_key="Đáp án"))

        self._run_bg(work)

    def act_generate_explanations(self):
        if not self._need_project():
            return
        mapping = self._current_mapping()
        if not mapping:
            return
        q_id = self._find_col_id(mapping, "cau_hoi", "question")
        e_id = self._find_col_id(mapping, "giai_thich", "giai_thich_dap_an", "explain")
        correct_id = self._find_col_id(mapping, "dap_an_dung", "correct")
        if not all([q_id, e_id, correct_id]):
            messagebox.showerror("Thiếu cột",
                                 "Cần có cột cau_hoi, dap_an_dung, giai_thich.")
            return
        client = self._ensure_client()
        if not client:
            return

        Q = self._get_list_items(mapping.target_name, q_id)
        E = self._get_list_items(mapping.target_name, e_id)
        cor = self._get_list_items(mapping.target_name, correct_id)
        opts = {}
        for letter in ("A", "B", "C", "D"):
            lid = self._find_col_id(mapping, f"dap_an_{letter.lower()}")
            opts[letter] = self._get_list_items(mapping.target_name, lid) if lid else []

        while len(E) < len(Q):
            E.append("")

        self._log(f"⏳ Sinh giải thích cho {sum(1 for x in E if not x.strip())} ô trống...")

        def work():
            try:
                new_E = generate_explanations(client, Q, opts, cor, E)
            except Exception as e:
                self._log(f"❌ {e}")
                return
            rows = [(i, a, b) for (i, a, b) in diff_lists(E, new_E)]
            if not rows:
                self._log("✅ Không có giải thích mới (có thể đã đầy).")
                return

            def apply_keys(keys):
                self._backup_project_json()
                kset = set(keys)
                final = E[:]
                idx_map = {i: b for (i, _a, b) in rows}
                for i in kset:
                    if i < len(final):
                        final[i] = idx_map[i]
                self.app.model.update_list_items(mapping.target_name, e_id, final)
                self.app._refresh_lists()
                self.app._refresh_qbank_preview()
                self._log(f"✅ Đã thêm giải thích cho {len(keys)} câu.")

            self.after(0, lambda: DiffApproveDialog(
                self, "Giải thích sinh bởi AI", rows, apply_keys, col_key="Câu #"))

        self._run_bg(work)

    def act_generate_questions(self):
        if not self._need_project():
            return
        mapping = self._current_mapping()
        if not mapping:
            return
        topic = self.var_topic.get().strip()
        if not topic:
            messagebox.showinfo("Thiếu chủ đề", "Nhập chủ đề ở khung 'Sinh câu hỏi mới'.")
            return
        n = max(1, min(50, int(self.var_n.get())))
        client = self._ensure_client()
        if not client:
            return
        cols = list(mapping.columns.keys())
        self._log(f"⏳ Sinh {n} câu hỏi về '{topic}'...")

        def work():
            try:
                rows = generate_questions(client, topic, n, cols,
                                          grade_hint=self.var_grade.get().strip())
            except Exception as e:
                self._log(f"❌ {e}")
                return
            if not rows:
                self._log("❌ AI không trả về câu hỏi nào.")
                return
            self._log(f"📝 Nhận được {len(rows)} câu. Mở dialog xem trước...")

            # diff dialog: hiện từng câu (cau_hoi → ABCD + đáp án đúng)
            display = []
            for i, r in enumerate(rows):
                key = i
                summary = (f"{r.get('cau_hoi','')}\n"
                           f"  A. {r.get('dap_an_a','')}\n"
                           f"  B. {r.get('dap_an_b','')}\n"
                           f"  C. {r.get('dap_an_c','')}\n"
                           f"  D. {r.get('dap_an_d','')}\n"
                           f"  → {r.get('dap_an_dung','')}")
                display.append((key, "(mới)", summary))

            mode = self.var_mode.get()

            def apply_keys(keys):
                self._backup_project_json()
                chosen = [rows[i] for i in keys]
                if not chosen:
                    return
                prop = QBankProposal(target_name=mapping.target_name,
                                     columns=dict(mapping.columns),
                                     rows=chosen, mode=mode)
                written = apply_qbank_proposal(self.app.model, prop)
                self.app._refresh_lists()
                self.app._refresh_qbank_preview()
                detail = ", ".join(f"{k}:{v}" for k, v in written.items())
                self._log(f"✅ Đã ghi {len(chosen)} câu ({mode}). [{detail}]")

            self.after(0, lambda: DiffApproveDialog(
                self, f"Câu hỏi AI tạo về '{topic}'", display, apply_keys,
                col_old="(trước đó: chưa có)", col_new="Câu hỏi đề xuất",
                col_key="Câu #"))

        self._run_bg(work)

    # =========================================================
    # Actions: rename + review
    # =========================================================
    def act_suggest_renames(self):
        if not self._need_project():
            return
        client = self._ensure_client()
        if not client:
            return
        self._log("⏳ AI đang đề xuất tên...")

        def work():
            try:
                proposals = suggest_renames(client, self.app.model)
            except Exception as e:
                self._log(f"❌ {e}")
                return
            if not proposals:
                self._log("✅ Không có đề xuất đổi tên.")
                return

            rows = [(i, f"[{p.kind}] {p.target_name}/{p.old_name}".strip("/"),
                     p.new_name)
                    for i, p in enumerate(proposals)]

            def apply_keys(keys):
                self._backup_project_json()
                applied = 0
                for i in keys:
                    if apply_rename(self.app.model, proposals[i]):
                        applied += 1
                self.app._refresh_all_tabs()
                self._log(f"✅ Đã đổi tên {applied}/{len(keys)} mục.")

            self.after(0, lambda: DiffApproveDialog(
                self, "Đề xuất đổi tên (AI)", rows, apply_keys,
                col_old="Hiện tại", col_new="Đề xuất", col_key="Đối tượng"))

        self._run_bg(work)

    def act_review(self):
        if not self._need_project():
            return
        client = self._ensure_client()
        if not client:
            return
        self._log("⏳ AI đang review dự án...")

        # gom mẫu qbank nếu có
        sample = None
        mappings = self.app.qbank_mappings
        if mappings:
            m = mappings[0]
            from core.qbank import render_preview
            tbl = render_preview(self.app.model, m, max_rows=5)
            if tbl:
                hdr = tbl[0]
                sample = [dict(zip(hdr, r)) for r in tbl[1:]]

        def work():
            try:
                rev = review_project(client, self.app.model, sample)
            except Exception as e:
                self._log(f"❌ {e}")
                return
            msg = ("📋 TỔNG QUAN\n" + rev.summary +
                   "\n\n💡 GỢI Ý:\n" + "\n".join(f"  • {s}" for s in rev.suggestions) +
                   "\n\n⚠️ VẤN ĐỀ:\n" + "\n".join(f"  • {s}" for s in rev.issues))
            self._log(msg)

        self._run_bg(work)
