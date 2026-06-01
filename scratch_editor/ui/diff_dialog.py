"""Dialog xem diff trước khi áp dụng đề xuất của AI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class DiffApproveDialog(tk.Toplevel):
    """Dialog 3 cột (tick | cũ | mới) cho danh sách thay đổi.

    rows: list[tuple[key, old, new]]
    on_apply(selected_keys: list) -> None
    """

    def __init__(self, master, title: str,
                 rows: list[tuple], on_apply: Callable,
                 col_old: str = "Cũ", col_new: str = "Mới (AI)",
                 col_key: str = "#"):
        super().__init__(master)
        self.title(title)
        self.geometry("900x600")
        self.transient(master); self.grab_set()
        self.on_apply = on_apply
        self._rows = rows
        self._checked: dict = {i: True for i in range(len(rows))}

        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="Chọn tất cả",
                   command=lambda: self._set_all(True)).pack(side="left", padx=4)
        ttk.Button(top, text="Bỏ chọn tất cả",
                   command=lambda: self._set_all(False)).pack(side="left", padx=4)
        ttk.Label(top, text=f"  {len(rows)} thay đổi đề xuất").pack(side="left", padx=10)

        cols = ("chk", "key", "old", "new")
        tv = ttk.Treeview(self, columns=cols, show="headings", height=20)
        tv.heading("chk", text="✓")
        tv.heading("key", text=col_key)
        tv.heading("old", text=col_old)
        tv.heading("new", text=col_new)
        tv.column("chk", width=40, anchor="center")
        tv.column("key", width=120)
        tv.column("old", width=340)
        tv.column("new", width=340)
        tv.pack(fill="both", expand=True, padx=8, pady=4)

        for i, (key, old, new) in enumerate(rows):
            tv.insert("", "end", iid=str(i),
                      values=("✓", str(key), str(old), str(new)))
        tv.bind("<Button-1>", self._toggle_click)
        self.tv = tv

        bar = ttk.Frame(self); bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Áp dụng các mục đã chọn",
                   command=self._apply).pack(side="right", padx=4)
        ttk.Button(bar, text="Huỷ", command=self.destroy).pack(side="right")

    def _set_all(self, val: bool):
        for i in range(len(self._rows)):
            self._checked[i] = val
            self.tv.set(str(i), "chk", "✓" if val else "")

    def _toggle_click(self, evt):
        region = self.tv.identify("region", evt.x, evt.y)
        col = self.tv.identify_column(evt.x)
        if region != "cell" or col != "#1":
            return
        row = self.tv.identify_row(evt.y)
        if not row:
            return
        i = int(row)
        self._checked[i] = not self._checked[i]
        self.tv.set(row, "chk", "✓" if self._checked[i] else "")

    def _apply(self):
        keys = [self._rows[i][0] for i, ok in self._checked.items() if ok]
        try:
            self.on_apply(keys)
        finally:
            self.destroy()
