"""Cửa sổ chính ứng dụng Scratch Editor (tkinter, tiếng Việt)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.sb3_io import Sb3Bundle, Sb3LoadError
from core.project_model import ProjectModel
from core.assets import prepare_backdrop, prepare_sprite_costume
from core.linter import Linter, format_issues
from core.sb3_repair import (
    repair_project_dict, repair_sb3_from_disk, format_report,
)
from core.qbank import (
    discover_question_lists, export_to_csv, import_from_csv,
    render_preview, QBankMapping,
)
from utils.paths import ensure_workspace, OUTPUT_DIR, cleanup_temp

from ui.stage_view import StageView
from ui.dialogs import ListEditorDialog, VariableEditDialog
from ui.ai_panel import AIPanel

APP_TITLE = "Scratch Editor – Công cụ chỉnh sửa dự án Scratch (.sb3)"


class ScratchEditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(1100, 720)

        ensure_workspace()
        cleanup_temp(keep_latest=5)

        self.bundle: Sb3Bundle | None = None
        self.model: ProjectModel | None = None
        self._hide_raw_vars = tk.BooleanVar(value=True)

        self._build_menu()
        self._build_layout()
        self._set_status("Sẵn sàng. Hãy mở file .sb3 để bắt đầu.")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- menu ----------
    def _build_menu(self):
        menubar = tk.Menu(self)

        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="Mở .sb3...", accelerator="Ctrl+O",
                           command=self.open_sb3)
        m_file.add_command(label="Xuất .sb3 mới...", accelerator="Ctrl+S",
                           command=self.export_sb3)
        m_file.add_separator()
        m_file.add_command(label="Mở thư mục Output",
                           command=lambda: self._open_in_explorer(OUTPUT_DIR))
        m_file.add_separator()
        m_file.add_command(label="Thoát", command=self._on_close)
        menubar.add_cascade(label="Tập tin", menu=m_file)

        m_tools = tk.Menu(menubar, tearoff=False)
        m_tools.add_command(label="Kiểm tra lỗi dự án",
                            command=self.run_linter)
        m_tools.add_separator()
        m_tools.add_command(label="🔧 Chuẩn hoá dự án đang mở (sửa để Scratch mở được)",
                            command=self.run_repair_current)
        m_tools.add_command(label="🔧 Chuẩn hoá file .sb3 từ đĩa (cho file lỗi nặng)...",
                            command=self.run_repair_from_disk)
        m_tools.add_separator()
        m_tools.add_command(label="Ẩn toàn bộ monitor biến",
                            command=self.hide_all_monitors)
        menubar.add_cascade(label="Công cụ", menu=m_tools)

        m_help = tk.Menu(menubar, tearoff=False)
        m_help.add_command(label="Hướng dẫn", command=self._show_help)
        menubar.add_cascade(label="Trợ giúp", menu=m_help)

        self.config(menu=menubar)
        self.bind_all("<Control-o>", lambda e: self.open_sb3())
        self.bind_all("<Control-s>", lambda e: self.export_sb3())

    # ---------- layout ----------
    def _build_layout(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x")
        ttk.Button(toolbar, text="📂 Mở .sb3", command=self.open_sb3).pack(side="left", padx=4, pady=4)
        ttk.Button(toolbar, text="💾 Xuất .sb3", command=self.export_sb3).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🔎 Kiểm tra lỗi", command=self.run_linter).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🔧 Chuẩn hoá", command=self.run_repair_current).pack(side="left", padx=4)
        ttk.Checkbutton(toolbar, text="Ẩn biến Scratch thô (vd: __, _temp)",
                        variable=self._hide_raw_vars,
                        command=self._refresh_vars).pack(side="left", padx=12)
        self.lbl_proj = ttk.Label(toolbar, text="(chưa mở dự án)",
                                  foreground="#555")
        self.lbl_proj.pack(side="right", padx=8)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        # ----- LEFT: Stage + thông tin sprite -----
        left = ttk.Frame(main)
        main.add(left, weight=2)

        self.stage_view = StageView(left, on_sprite_moved=self._on_sprite_moved)
        self.stage_view.pack(anchor="n", pady=6)

        sp_frame = ttk.LabelFrame(left, text="Thuộc tính sprite đang chọn")
        sp_frame.pack(fill="x", padx=6, pady=6)

        self.sp_name_var = tk.StringVar(value="(chưa chọn)")
        ttk.Label(sp_frame, textvariable=self.sp_name_var,
                  font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=6, sticky="w", padx=6, pady=4)

        ttk.Label(sp_frame, text="X:").grid(row=1, column=0, sticky="e", padx=2)
        self.sp_x = ttk.Entry(sp_frame, width=8)
        self.sp_x.grid(row=1, column=1, padx=2)
        ttk.Label(sp_frame, text="Y:").grid(row=1, column=2, sticky="e", padx=2)
        self.sp_y = ttk.Entry(sp_frame, width=8)
        self.sp_y.grid(row=1, column=3, padx=2)
        ttk.Label(sp_frame, text="Size %:").grid(row=1, column=4, sticky="e", padx=2)
        self.sp_size = ttk.Entry(sp_frame, width=8)
        self.sp_size.grid(row=1, column=5, padx=2)

        ttk.Label(sp_frame, text="Direction:").grid(row=2, column=0, sticky="e", padx=2, pady=4)
        self.sp_dir = ttk.Entry(sp_frame, width=8)
        self.sp_dir.grid(row=2, column=1, padx=2)
        self.sp_visible_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(sp_frame, text="Hiển thị",
                        variable=self.sp_visible_var).grid(row=2, column=2, columnspan=2, padx=4)
        ttk.Button(sp_frame, text="Áp dụng",
                   command=self._apply_sprite_props).grid(row=2, column=4, columnspan=2, sticky="ew", padx=4)
        ttk.Button(sp_frame, text="Thay costume từ ảnh...",
                   command=self._replace_sprite_costume).grid(row=3, column=0, columnspan=6, sticky="ew", padx=4, pady=4)

        # ----- RIGHT: Notebook -----
        right = ttk.Frame(main)
        main.add(right, weight=3)

        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True)

        self._build_tab_sprites()
        self._build_tab_backdrops()
        self._build_tab_vars()
        self._build_tab_lists()
        self._build_tab_broadcasts()
        self._build_tab_assets()
        self._build_tab_qbank()
        self._build_tab_lint()
        self._build_tab_ai()

        # Status bar
        self.status = ttk.Label(self, text="", anchor="w",
                                relief="sunken", padding=4)
        self.status.pack(side="bottom", fill="x")

    # ----- Tab: sprites -----
    def _build_tab_sprites(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Sprite")

        cols = ("name", "x", "y", "size", "dir", "visible", "costumes")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        for c, label, w in [
            ("name", "Tên", 160), ("x", "X", 60), ("y", "Y", 60),
            ("size", "Size", 60), ("dir", "Hướng", 60),
            ("visible", "Hiện", 50), ("costumes", "Số costume", 80),
        ]:
            tv.heading(c, text=label)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        tv.bind("<<TreeviewSelect>>", self._on_sprite_selected)
        self.tv_sprites = tv

    # ----- Tab: backdrops -----
    def _build_tab_backdrops(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Backdrop")

        cols = ("idx", "name", "md5ext", "size")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        for c, label, w in [("idx", "#", 40), ("name", "Tên", 180),
                            ("md5ext", "Asset", 220), ("size", "Kích thước", 100)]:
            tv.heading(c, text=label)
            tv.column(c, width=w)
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        self.tv_backdrops = tv

        bar = ttk.Frame(frm)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Button(bar, text="Thay ảnh nền (backdrop hiện tại)...",
                   command=self._replace_backdrop).pack(side="left", padx=4)
        ttk.Button(bar, text="Đặt làm backdrop hiện tại",
                   command=self._set_current_backdrop).pack(side="left", padx=4)

    # ----- Tab: variables -----
    def _build_tab_vars(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Biến")

        cols = ("target", "name", "value", "cloud")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        for c, label, w in [("target", "Thuộc về", 140), ("name", "Tên biến", 200),
                            ("value", "Giá trị", 200), ("cloud", "Cloud", 60)]:
            tv.heading(c, text=label)
            tv.column(c, width=w)
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        tv.bind("<Double-1>", self._edit_variable)
        self.tv_vars = tv

    # ----- Tab: lists -----
    def _build_tab_lists(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="List")

        cols = ("target", "name", "len", "preview")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        for c, label, w in [("target", "Thuộc về", 140), ("name", "Tên list", 200),
                            ("len", "Số dòng", 80), ("preview", "Xem trước", 360)]:
            tv.heading(c, text=label)
            tv.column(c, width=w)
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        tv.bind("<Double-1>", self._edit_list)
        self.tv_lists = tv

    # ----- Tab: broadcasts -----
    def _build_tab_broadcasts(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Broadcast")

        cols = ("id", "name")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        tv.heading("id", text="ID"); tv.column("id", width=200)
        tv.heading("name", text="Tên broadcast"); tv.column("name", width=300)
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        self.tv_broadcasts = tv

    # ----- Tab: assets -----
    def _build_tab_assets(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Asset")

        cols = ("file", "size", "used_by")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        for c, label, w in [("file", "Tên file", 260), ("size", "Dung lượng", 100),
                            ("used_by", "Sử dụng bởi", 380)]:
            tv.heading(c, text=label)
            tv.column(c, width=w)
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        self.tv_assets = tv

    # ----- Tab: qbank -----
    def _build_tab_qbank(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Ngân hàng câu hỏi")

        top = ttk.Frame(frm)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Mapping (sprite/stage chứa list):").pack(side="left")
        self.cmb_qbank = ttk.Combobox(top, state="readonly", width=40)
        self.cmb_qbank.pack(side="left", padx=6)
        self.cmb_qbank.bind("<<ComboboxSelected>>", lambda e: self._refresh_qbank_preview())
        ttk.Button(top, text="Xuất CSV...", command=self.qbank_export).pack(side="left", padx=4)
        ttk.Button(top, text="Nhập CSV...", command=self.qbank_import).pack(side="left", padx=4)

        self.qbank_tree = ttk.Treeview(frm, show="headings", height=18)
        self.qbank_tree.pack(fill="both", expand=True, padx=6, pady=6)

        self.qbank_mappings: list[QBankMapping] = []

    # ----- Tab: AI -----
    def _build_tab_ai(self):
        self.ai_panel = AIPanel(self.nb, app=self)
        self.nb.add(self.ai_panel, text="🤖 AI Assistant")

    # ----- Tab: lint -----
    def _build_tab_lint(self):
        frm = ttk.Frame(self.nb)
        self.nb.add(frm, text="Kiểm tra lỗi")

        bar = ttk.Frame(frm)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Button(bar, text="🔎 Chạy kiểm tra ngay",
                   command=self.run_linter).pack(side="left")

        self.txt_lint = tk.Text(frm, wrap="word", font=("Consolas", 10))
        self.txt_lint.pack(fill="both", expand=True, padx=6, pady=6)
        self.txt_lint.insert("end", "Bấm 'Chạy kiểm tra ngay' sau khi mở dự án.\n")
        self.txt_lint.config(state="disabled")

    # =========================================================
    # Actions
    # =========================================================
    def open_sb3(self):
        path = filedialog.askopenfilename(
            title="Chọn file .sb3", filetypes=[("Scratch project", "*.sb3")])
        if not path:
            return
        try:
            bundle = Sb3Bundle.open(Path(path))
        except Sb3LoadError as e:
            messagebox.showerror("Lỗi mở file", str(e))
            return
        # cleanup bundle cũ
        if self.bundle is not None:
            self.bundle.cleanup()
        self.bundle = bundle
        self.model = ProjectModel(bundle.project)
        self.lbl_proj.config(text=f"📁 {bundle.source_path.name}")
        self._set_status(f"Đã mở: {bundle.source_path} (workdir: {bundle.workdir})")
        self.stage_view.set_project(self.model, bundle.workdir)
        self._refresh_all_tabs()

    def export_sb3(self):
        if not self.bundle:
            messagebox.showinfo("Chưa có dự án", "Hãy mở file .sb3 trước.")
            return
        suggest = self.bundle.source_path.stem + "_edited.sb3"
        out_name = filedialog.asksaveasfilename(
            title="Lưu file .sb3 mới", defaultextension=".sb3",
            initialdir=str(OUTPUT_DIR), initialfile=suggest,
            filetypes=[("Scratch project", "*.sb3")])
        if not out_name:
            return
        # Chỉ giữ tên file – luôn xuất vào OUTPUT_DIR để an toàn
        out_path = Path(out_name)
        try:
            saved = self.bundle.export_sb3(out_name=out_path.name)
            # nếu user chọn đường dẫn ngoài, copy ra đó
            if out_path.parent.resolve() != OUTPUT_DIR.resolve():
                import shutil
                shutil.copy2(saved, out_path)
                final = out_path
            else:
                final = saved
        except Exception as e:
            messagebox.showerror("Lỗi xuất .sb3", str(e))
            return
        messagebox.showinfo(
            "Xuất thành công",
            f"Đã xuất:\n{final}\n\nLưu ý: file gốc KHÔNG bị thay đổi.\n"
            "Có thể mở file mới bằng Scratch Desktop.")
        self._set_status(f"Đã xuất: {final}")

    def run_linter(self):
        if not self.model or not self.bundle:
            messagebox.showinfo("Chưa có dự án", "Hãy mở file .sb3 trước.")
            return
        issues = Linter(self.model, self.bundle.workdir).run()
        self.txt_lint.config(state="normal")
        self.txt_lint.delete("1.0", "end")
        summary = (f"Tổng số: {len(issues)} | "
                   f"Lỗi: {sum(1 for i in issues if i.severity=='error')} | "
                   f"Cảnh báo: {sum(1 for i in issues if i.severity=='warning')} | "
                   f"Thông tin: {sum(1 for i in issues if i.severity=='info')}\n\n")
        self.txt_lint.insert("end", summary)
        self.txt_lint.insert("end", format_issues(issues))
        self.txt_lint.config(state="disabled")
        self.nb.select(7)
        self._set_status(f"Kiểm tra xong: {len(issues)} mục.")

    def run_repair_current(self):
        if not self.bundle or not self.model:
            messagebox.showinfo("Chưa có dự án",
                                "Hãy mở file .sb3 trước, hoặc dùng "
                                "'Chuẩn hoá file .sb3 từ đĩa' cho file lỗi nặng.")
            return
        if not messagebox.askyesno(
                "Chuẩn hoá dự án",
                "Sẽ tự sửa các lỗi khiến Scratch không mở được:\n"
                "• Bổ sung trường thiếu (meta, monitors, costumes...)\n"
                "• Khớp lại MD5 của asset, đổi tên file lệch\n"
                "• Thay placeholder cho costume bị thiếu file\n"
                "• Dồn broadcasts về Stage, dọn monitor mồ côi\n"
                "• Cắt block parent/next trỏ id lạ\n\n"
                "File gốc KHÔNG bị sửa. Tiếp tục?"):
            return
        # backup project.json
        import json as _json, time
        from utils.paths import BACKUP_DIR
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        (BACKUP_DIR / f"project_pre_repair_{stamp}.json").write_text(
            _json.dumps(self.bundle.project, ensure_ascii=False),
            encoding="utf-8")
        rpt = repair_project_dict(self.bundle.project, self.bundle.workdir)
        # refresh + show report
        self._refresh_all_tabs()
        self.stage_view.refresh()
        text = format_report(rpt)
        self._show_report_window("Báo cáo chuẩn hoá", text)
        self._set_status(f"Chuẩn hoá xong: {len(rpt.fixes)} sửa đổi.")

    def run_repair_from_disk(self):
        path = filedialog.askopenfilename(
            title="Chọn file .sb3 bị lỗi", filetypes=[("Scratch project", "*.sb3")])
        if not path:
            return
        try:
            out_path, rpt = repair_sb3_from_disk(Path(path), OUTPUT_DIR)
        except Exception as e:
            messagebox.showerror("Lỗi chuẩn hoá", str(e))
            return
        text = format_report(rpt)
        if rpt.fatal_errors:
            messagebox.showerror("Lỗi nghiêm trọng", text)
            return
        text += f"\n\n📦 File đã chuẩn hoá:\n{out_path}"
        self._show_report_window("Chuẩn hoá file .sb3 từ đĩa", text)
        if messagebox.askyesno("Mở file đã chuẩn hoá?",
                               "Mở file vừa chuẩn hoá trong editor?"):
            try:
                bundle = Sb3Bundle.open(out_path)
            except Sb3LoadError as e:
                messagebox.showerror("Lỗi mở file", str(e))
                return
            if self.bundle is not None:
                self.bundle.cleanup()
            self.bundle = bundle
            self.model = ProjectModel(bundle.project)
            self.lbl_proj.config(text=f"📁 {bundle.source_path.name}")
            self.stage_view.set_project(self.model, bundle.workdir)
            self._refresh_all_tabs()

    def _show_report_window(self, title: str, text: str):
        win = tk.Toplevel(self); win.title(title); win.geometry("780x560")
        win.transient(self)
        txt = tk.Text(win, wrap="word", font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("end", text)
        txt.config(state="disabled")
        bar = ttk.Frame(win); bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Đóng", command=win.destroy).pack(side="right", padx=8)

    def hide_all_monitors(self):
        if not self.model:
            return
        n = self.model.hide_all_variable_monitors()
        messagebox.showinfo("Hoàn tất", f"Đã ẩn {n} monitor biến.")
        self.stage_view.refresh()

    # ---------- sprite tab ----------
    def _refresh_sprites(self):
        for i in self.tv_sprites.get_children():
            self.tv_sprites.delete(i)
        if not self.model:
            return
        for sp in self.model.sprites():
            self.tv_sprites.insert("", "end", values=(
                sp.get("name", ""),
                sp.get("x", 0), sp.get("y", 0),
                sp.get("size", 100), sp.get("direction", 90),
                "✓" if sp.get("visible", True) else "✗",
                len(sp.get("costumes", [])),
            ))

    def _selected_sprite_name(self) -> str | None:
        sel = self.tv_sprites.selection()
        if not sel:
            return None
        return self.tv_sprites.item(sel[0], "values")[0]

    def _on_sprite_selected(self, _evt=None):
        if not self.model:
            return
        name = self._selected_sprite_name()
        if not name:
            return
        sp = self.model.target_by_name(name)
        if not sp:
            return
        self.sp_name_var.set(f"Sprite: {name}")
        for entry, key, default in [
            (self.sp_x, "x", 0), (self.sp_y, "y", 0),
            (self.sp_size, "size", 100), (self.sp_dir, "direction", 90),
        ]:
            entry.delete(0, "end")
            entry.insert(0, str(sp.get(key, default)))
        self.sp_visible_var.set(bool(sp.get("visible", True)))

    def _apply_sprite_props(self):
        if not self.model:
            return
        name = self._selected_sprite_name()
        if not name:
            messagebox.showinfo("Chưa chọn sprite", "Chọn sprite trong bảng trước.")
            return
        try:
            x = float(self.sp_x.get()); y = float(self.sp_y.get())
            size = float(self.sp_size.get()); dirn = float(self.sp_dir.get())
        except ValueError:
            messagebox.showerror("Sai dữ liệu", "X/Y/Size/Direction phải là số.")
            return
        self.model.set_sprite_xy(name, x, y)
        self.model.set_sprite_size(name, size)
        self.model.set_sprite_direction(name, dirn)
        self.model.set_sprite_visible(name, self.sp_visible_var.get())
        self._refresh_sprites()
        self.stage_view.refresh()
        self._set_status(f"Cập nhật sprite '{name}'")

    def _on_sprite_moved(self, name: str, x: float, y: float):
        # cập nhật bảng + entry
        self._refresh_sprites()
        # nếu đang chọn cùng sprite, cập nhật entry
        if self._selected_sprite_name() == name:
            self.sp_x.delete(0, "end"); self.sp_x.insert(0, str(x))
            self.sp_y.delete(0, "end"); self.sp_y.insert(0, str(y))
        self._set_status(f"{name} → ({x}, {y})")

    def _replace_sprite_costume(self):
        if not self.model or not self.bundle:
            return
        name = self._selected_sprite_name()
        if not name:
            messagebox.showinfo("Chưa chọn sprite", "Chọn sprite trong bảng trước.")
            return
        sp = self.model.target_by_name(name)
        if not sp:
            return
        idx = int(sp.get("currentCostume", 0))
        path = filedialog.askopenfilename(
            title=f"Chọn ảnh thay costume cho '{name}'",
            filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg")])
        if not path:
            return
        try:
            asset = prepare_sprite_costume(Path(path))
        except Exception as e:
            messagebox.showerror("Lỗi xử lý ảnh", str(e))
            return
        self.bundle.write_asset(asset.md5ext, asset.data)
        rcx = asset.rotation_center_x if asset.data_format != "svg" else None
        rcy = asset.rotation_center_y if asset.data_format != "svg" else None
        br = asset.bitmap_resolution if asset.data_format != "svg" else None
        self.model.replace_costume_asset(
            name, idx, asset.md5ext, asset.asset_id,
            asset.data_format, rcx, rcy, br)
        self.stage_view.refresh()
        self._refresh_sprites()
        self._refresh_assets()
        self._set_status(f"Đã thay costume #{idx} của '{name}'.")

    # ---------- backdrop tab ----------
    def _refresh_backdrops(self):
        for i in self.tv_backdrops.get_children():
            self.tv_backdrops.delete(i)
        if not self.model or not self.bundle:
            return
        stage = self.model.stage()
        if not stage:
            return
        for i, c in enumerate(stage.get("costumes", [])):
            md5ext = c.get("md5ext", "")
            size = "?"
            p = self.bundle.workdir / md5ext if md5ext else None
            if p and p.exists():
                size = f"{p.stat().st_size//1024} KB"
            mark = " (hiện tại)" if i == int(stage.get("currentCostume", 0)) else ""
            self.tv_backdrops.insert("", "end", values=(
                i, c.get("name", "") + mark, md5ext, size))

    def _replace_backdrop(self):
        if not self.model or not self.bundle:
            return
        stage = self.model.stage()
        if not stage:
            return
        path = filedialog.askopenfilename(
            title="Chọn ảnh nền mới",
            filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg")])
        if not path:
            return
        mode = self._ask_scale_mode()
        if mode is None:
            return
        try:
            asset = prepare_backdrop(Path(path), mode=mode)
        except Exception as e:
            messagebox.showerror("Lỗi xử lý ảnh", str(e))
            return
        idx = int(stage.get("currentCostume", 0))
        self.bundle.write_asset(asset.md5ext, asset.data)
        self.model.replace_costume_asset(
            stage.get("name", "Stage"), idx,
            asset.md5ext, asset.asset_id, asset.data_format,
            asset.rotation_center_x, asset.rotation_center_y,
            asset.bitmap_resolution if asset.data_format != "svg" else None)
        self.stage_view.refresh()
        self._refresh_backdrops()
        self._refresh_assets()
        self._set_status("Đã thay ảnh nền.")

    def _ask_scale_mode(self) -> str | None:
        win = tk.Toplevel(self); win.title("Chế độ scale")
        win.transient(self); win.grab_set()
        var = tk.StringVar(value="fit")
        ttk.Label(win, text="Chọn cách scale ảnh về 480x360:").pack(padx=10, pady=8)
        for label, v in [("Fit – giữ tỉ lệ, có viền trong suốt", "fit"),
                         ("Cover – lấp đầy, cắt phần thừa", "cover"),
                         ("Stretch – kéo dãn vừa khung", "stretch")]:
            ttk.Radiobutton(win, text=label, value=v,
                            variable=var).pack(anchor="w", padx=20)
        ok = {"ok": False}
        bar = ttk.Frame(win); bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="OK",
                   command=lambda: (ok.update(ok=True), win.destroy())).pack(side="right", padx=8)
        ttk.Button(bar, text="Huỷ", command=win.destroy).pack(side="right")
        self.wait_window(win)
        return var.get() if ok["ok"] else None

    def _set_current_backdrop(self):
        if not self.model:
            return
        sel = self.tv_backdrops.selection()
        if not sel:
            return
        idx = int(self.tv_backdrops.item(sel[0], "values")[0])
        stage = self.model.stage()
        if stage:
            stage["currentCostume"] = idx
            self.stage_view.refresh()
            self._refresh_backdrops()

    # ---------- variables tab ----------
    def _refresh_vars(self):
        for i in self.tv_vars.get_children():
            self.tv_vars.delete(i)
        if not self.model:
            return
        hide = self._hide_raw_vars.get()
        for v in self.model.iter_variables():
            if hide and (v.name.startswith("_") or v.name.startswith("__")):
                continue
            self.tv_vars.insert("", "end",
                                iid=f"{v.target_name}|{v.var_id}",
                                values=(v.target_name, v.name,
                                        str(v.value),
                                        "☁" if v.is_cloud else ""))

    def _edit_variable(self, _evt=None):
        sel = self.tv_vars.selection()
        if not sel or not self.model:
            return
        target_name, var_id = sel[0].split("|", 1)
        t = self.model.target_by_name(target_name)
        if not t:
            return
        payload = (t.get("variables") or {}).get(var_id)
        if not payload:
            return
        VariableEditDialog(
            self, payload[0], payload[1],
            on_save=lambda val: (
                self.model.update_variable_value(target_name, var_id, val),
                self._refresh_vars()))

    # ---------- lists tab ----------
    def _refresh_lists(self):
        for i in self.tv_lists.get_children():
            self.tv_lists.delete(i)
        if not self.model:
            return
        for le in self.model.iter_lists():
            preview = " | ".join(str(x) for x in le.items[:3])
            if len(le.items) > 3:
                preview += " …"
            self.tv_lists.insert("", "end",
                                 iid=f"{le.target_name}|{le.list_id}",
                                 values=(le.target_name, le.name,
                                         len(le.items), preview))

    def _edit_list(self, _evt=None):
        sel = self.tv_lists.selection()
        if not sel or not self.model:
            return
        target_name, list_id = sel[0].split("|", 1)
        t = self.model.target_by_name(target_name)
        if not t:
            return
        payload = (t.get("lists") or {}).get(list_id)
        if not payload:
            return
        ListEditorDialog(
            self, f"Sửa list: {payload[0]} ({target_name})",
            [str(x) for x in payload[1]],
            on_save=lambda items: (
                self.model.update_list_items(target_name, list_id, items),
                self._refresh_lists(),
                self._refresh_qbank_mappings()))

    # ---------- broadcasts ----------
    def _refresh_broadcasts(self):
        for i in self.tv_broadcasts.get_children():
            self.tv_broadcasts.delete(i)
        if not self.model:
            return
        for b in self.model.iter_broadcasts():
            self.tv_broadcasts.insert("", "end", values=(b.broadcast_id, b.name))

    # ---------- assets ----------
    def _refresh_assets(self):
        for i in self.tv_assets.get_children():
            self.tv_assets.delete(i)
        if not self.model or not self.bundle:
            return
        # đếm xem file dùng bởi ai
        use_map: dict[str, list[str]] = {}
        for t in self.model.targets:
            tname = t.get("name", "?")
            for c in t.get("costumes", []):
                md = c.get("md5ext")
                if md: use_map.setdefault(md, []).append(f"{tname}/costume:{c.get('name','')}")
            for s in t.get("sounds", []):
                md = s.get("md5ext")
                if md: use_map.setdefault(md, []).append(f"{tname}/sound:{s.get('name','')}")
        for p in sorted(self.bundle.list_assets(), key=lambda x: x.name):
            size = f"{p.stat().st_size//1024} KB" if p.stat().st_size >= 1024 else f"{p.stat().st_size} B"
            uses = ", ".join(use_map.get(p.name, [])) or "(không dùng)"
            self.tv_assets.insert("", "end", values=(p.name, size, uses))

    # ---------- qbank ----------
    def _refresh_qbank_mappings(self):
        if not self.model:
            self.cmb_qbank["values"] = []
            return
        self.qbank_mappings = discover_question_lists(self.model)
        labels = [f"{m.target_name}  ({len(m.columns)} list)"
                  for m in self.qbank_mappings]
        self.cmb_qbank["values"] = labels
        if labels:
            self.cmb_qbank.current(0)
            self._refresh_qbank_preview()

    def _current_qbank_mapping(self) -> QBankMapping | None:
        i = self.cmb_qbank.current()
        if i < 0 or i >= len(self.qbank_mappings):
            return None
        return self.qbank_mappings[i]

    def _refresh_qbank_preview(self):
        for c in self.qbank_tree.get_children():
            self.qbank_tree.delete(c)
        m = self._current_qbank_mapping()
        if not m or not self.model:
            self.qbank_tree["columns"] = ()
            return
        table = render_preview(self.model, m, max_rows=200)
        if not table:
            return
        headers = table[0]
        self.qbank_tree["columns"] = tuple(headers)
        for h in headers:
            self.qbank_tree.heading(h, text=h)
            self.qbank_tree.column(h, width=140, anchor="w")
        for row in table[1:]:
            self.qbank_tree.insert("", "end", values=row)

    def qbank_export(self):
        m = self._current_qbank_mapping()
        if not m or not self.model:
            messagebox.showinfo("Chưa có dữ liệu", "Mở dự án và chọn mapping trước.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu CSV", defaultextension=".csv",
            initialfile=f"qbank_{m.target_name}.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            n = export_to_csv(self.model, m, Path(path))
        except Exception as e:
            messagebox.showerror("Lỗi xuất CSV", str(e))
            return
        messagebox.showinfo("OK", f"Đã xuất {n} dòng vào {path}")

    def qbank_import(self):
        m = self._current_qbank_mapping()
        if not m or not self.model:
            messagebox.showinfo("Chưa có dữ liệu", "Mở dự án và chọn mapping trước.")
            return
        path = filedialog.askopenfilename(
            title="Chọn CSV", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        create = messagebox.askyesno(
            "Tạo list mới?",
            "Nếu CSV có cột chưa tồn tại trong list, tạo list mới?")
        try:
            res = import_from_csv(self.model, m, Path(path),
                                  create_missing_lists=create)
        except Exception as e:
            messagebox.showerror("Lỗi nhập CSV", str(e))
            return
        self._refresh_lists()
        self._refresh_qbank_preview()
        detail = "\n".join(f"  {k}: {v} dòng" for k, v in res.items())
        messagebox.showinfo("OK", f"Đã nhập:\n{detail}")

    # ---------- misc ----------
    def _refresh_all_tabs(self):
        self._refresh_sprites()
        self._refresh_backdrops()
        self._refresh_vars()
        self._refresh_lists()
        self._refresh_broadcasts()
        self._refresh_assets()
        self._refresh_qbank_mappings()

    def _set_status(self, text: str):
        self.status.config(text=text)

    def _open_in_explorer(self, p: Path):
        import os, subprocess, sys
        p = Path(p); p.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _show_help(self):
        messagebox.showinfo(
            "Hướng dẫn nhanh",
            "1) Mở .sb3 → file gốc KHÔNG bị thay đổi (giải nén vào workspace/temp).\n"
            "2) Sửa sprite/biến/list/backdrop ở tab tương ứng. Kéo sprite trực tiếp trên Stage.\n"
            "3) Ngân hàng câu hỏi: xuất CSV ra Excel để sửa, nhập CSV lại.\n"
            "4) Chạy 'Kiểm tra lỗi' trước khi xuất.\n"
            "5) Xuất .sb3 → lưu vào workspace/output/, mở bằng Scratch Desktop.\n")

    def _on_close(self):
        if self.bundle is not None:
            self.bundle.cleanup()
        self.destroy()
