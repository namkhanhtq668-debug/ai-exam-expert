"""Hộp thoại phụ: chỉnh sửa list, biến."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox


class ListEditorDialog(tk.Toplevel):
    def __init__(self, master, title: str, items: list[str],
                 on_save):
        super().__init__(master)
        self.title(title)
        self.geometry("520x500")
        self.on_save = on_save
        self.transient(master)
        self.grab_set()

        ttk.Label(self, text="Mỗi dòng là một phần tử của list:").pack(
            anchor="w", padx=8, pady=(8, 0))

        self.text = tk.Text(self, wrap="none", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=8, pady=4)
        sb = ttk.Scrollbar(self.text, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        for it in items:
            self.text.insert("end", str(it) + "\n")

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Lưu", command=self._save).pack(side="right", padx=4)
        ttk.Button(bar, text="Huỷ", command=self.destroy).pack(side="right")

    def _save(self):
        raw = self.text.get("1.0", "end").rstrip("\n")
        items = raw.split("\n") if raw else []
        try:
            self.on_save(items)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=self)
            return
        self.destroy()


class VariableEditDialog(tk.Toplevel):
    def __init__(self, master, var_name: str, current_value, on_save):
        super().__init__(master)
        self.title(f"Sửa biến: {var_name}")
        self.geometry("400x150")
        self.transient(master)
        self.grab_set()
        self.on_save = on_save

        ttk.Label(self, text=f"Giá trị cho biến '{var_name}':").pack(
            anchor="w", padx=10, pady=(10, 0))
        self.entry = ttk.Entry(self)
        self.entry.insert(0, str(current_value))
        self.entry.pack(fill="x", padx=10, pady=8)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=10)
        ttk.Button(bar, text="Lưu", command=self._save).pack(side="right", padx=4)
        ttk.Button(bar, text="Huỷ", command=self.destroy).pack(side="right")

    def _save(self):
        v = self.entry.get()
        # giữ kiểu số nếu có thể
        try:
            if "." in v:
                val = float(v)
            else:
                val = int(v)
        except ValueError:
            val = v
        self.on_save(val)
        self.destroy()
