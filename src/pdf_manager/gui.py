from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "PDF 文献管理器"
OUTPUT_DIR_NAME = "_pdf_manager_output"
STYLE_OPTIONS = {
    "GB/T 7714": "gbt7714",
    "IEEE": "ieee",
    "APA": "apa",
    "MLA": "mla",
    "Chicago": "chicago",
}
STYLE_LABEL_BY_KEY = {v: k for k, v in STYLE_OPTIONS.items()}

COLS = ("select", "filename", "type", "confidence", "title", "year", "doi", "newname")
COL_LABELS = {
    "select": "",
    "filename": "原文件名",
    "type": "类型",
    "confidence": "置信度",
    "title": "标题 / 标记",
    "year": "年份",
    "doi": "DOI / arXiv",
    "newname": "建议文件名（可编辑）",
}
COL_WIDTHS = {
    "select": 42,
    "filename": 220,
    "type": 86,
    "confidence": 72,
    "title": 330,
    "year": 62,
    "doi": 170,
    "newname": 260,
}


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def _clean_filename(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:120] or "untitled"


def _short_title(title: str, limit: int = 5) -> str:
    words = re.sub(r"[^a-zA-Z0-9\s]", " ", title or "").split()
    return "_".join(w[:24].capitalize() for w in words[:limit]) or "Paper"


def _suggest_name(rec: dict) -> str:
    if rec.get("detected_type") in {"paper", "thesis"}:
        from pdf_manager import citation

        return _clean_filename(citation.filename_from_gbt(rec))
    tag = rec.get("tag") or rec.get("title") or Path(rec.get("original_filename", "document")).stem
    return _clean_filename(f"{tag}.pdf")


def _status_label(rec: dict) -> str:
    if rec.get("error"):
        return "失败"
    if rec.get("needs_review") or rec.get("detected_type") == "unknown":
        return "待复核"
    return {"paper": "期刊论文", "thesis": "学位论文", "document": "普通 PDF"}.get(
        rec.get("detected_type"), rec.get("detected_type") or ""
    )


def _authors_to_text(authors) -> str:
    if isinstance(authors, list):
        return "; ".join(str(a).strip() for a in authors if str(a).strip())
    return str(authors or "")


def _authors_from_text(text: str) -> list[str]:
    return [a.strip() for a in re.split(r";|\n", text or "") if a.strip()]


class _EditableTreeview(ttk.Treeview):
    def __init__(self, master, edit_col: str, on_edit=None, **kw):
        super().__init__(master, **kw)
        self._edit_col = edit_col
        self._on_edit = on_edit
        self._entry: tk.Entry | None = None
        self._editing_item: str | None = None
        self.bind("<Double-1>", self._on_double_click)

    def _on_double_click(self, event):
        if self.identify_region(event.x, event.y) != "cell":
            return
        item = self.identify_row(event.y)
        if not item:
            return
        if self.identify_column(event.x) == self._edit_col:
            self._start_edit(item)

    def _start_edit(self, item: str):
        self._commit_edit()
        bbox = self.bbox(item, self._edit_col)
        if not bbox:
            return
        col_idx = int(self._edit_col.lstrip("#")) - 1
        values = list(self.item(item, "values"))
        current = values[col_idx]
        self._editing_item = item
        self._entry = tk.Entry(self, font=("Microsoft YaHei UI", 9), relief=tk.SOLID, bd=1)
        self._entry.insert(0, current)
        self._entry.select_range(0, tk.END)
        self._entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        self._entry.focus_set()
        self._entry.bind("<Return>", lambda _e: self._commit_edit())
        self._entry.bind("<Escape>", lambda _e: self._cancel_edit())
        self._entry.bind("<FocusOut>", lambda _e: self._commit_edit())

    def _commit_edit(self):
        if not self._entry or not self._editing_item:
            return
        item = self._editing_item
        values = list(self.item(item, "values"))
        col_idx = int(self._edit_col.lstrip("#")) - 1
        values[col_idx] = _clean_filename(self._entry.get())
        self.item(item, values=values)
        if self._on_edit:
            self._on_edit(item, values[col_idx])
        self._entry.destroy()
        self._entry = None
        self._editing_item = None

    def _cancel_edit(self):
        if self._entry:
            self._entry.destroy()
        self._entry = None
        self._editing_item = None


class ReviewDialog(tk.Toplevel):
    def __init__(self, master: "App", item: str, rec: dict):
        super().__init__(master)
        self.title("复核 / 编辑元数据")
        self.geometry("720x620")
        self.minsize(620, 520)
        self.transient(master)
        self.grab_set()
        self._master = master
        self._item = item
        self._rec = rec
        self._vars: dict[str, tk.Variable] = {}
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        root = ttk.Frame(self, padding=14)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(1, weight=1)

        fields = [
            ("title", "标题", tk.StringVar(value=self._rec.get("title") or "")),
            ("authors", "作者（分号分隔）", tk.StringVar(value=_authors_to_text(self._rec.get("authors")))),
            ("year", "年份", tk.StringVar(value=self._rec.get("year") or "")),
            ("venue", "期刊 / 会议 / 学校", tk.StringVar(value=self._rec.get("venue") or "")),
            ("place", "地点", tk.StringVar(value=self._rec.get("place") or "")),
            ("advisor", "导师", tk.StringVar(value=self._rec.get("advisor") or "")),
            ("doi", "DOI", tk.StringVar(value=self._rec.get("doi") or "")),
            ("arxiv_id", "arXiv", tk.StringVar(value=self._rec.get("arxiv_id") or "")),
            ("tag", "Tag / citekey", tk.StringVar(value=self._rec.get("tag") or "")),
        ]
        for row, (key, label, var) in enumerate(fields):
            ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(root, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)
            self._vars[key] = var

        ttk.Label(root, text="类型").grid(row=len(fields), column=0, sticky="w", pady=4)
        type_var = tk.StringVar(value=self._rec.get("detected_type") or "document")
        ttk.Combobox(root, textvariable=type_var, values=["paper", "thesis", "document", "unknown"],
                     state="readonly").grid(row=len(fields), column=1, sticky="w", pady=4)
        self._vars["detected_type"] = type_var

        thesis_type_var = tk.StringVar(value=self._rec.get("thesis_type") or "")
        ttk.Label(root, text="学位类型").grid(row=len(fields) + 1, column=0, sticky="w", pady=4)
        ttk.Combobox(root, textvariable=thesis_type_var, values=["", "master", "doctoral", "unknown"],
                     state="readonly").grid(row=len(fields) + 1, column=1, sticky="w", pady=4)
        self._vars["thesis_type"] = thesis_type_var

        review_var = tk.BooleanVar(value=bool(self._rec.get("needs_review")))
        ttk.Checkbutton(root, text="需要人工复核", variable=review_var).grid(
            row=len(fields) + 2, column=1, sticky="w", pady=4
        )
        self._vars["needs_review"] = review_var

        reason = self._rec.get("classification_reason") or ""
        ttk.Label(root, text="识别理由").grid(row=len(fields) + 3, column=0, sticky="nw", pady=4)
        reason_text = tk.Text(root, height=4, wrap=tk.WORD, font=("Microsoft YaHei UI", 9))
        reason_text.grid(row=len(fields) + 3, column=1, sticky="ew", pady=4)
        reason_text.insert("1.0", reason)
        self._reason_text = reason_text

        ttk.Label(root, text="引用预览").grid(row=len(fields) + 4, column=0, sticky="nw", pady=4)
        self._preview = tk.Text(root, height=8, wrap=tk.WORD, font=("Microsoft YaHei UI", 9))
        self._preview.grid(row=len(fields) + 4, column=1, sticky="nsew", pady=4)
        root.rowconfigure(len(fields) + 4, weight=1)
        self._refresh_preview()

        for var in self._vars.values():
            try:
                var.trace_add("write", lambda *_: self._refresh_preview())
            except Exception:
                pass

        buttons = ttk.Frame(root)
        buttons.grid(row=len(fields) + 5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="保存", command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side=tk.LEFT)

    def _preview_record(self) -> dict:
        rec = dict(self._rec)
        rec["title"] = self._vars["title"].get().strip()
        rec["authors"] = _authors_from_text(self._vars["authors"].get())
        rec["year"] = self._vars["year"].get().strip()
        rec["venue"] = self._vars["venue"].get().strip()
        rec["place"] = self._vars["place"].get().strip()
        rec["advisor"] = self._vars["advisor"].get().strip()
        rec["doi"] = self._vars["doi"].get().strip()
        rec["arxiv_id"] = self._vars["arxiv_id"].get().strip()
        rec["tag"] = self._vars["tag"].get().strip()
        rec["detected_type"] = self._vars["detected_type"].get()
        rec["thesis_type"] = self._vars["thesis_type"].get().strip() or None
        rec["needs_review"] = bool(self._vars["needs_review"].get())
        return rec

    def _refresh_preview(self):
        from pdf_manager import citation

        rec = self._preview_record()
        style = self._master._cfg().get("citation_style", "gbt7714")
        text = [
            f"{citation.style_label(style)}:",
            citation.generate(rec, style),
            "",
            "IEEE:",
            citation.generate(rec, "ieee"),
        ]
        self._preview.configure(state=tk.NORMAL)
        self._preview.delete("1.0", tk.END)
        self._preview.insert("1.0", "\n".join(text))
        self._preview.configure(state=tk.DISABLED)

    def _save(self):
        from pdf_manager import bibtex, citation

        rec = self._preview_record()
        rec["classification_reason"] = self._reason_text.get("1.0", tk.END).strip()
        if rec["detected_type"] in {"paper", "thesis"}:
            rec["ieee_citation"] = citation.generate(rec, "ieee")
            rec["citation"] = citation.generate(rec, self._master._cfg().get("citation_style", "gbt7714"))
            if not rec.get("bibtex_key"):
                key, bib_entry = bibtex.generate(rec)
                rec["bibtex_key"] = key
                rec["_bibtex_entry"] = bib_entry
            rec["tag"] = rec.get("tag") or rec.get("bibtex_key")
        self._rec.update(rec)
        self._master._refresh_row(self._item)
        self._master._update_summary()
        self._master._update_detail()
        self.destroy()


class BatchReviewDialog(tk.Toplevel):
    def __init__(self, master: "App", rows: list[tuple[str, dict, tuple]]):
        super().__init__(master)
        self.title("批量复核")
        self.geometry("520x360")
        self.transient(master)
        self.grab_set()
        self._master = master
        self._rows = rows
        self._vars: dict[str, tk.Variable] = {}
        self._build()

    def _build(self):
        root = ttk.Frame(self, padding=14)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        ttk.Label(root, text=f"将修改 {len(self._rows)} 条勾选记录", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        fields = [
            ("detected_type", "类型", ["不修改", "paper", "thesis", "document", "unknown"]),
            ("thesis_type", "学位类型", ["不修改", "", "master", "doctoral", "unknown"]),
        ]
        row = 1
        for key, label, values in fields:
            ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=5)
            var = tk.StringVar(value="不修改")
            ttk.Combobox(root, textvariable=var, values=values, state="readonly").grid(row=row, column=1, sticky="ew", pady=5)
            self._vars[key] = var
            row += 1
        for key, label in (("year", "年份"), ("venue", "学校 / 期刊"), ("place", "地点"), ("advisor", "导师")):
            ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=5)
            var = tk.StringVar()
            ttk.Entry(root, textvariable=var).grid(row=row, column=1, sticky="ew", pady=5)
            self._vars[key] = var
            row += 1
        clear_review = tk.BooleanVar(value=True)
        self._vars["clear_review"] = clear_review
        ttk.Checkbutton(root, text="保存后清除待复核标记", variable=clear_review).grid(
            row=row, column=1, sticky="w", pady=5
        )
        buttons = ttk.Frame(root)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="应用", command=self._apply).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side=tk.LEFT)

    def _apply(self):
        for item, rec, _values in self._rows:
            dtype = self._vars["detected_type"].get()
            if dtype != "不修改":
                rec["detected_type"] = dtype
            ttype = self._vars["thesis_type"].get()
            if ttype != "不修改":
                rec["thesis_type"] = ttype or None
            for key in ("year", "venue", "place", "advisor"):
                val = self._vars[key].get().strip()
                if val:
                    rec[key] = val
            if self._vars["clear_review"].get():
                rec["needs_review"] = False
            self._master._refresh_row(item)
        self._master._update_summary()
        self._master._status_var.set(f"批量复核完成：{len(self._rows)} 条")
        self.destroy()


class ZoteroImportPrompt(tk.Toplevel):
    def __init__(self, master: "App", summary: dict, report: Path):
        super().__init__(master)
        self.title("Zotero 导入检查")
        self.geometry("560x260")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: str | None = None
        root = ttk.Frame(self, padding=16)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        ttk.Label(root, text="Zotero 导出检查", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        text = (
            f"本次 Zotero 将导入 {summary['citable']}/{summary['total']} 条文献；"
            f"跳过 {summary['omitted']} 条。\n\n"
            "跳过项通常是待复核、unknown、document、缺 DOI 或缺作者的记录。"
            "建议先打开待复核面板修正，再重新导出。\n\n"
            f"报告文件：{report}"
        )
        ttk.Label(root, text=text, wraplength=520, justify=tk.LEFT).grid(row=1, column=0, sticky="ew", pady=(10, 12))
        buttons = ttk.Frame(root)
        buttons.grid(row=2, column=0, sticky="e")
        for label, result, style in (
            ("打开待复核面板", "review", "Accent.TButton"),
            ("打开报告", "report", "Toolbutton.TButton"),
            ("继续导入", "continue", "Primary.TButton"),
            ("取消", "cancel", "Toolbutton.TButton"),
        ):
            ttk.Button(buttons, text=label, style=style, command=lambda r=result: self._choose(r)).pack(
                side=tk.LEFT, padx=(8, 0)
            )
        self.protocol("WM_DELETE_WINDOW", lambda: self._choose("cancel"))

    def _choose(self, result: str):
        self.result = result
        self.destroy()


class ZoteroReviewDialog(tk.Toplevel):
    FILTERS = {
        "全部跳过项": "all",
        "unknown": "unknown",
        "document": "document",
        "needs_review": "needs_review",
        "缺 DOI": "missing_doi",
        "缺作者": "missing_authors",
    }

    def __init__(self, master: "App"):
        super().__init__(master)
        self.title("Zotero 导出检查 / 待复核")
        self.geometry("960x560")
        self.minsize(820, 460)
        self.transient(master)
        self.grab_set()
        self._master = master
        self._filter_var = tk.StringVar(value="全部跳过项")
        self._build()
        self._refresh()

    def _build(self):
        root = ttk.Frame(self, padding=14)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        self._summary_var = tk.StringVar()
        ttk.Label(root, textvariable=self._summary_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")

        tools = ttk.Frame(root)
        tools.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        ttk.Label(tools, text="筛选", style="Muted.TLabel").pack(side=tk.LEFT)
        combo = ttk.Combobox(
            tools,
            textvariable=self._filter_var,
            values=list(self.FILTERS),
            state="readonly",
            width=18,
        )
        combo.pack(side=tk.LEFT, padx=(6, 12))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh())
        ttk.Button(tools, text="标为 paper", command=lambda: self._apply_type("paper")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(tools, text="标为 thesis", command=lambda: self._apply_type("thesis")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(tools, text="清除待复核", command=self._clear_review).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(tools, text="重新导出", style="Primary.TButton", command=self._export).pack(side=tk.RIGHT)
        ttk.Button(tools, text="打开报告", command=self._open_report).pack(side=tk.RIGHT, padx=(0, 8))

        cols = ("file", "type", "review", "doi", "authors", "reason", "title")
        self._tree = ttk.Treeview(root, columns=cols, show="headings", selectmode="extended")
        labels = {
            "file": "文件",
            "type": "类型",
            "review": "复核",
            "doi": "DOI",
            "authors": "作者",
            "reason": "跳过原因",
            "title": "标题",
        }
        widths = {"file": 170, "type": 80, "review": 60, "doi": 150, "authors": 130, "reason": 220, "title": 240}
        for col in cols:
            self._tree.heading(col, text=labels[col])
            self._tree.column(col, width=widths[col], anchor=tk.W)
        self._tree.grid(row=2, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(root, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=2, column=1, sticky="ns")

        bottom = ttk.Frame(root)
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            bottom,
            text="提示：只有 paper/thesis 会写入 Zotero RIS/BibTeX；修改后请重新导出。",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side=tk.RIGHT)

    def _refresh(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        summary = self._summary()
        self._summary_var.set(
            f"total {summary['total']} | 可导入 {summary['citable']} | skipped {summary['omitted']}"
        )
        for iid, rec in self._filtered_rows():
            self._tree.insert("", tk.END, iid=iid, values=(
                rec.get("original_filename", ""),
                rec.get("detected_type", ""),
                "yes" if rec.get("needs_review") else "no",
                rec.get("doi") or "",
                _authors_to_text(rec.get("authors")),
                self._skip_reason(rec),
                rec.get("title") or rec.get("tag") or "",
            ))

    def _summary(self) -> dict:
        from pdf_manager import integrations

        return integrations.zotero_export_summary(self._master._records)

    def _skipped_rows(self) -> list[tuple[str, dict]]:
        return [
            (iid, rec)
            for iid, rec in self._master._row_by_file.items()
            if rec.get("detected_type") not in {"paper", "thesis"}
        ]

    def _filtered_rows(self) -> list[tuple[str, dict]]:
        mode = self.FILTERS.get(self._filter_var.get(), "all")
        rows = self._skipped_rows()
        if mode == "unknown":
            return [(iid, rec) for iid, rec in rows if rec.get("detected_type") == "unknown"]
        if mode == "document":
            return [(iid, rec) for iid, rec in rows if rec.get("detected_type") == "document"]
        if mode == "needs_review":
            return [(iid, rec) for iid, rec in rows if rec.get("needs_review")]
        if mode == "missing_doi":
            return [(iid, rec) for iid, rec in rows if not rec.get("doi")]
        if mode == "missing_authors":
            return [(iid, rec) for iid, rec in rows if not rec.get("authors")]
        return rows

    def _selected_records(self) -> list[tuple[str, dict]]:
        selected = self._tree.selection()
        if selected:
            return [(iid, self._master._row_by_file[iid]) for iid in selected if iid in self._master._row_by_file]
        return self._filtered_rows()

    def _apply_type(self, detected_type: str):
        rows = self._selected_records()
        if not rows:
            messagebox.showinfo("没有记录", "当前筛选下没有可修改记录。")
            return
        for iid, rec in rows:
            rec["detected_type"] = detected_type
            rec["needs_review"] = False
            rec["_suggested_name"] = None
            self._master._refresh_row(iid)
        self._master._update_summary()
        self._refresh()
        self._master._status_var.set(f"Zotero 复核：已标为 {detected_type} {len(rows)} 条")

    def _clear_review(self):
        rows = self._selected_records()
        if not rows:
            messagebox.showinfo("没有记录", "当前筛选下没有可修改记录。")
            return
        for iid, rec in rows:
            rec["needs_review"] = False
            self._master._refresh_row(iid)
        self._master._update_summary()
        self._refresh()
        self._master._status_var.set(f"Zotero 复核：已清除待复核 {len(rows)} 条")

    def _export(self) -> Path | None:
        out = self._master._write_current_export()
        if out:
            self._refresh()
            messagebox.showinfo("重新导出完成", f"Zotero RIS/BibTeX 和报告已更新：\n{out}")
        return out

    def _open_report(self):
        out = self._master._write_current_export()
        if not out:
            return
        report = out / "zotero_import_report.md"
        try:
            os.startfile(str(report))
        except Exception as exc:
            messagebox.showerror("打开失败", f"请手动打开：\n{report}\n\n{exc}")

    def _skip_reason(self, rec: dict) -> str:
        if rec.get("error"):
            return "processing error"
        if rec.get("needs_review"):
            return "needs_review"
        if not rec.get("doi"):
            return "missing DOI"
        if not rec.get("authors"):
            return "missing authors"
        return f"classified as {rec.get('detected_type') or 'unknown'}"


class AIReadingDialog(tk.Toplevel):
    def __init__(self, master: "App", rec: dict):
        super().__init__(master)
        self.title("AI 粗读 / 精读")
        self.geometry("640x520")
        self.minsize(560, 440)
        self.transient(master)
        self._master = master
        self._rec = rec
        self._busy = False
        self._result_path: Path | None = None
        self._mode_var = tk.StringVar(value="rough")
        self._model_var = tk.StringVar(value="gpt-5.4")
        self._base_url_var = tk.StringVar(value="https://api.openai.com/v1")
        self._env_var = tk.StringVar(value="OPENAI_API_KEY")
        self._temp_key_var = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="密钥不会写入配置、日志、报告或 GitHub；留空则读取环境变量。")
        self._build()

    def _build(self):
        root = ttk.Frame(self, padding=14)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(7, weight=1)

        title = self._rec.get("title") or self._rec.get("original_filename") or "Untitled"
        ttk.Label(root, text="AI 阅读", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(root, text=title, wraplength=590, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12)
        )

        mode_box = ttk.Frame(root)
        mode_box.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Radiobutton(mode_box, text="粗读筛选", variable=self._mode_var, value="rough").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_box, text="精读笔记", variable=self._mode_var, value="deep").pack(side=tk.LEFT, padx=(16, 0))

        for row, (label, var) in enumerate((
            ("模型", self._model_var),
            ("Base URL", self._base_url_var),
            ("环境变量", self._env_var),
        ), start=3):
            ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(root, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)

        ttk.Label(root, text="临时 API Key").grid(row=6, column=0, sticky="nw", pady=4)
        key_frame = ttk.Frame(root)
        key_frame.grid(row=6, column=1, sticky="new", pady=4)
        key_frame.columnconfigure(0, weight=1)
        ttk.Entry(key_frame, textvariable=self._temp_key_var, show="*").grid(row=0, column=0, sticky="ew")
        ttk.Label(
            key_frame,
            text="可留空；若填写，仅本次运行内存使用，不保存。",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        ttk.Label(root, text="阅读偏好").grid(row=7, column=0, sticky="nw", pady=4)
        self._preference = tk.Text(root, height=7, wrap=tk.WORD, font=("Microsoft YaHei UI", 9))
        self._preference.grid(row=7, column=1, sticky="nsew", pady=4)
        self._preference.insert(
            "1.0",
            "偏好：航天动力学、小推力轨迹优化、最优控制、RTBP、ADRC；优先判断是否值得精读和引用。",
        )

        ttk.Label(root, textvariable=self._status_var, style="Muted.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        buttons = ttk.Frame(root)
        buttons.grid(row=9, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self._run_btn = ttk.Button(buttons, text="生成阅读笔记", style="Primary.TButton", command=self._run)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="打开结果", command=self._open_result).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=tk.LEFT)

    def _run(self):
        if self._busy:
            return
        pdf_path = Path(self._rec.get("absolute_path") or "")
        if not pdf_path.exists():
            messagebox.showerror("文件不存在", f"找不到 PDF：\n{pdf_path}")
            return
        scan_dir = self._master._dir_var.get().strip()
        if not scan_dir:
            messagebox.showinfo("未选择文件夹", "请先选择扫描文件夹。")
            return
        params = {
            "mode": self._mode_var.get(),
            "model": self._model_var.get().strip(),
            "base_url": self._base_url_var.get().strip(),
            "env_name": self._env_var.get().strip(),
            "temporary_key": self._temp_key_var.get(),
            "preference": self._preference.get("1.0", tk.END).strip(),
        }
        self._busy = True
        self._run_btn.configure(state=tk.DISABLED)
        self._status_var.set("正在调用模型生成阅读笔记，请稍候...")
        threading.Thread(target=self._worker, args=(pdf_path, Path(scan_dir) / OUTPUT_DIR_NAME, params), daemon=True).start()

    def _worker(self, pdf_path: Path, out_dir: Path, params: dict):
        try:
            from pdf_manager import ai_reading

            api_key = ai_reading.resolve_api_key(params["env_name"], params["temporary_key"])
            result = ai_reading.generate_reading(
                rec=self._rec,
                pdf_path=pdf_path,
                out_dir=out_dir,
                mode=params["mode"],
                model=params["model"] or ai_reading.DEFAULT_MODEL,
                base_url=params["base_url"] or ai_reading.DEFAULT_BASE_URL,
                api_key=api_key,
                preference=params["preference"],
            )
            self.after(0, lambda: self._finish(result, None))
        except Exception as exc:
            err = exc
            self.after(0, lambda: self._finish(None, err))

    def _finish(self, result: Path | None, exc: Exception | None):
        self._busy = False
        self._run_btn.configure(state=tk.NORMAL)
        if exc:
            messagebox.showerror("AI 阅读失败", str(exc))
            self._status_var.set("生成失败。请检查 API Key、Base URL、模型名和网络。")
            return
        self._result_path = result
        self._status_var.set(f"已生成：{result}")
        self._master._status_var.set(f"AI 阅读笔记已生成：{result.name}")

    def _open_result(self):
        if self._result_path and self._result_path.exists():
            os.startfile(str(self._result_path))
            return
        scan_dir = self._master._dir_var.get().strip()
        notes_dir = Path(scan_dir) / OUTPUT_DIR_NAME / "ai_reading_notes" if scan_dir else None
        if notes_dir and notes_dir.exists():
            os.startfile(str(notes_dir))
            return
        messagebox.showinfo("暂无结果", "请先生成 AI 阅读笔记。")


class DuplicateDialog(tk.Toplevel):
    def __init__(self, master: "App"):
        super().__init__(master)
        self.title("重复文献合并")
        self.geometry("820x460")
        self.transient(master)
        self.grab_set()
        self._master = master
        self._build()

    def _build(self):
        from pdf_manager import duplicates

        root = ttk.Frame(self, padding=14)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        ttk.Label(root, text="重复组：保留信息最完整的一条，其余标记为已合并候选。", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        cols = ("group", "file", "title", "doi", "keep")
        tree = ttk.Treeview(root, columns=cols, show="headings")
        labels = {"group": "重复组", "file": "文件", "title": "标题", "doi": "DOI", "keep": "保留"}
        widths = {"group": 180, "file": 170, "title": 260, "doi": 140, "keep": 70}
        for col in cols:
            tree.heading(col, text=labels[col])
            tree.column(col, width=widths[col], anchor=tk.W)
        tree.grid(row=1, column=0, sticky="nsew")
        groups = duplicates.build_groups(self._master._records)
        for group in groups:
            primary = duplicates.choose_primary(group["records"])
            for rec in group["records"]:
                tree.insert("", tk.END, values=(
                    group["key"],
                    rec.get("original_filename", ""),
                    rec.get("title", ""),
                    rec.get("doi", ""),
                    "是" if rec is primary else "",
                ))
        if not groups:
            tree.insert("", tk.END, values=("", "未检测到重复文献", "", "", ""))
        buttons = ttk.Frame(root)
        buttons.grid(row=2, column=0, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="应用合并标记", command=self._apply_merge_marks).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=tk.LEFT)

    def _apply_merge_marks(self):
        from pdf_manager import duplicates

        duplicates.mark_duplicates(self._master._records)
        for item, rec in self._master._row_by_file.items():
            self._master._refresh_row(item)
        self._master._update_summary()
        self._master._status_var.set("重复文献合并标记已应用")
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1240x780")
        self.minsize(1080, 680)
        self.configure(bg="#f3f6fb")

        self._records: list[dict] = []
        self._q: queue.Queue = queue.Queue()
        self._scan_token = 0
        self._scanning = False
        self._total = 0
        self._done = 0
        self._last_output: Path | None = None
        self._row_by_file: dict[str, dict] = {}

        self._set_icon()
        self._configure_style()
        self._build_ui()
        self._dir_var.set(self._default_scan_dir())

    def _set_icon(self):
        ico = _resource_path("assets/pdf_manager.ico")
        try:
            if ico.exists():
                self.iconbitmap(str(ico))
        except tk.TclError:
            pass

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Microsoft YaHei UI", 9))
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Surface.TFrame", background="#ffffff")
        style.configure("Hero.TFrame", background="#152238")
        style.configure("HeroTitle.TLabel", background="#152238", foreground="#ffffff",
                        font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("HeroText.TLabel", background="#152238", foreground="#cbd7ea")
        style.configure("Section.TLabel", background="#ffffff", foreground="#1d2939",
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#667085")
        style.configure("Status.TLabel", background="#f3f6fb", foreground="#42526e")
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 7))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.configure("Danger.TButton", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.configure("TButton", padding=(10, 6))
        style.configure("Toolbutton.TButton", padding=(8, 5))
        style.configure("Treeview", rowheight=32, fieldbackground="#ffffff", background="#ffffff",
                        foreground="#1d2939", borderwidth=0)
        style.configure("Treeview.Heading", background="#f5f7fb", foreground="#344054",
                        font=("Microsoft YaHei UI", 9, "bold"), relief=tk.FLAT)
        style.map("Treeview", background=[("selected", "#cfe8ff")], foreground=[("selected", "#0f172a")])
        style.configure("Horizontal.TProgressbar", troughcolor="#dde5ef", background="#2f80ed")

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._build_footer()

    def _build_header(self):
        header = ttk.Frame(self, style="Hero.TFrame", padding=(18, 16))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        mark = tk.Canvas(header, width=56, height=56, bg="#152238", bd=0, highlightthickness=0)
        mark.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        mark.create_oval(2, 2, 54, 54, fill="#2f80ed", outline="")
        mark.create_rectangle(18, 12, 39, 44, fill="#ffffff", outline="")
        mark.create_polygon(32, 12, 39, 19, 32, 19, fill="#d9e9ff", outline="")
        mark.create_text(28, 29, text="PDF", fill="#d92d20", font=("Segoe UI", 8, "bold"))
        mark.create_line(20, 37, 36, 37, fill="#2f80ed", width=2)

        ttk.Label(header, text=APP_TITLE, style="HeroTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(
            header,
            text="国标命名、硕博论文识别、BibTeX/RIS、Obsidian 笔记和第三方文献软件导入。",
            style="HeroText.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(4, 0))

        self._summary_vars = {
            "all": tk.StringVar(value="0\nPDF"),
            "paper": tk.StringVar(value="0\n论文"),
            "review": tk.StringVar(value="0\n待复核"),
            "error": tk.StringVar(value="0\n失败"),
        }
        summary = ttk.Frame(header, style="Hero.TFrame")
        summary.grid(row=0, column=2, rowspan=2, sticky="e")
        for idx, (key, label) in enumerate((("all", "总数"), ("paper", "论文"), ("review", "复核"), ("error", "失败"))):
            box = tk.Frame(summary, bg="#22304a", padx=12, pady=8)
            box.grid(row=0, column=idx, padx=(8, 0), sticky="e")
            tk.Label(box, textvariable=self._summary_vars[key], bg="#22304a", fg="#ffffff",
                     font=("Microsoft YaHei UI", 12, "bold"), justify=tk.CENTER).pack()
            tk.Label(box, text=label, bg="#22304a", fg="#aab7cf", font=("Microsoft YaHei UI", 8)).pack()

    def _build_toolbar(self):
        shell = ttk.Frame(self, style="Surface.TFrame", padding=(14, 12))
        shell.grid(row=1, column=0, sticky="ew", padx=14, pady=(14, 10))
        shell.columnconfigure(1, weight=1)

        ttk.Label(shell, text="扫描文件夹", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self._dir_var = tk.StringVar()
        ttk.Entry(shell, textvariable=self._dir_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0), padx=(0, 10))
        ttk.Button(shell, text="选择文件夹", command=self._browse).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        self._scan_btn = ttk.Button(shell, text="开始扫描", style="Primary.TButton", command=self._start_scan)
        self._scan_btn.grid(row=1, column=3, sticky="ew")

        options = ttk.Frame(shell, style="Surface.TFrame")
        options.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self._recursive_var = tk.BooleanVar(value=False)
        self._network_var = tk.BooleanVar(value=True)
        self._obsidian_var = tk.BooleanVar(value=True)
        self._style_var = tk.StringVar(value="GB/T 7714")
        self._obsidian_dir_var = tk.StringVar(value="02_literature")
        self._obsidian_template_var = tk.StringVar(value="")
        ttk.Checkbutton(options, text="递归子目录", variable=self._recursive_var).pack(side=tk.LEFT)
        ttk.Checkbutton(options, text="联网补全 DOI / arXiv", variable=self._network_var).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Checkbutton(options, text="生成 Obsidian 文献笔记", variable=self._obsidian_var).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Label(options, text="引用风格", style="Muted.TLabel").pack(side=tk.LEFT, padx=(18, 6))
        ttk.Combobox(options, textvariable=self._style_var, values=list(STYLE_OPTIONS), state="readonly", width=12).pack(side=tk.LEFT)
        ttk.Label(options, text="默认按 GB/T 7714 引用格式命名，待复核项不会被静默当作论文处理。", style="Muted.TLabel").pack(side=tk.RIGHT)

        obsidian_opts = ttk.Frame(shell, style="Surface.TFrame")
        obsidian_opts.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        obsidian_opts.columnconfigure(3, weight=1)
        ttk.Label(obsidian_opts, text="Obsidian 目录", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(obsidian_opts, textvariable=self._obsidian_dir_var, width=18).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(obsidian_opts, text="模板", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(obsidian_opts, textvariable=self._obsidian_template_var).grid(row=0, column=3, sticky="ew", padx=(6, 8))
        ttk.Button(obsidian_opts, text="选择模板", command=self._browse_obsidian_template).grid(row=0, column=4, sticky="e")

        self._progress = ttk.Progressbar(shell, mode="determinate")
        self._progress.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(12, 0))

    def _build_table(self):
        body = ttk.Frame(self, style="Surface.TFrame", padding=(14, 12))
        body.grid(row=2, column=0, sticky="nsew", padx=14)
        body.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)

        top = ttk.Frame(body, style="Surface.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="扫描结果", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        primary_actions = ttk.Frame(top, style="Surface.TFrame")
        primary_actions.grid(row=0, column=1, sticky="e")
        buttons = [
            ("全选", self._select_all, "Toolbutton.TButton"),
            ("反选", self._invert_sel, "Toolbutton.TButton"),
            ("复核 / 编辑", self._open_review_dialog, "Accent.TButton"),
            ("加载上次结果", self._load_session, "Toolbutton.TButton"),
            ("导出索引 / 引用", self._export, "Primary.TButton"),
        ]
        for i, (text, command, btn_style) in enumerate(buttons):
            ttk.Button(primary_actions, text=text, style=btn_style, command=command).pack(
                side=tk.LEFT, padx=(0 if i == 0 else 6, 0)
            )

        secondary = ttk.Frame(body, style="Surface.TFrame")
        secondary.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(secondary, text="快捷操作", style="Muted.TLabel").pack(side=tk.LEFT)
        secondary_buttons = [
            ("重命名计划", self._write_rename_plan, "Toolbutton.TButton"),
            ("应用重命名", self._apply_rename, "Danger.TButton"),
            ("撤销重命名", self._undo_rename, "Toolbutton.TButton"),
            ("批量复核", self._open_batch_review_dialog, "Toolbutton.TButton"),
            ("重复合并", self._open_duplicate_dialog, "Toolbutton.TButton"),
            ("AI 阅读", self._open_ai_reading_dialog, "Accent.TButton"),
            ("打开输出目录", self._open_output, "Toolbutton.TButton"),
            ("Zotero 检查", self._open_zotero_review_dialog, "Toolbutton.TButton"),
            ("导入 Zotero", self._import_zotero, "Toolbutton.TButton"),
            ("导入 Obsidian", self._import_obsidian, "Toolbutton.TButton"),
        ]
        for text, command, btn_style in secondary_buttons:
            ttk.Button(secondary, text=text, style=btn_style, command=command).pack(side=tk.LEFT, padx=(8, 0))

        table_frame = ttk.Frame(body, style="Surface.TFrame")
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self._tree = _EditableTreeview(table_frame, edit_col="#8", on_edit=self._on_new_name_edit,
                                       columns=COLS, show="headings", selectmode="browse")
        for col in COLS:
            self._tree.heading(col, text=COL_LABELS[col])
            self._tree.column(col, width=COL_WIDTHS[col], minwidth=36 if col == "select" else 60,
                              stretch=col in {"title", "newname"},
                              anchor=tk.CENTER if col in {"select", "type", "confidence", "year"} else tk.W)
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self._tree.bind("<Button-1>", self._on_click_select)
        self._tree.bind("<Double-1>", self._maybe_open_review)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._update_detail())
        self._tree.tag_configure("paper", background="#edf8f1")
        self._tree.tag_configure("thesis", background="#eef4ff")
        self._tree.tag_configure("document", background="#ffffff")
        self._tree.tag_configure("unknown", background="#fff7df")
        self._tree.tag_configure("error", background="#fdecec")

    def _build_footer(self):
        footer = ttk.Frame(self, padding=(14, 10))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self._detail_var = tk.StringVar(value="选择文件后显示 DOI、作者、识别理由和复核提示。")
        ttk.Label(footer, textvariable=self._detail_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="准备就绪")
        ttk.Label(footer, textvariable=self._status_var, style="Status.TLabel").grid(row=0, column=1, sticky="e")

    def _default_scan_dir(self) -> str:
        return str(Path(sys.executable).parent) if getattr(sys, "frozen", False) else str(Path.cwd())

    def _browse(self):
        directory = filedialog.askdirectory(initialdir=self._dir_var.get() or str(Path.cwd()))
        if directory:
            self._dir_var.set(directory)

    def _cfg(self) -> dict:
        return {
            "recursive": self._recursive_var.get(),
            "enable_network": self._network_var.get(),
            "crossref_mailto": "",
            "min_paper_confidence": 0.75,
            "review_confidence_threshold": 0.45,
            "output_obsidian_notes": self._obsidian_var.get(),
            "output_bibtex": True,
            "output_ieee": True,
            "citation_style": STYLE_OPTIONS.get(self._style_var.get(), "gbt7714"),
            "obsidian_links": ["trajectory_optimization_kb", "02_literature"],
            "obsidian_literature_dir": self._obsidian_dir_var.get().strip() or "02_literature",
            "obsidian_note_template": self._obsidian_template_var.get().strip(),
        }

    def _browse_obsidian_template(self):
        selected = filedialog.askopenfilename(
            title="选择 Obsidian 笔记模板",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if selected:
            self._obsidian_template_var.set(selected)

    def _start_scan(self):
        scan_dir = self._dir_var.get().strip()
        if not scan_dir or not Path(scan_dir).is_dir():
            messagebox.showerror("路径无效", "请选择一个有效文件夹。")
            return
        if self._scanning:
            return
        self._scan_token += 1
        token = self._scan_token
        self._scanning = True
        self._scan_btn.configure(state=tk.DISABLED)
        self._clear_table()
        self._progress.configure(value=0, maximum=1)
        self._status_var.set("正在扫描 PDF...")
        self._detail_var.set("正在提取 PDF metadata、首页文本、DOI / arXiv 信息。")
        threading.Thread(target=self._scan_worker, args=(scan_dir, self._cfg(), token), daemon=True).start()
        self.after(80, lambda: self._poll_queue(token))

    def _scan_worker(self, scan_dir: str, cfg: dict, token: int):
        from pdf_manager import bibtex, citation, classifier, extractor, metadata, scanner

        bibtex.reset_keys()
        files = scanner.scan(scan_dir, cfg.get("recursive", False))
        self._q.put((token, "total", len(files)))
        for file_info in files:
            path: Path = file_info["path"]
            rec = self._base_record(path, scan_dir, file_info)
            try:
                ext = extractor.extract(path)
                rec["page_count"] = ext.get("page_count", 0)
                rec["doi"] = ext.get("doi")
                rec["arxiv_id"] = ext.get("arxiv_id")
                rec["needs_review"] = ext.get("needs_review", False)
                cls = classifier.classify(ext, cfg)
                rec["detected_type"] = cls["detected_type"]
                rec["confidence"] = cls["confidence"]
                rec["needs_review"] = cls["needs_review"]
                rec["classification_reason"] = cls.get("classification_reason")
                rec["thesis_type"] = cls.get("thesis_type")
                meta = metadata.fetch(ext, cfg)
                for key in ("title", "authors", "year", "venue", "volume", "issue", "pages", "publisher", "place", "advisor"):
                    if meta.get(key):
                        rec[key] = meta[key]
                if meta.get("summary"):
                    rec["notes"] = meta["summary"]
                if rec["detected_type"] in {"paper", "thesis"}:
                    rec["ieee_citation"] = citation.generate(rec, "ieee")
                    rec["citation"] = citation.generate(rec, cfg.get("citation_style", "gbt7714"))
                    key, bib_entry = bibtex.generate(rec)
                    rec["bibtex_key"] = key
                    rec["_bibtex_entry"] = bib_entry
                    rec["tag"] = key
                elif rec.get("title"):
                    rec["tag"] = rec["title"]
            except Exception as exc:
                rec["error"] = str(exc)
                rec["needs_review"] = True
                rec["classification_reason"] = rec.get("classification_reason") or "Processing failed"
            self._q.put((token, "record", rec))
        self._q.put((token, "done", None))

    def _base_record(self, path: Path, scan_dir: str, file_info: dict) -> dict:
        try:
            relative_path = str(path.relative_to(scan_dir))
        except ValueError:
            relative_path = str(path)
        return {
            "original_filename": path.name,
            "absolute_path": str(path.resolve()),
            "relative_path": relative_path,
            "file_size": file_info.get("file_size", 0),
            "page_count": 0,
            "detected_type": "document",
            "confidence": 0.0,
            "title": None,
            "authors": [],
            "year": None,
            "venue": None,
            "volume": None,
            "issue": None,
            "pages": None,
            "doi": None,
            "arxiv_id": None,
            "url": None,
            "publisher": None,
            "place": None,
            "advisor": None,
            "ieee_citation": None,
            "citation": None,
            "bibtex_key": None,
            "tag": path.stem,
            "duplicate_group": None,
            "merged_into": None,
            "needs_review": False,
            "classification_reason": None,
            "thesis_type": None,
            "notes": None,
            "error": None,
            "_bibtex_entry": None,
            "_suggested_name": None,
        }

    def _poll_queue(self, token: int):
        try:
            while True:
                msg_token, msg, data = self._q.get_nowait()
                if msg_token != token:
                    continue
                if msg == "total":
                    self._total = data
                    self._done = 0
                    self._progress.configure(maximum=max(data, 1), value=0)
                elif msg == "record":
                    self._records.append(data)
                    self._add_row(data)
                    self._done += 1
                    self._progress.configure(value=self._done)
                    self._status_var.set(f"扫描中：{self._done}/{self._total}")
                    self._update_summary()
                elif msg == "done":
                    self._scanning = False
                    self._scan_btn.configure(state=tk.NORMAL)
                    self._progress.configure(value=self._total)
                    self._update_summary()
                    self._status_var.set(self._summary_text())
                    self._detail_var.set("扫描完成。可复核编辑后再导出；导出会保存 session.json 供下次加载。")
                    return
        except queue.Empty:
            pass
        if self._scanning and self._scan_token == token:
            self.after(100, lambda: self._poll_queue(token))

    def _add_row(self, rec: dict):
        iid = self._unique_iid(rec["absolute_path"])
        self._row_by_file[iid] = rec
        self._tree.insert("", tk.END, iid=iid, values=self._row_values(rec), tags=(self._row_tag(rec),))

    def _row_values(self, rec: dict) -> tuple:
        rec["_suggested_name"] = rec.get("_suggested_name") or _suggest_name(rec)
        id_text = rec.get("doi") or rec.get("arxiv_id") or ""
        title = rec.get("title") or rec.get("tag") or ""
        return (
            "☑",
            rec.get("original_filename", ""),
            _status_label(rec),
            f"{float(rec.get('confidence') or 0):.2f}",
            title[:120],
            rec.get("year") or "",
            id_text,
            rec.get("_suggested_name") or "",
        )

    def _row_tag(self, rec: dict) -> str:
        return "error" if rec.get("error") else rec.get("detected_type", "document")

    def _refresh_row(self, item: str):
        rec = self._row_by_file.get(item)
        if not rec:
            return
        self._tree.item(item, values=self._row_values(rec), tags=(self._row_tag(rec),))

    def _unique_iid(self, text: str) -> str:
        base = re.sub(r"\W+", "_", text)
        iid = base
        n = 2
        while iid in self._row_by_file:
            iid = f"{base}_{n}"
            n += 1
        return iid

    def _clear_table(self):
        self._records.clear()
        self._row_by_file.clear()
        self._last_output = None
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._update_summary()

    def _on_click_select(self, event):
        if self._tree.identify_region(event.x, event.y) != "cell" or self._tree.identify_column(event.x) != "#1":
            return
        item = self._tree.identify_row(event.y)
        if item:
            values = list(self._tree.item(item, "values"))
            values[0] = "☐" if values[0] == "☑" else "☑"
            self._tree.item(item, values=values)

    def _maybe_open_review(self, event):
        if self._tree.identify_region(event.x, event.y) != "cell":
            return
        if self._tree.identify_column(event.x) == "#8":
            return
        self._open_review_dialog()

    def _on_new_name_edit(self, item: str, new_name: str):
        rec = self._row_by_file.get(item)
        if rec:
            rec["_suggested_name"] = new_name

    def _selected_rows(self) -> list[tuple[str, dict, tuple]]:
        rows = []
        for item in self._tree.get_children():
            values = self._tree.item(item, "values")
            if values and values[0] == "☑":
                rec = self._row_by_file.get(item)
                if rec:
                    rows.append((item, rec, values))
        return rows

    def _selected_item(self) -> tuple[str, dict] | None:
        selection = self._tree.selection()
        if not selection:
            return None
        item = selection[0]
        rec = self._row_by_file.get(item)
        return (item, rec) if rec else None

    def _select_all(self):
        for item in self._tree.get_children():
            values = list(self._tree.item(item, "values"))
            values[0] = "☑"
            self._tree.item(item, values=values)

    def _invert_sel(self):
        for item in self._tree.get_children():
            values = list(self._tree.item(item, "values"))
            values[0] = "☐" if values[0] == "☑" else "☑"
            self._tree.item(item, values=values)

    def _open_review_dialog(self):
        selected = self._selected_item()
        if not selected:
            messagebox.showinfo("未选择文件", "请先选择一条记录。")
            return
        item, rec = selected
        ReviewDialog(self, item, rec)

    def _open_ai_reading_dialog(self):
        selected = self._selected_item()
        if not selected:
            messagebox.showinfo("未选择文献", "请先选择一条需要粗读/精读的记录。")
            return
        _item, rec = selected
        if rec.get("detected_type") not in {"paper", "thesis"}:
            if not messagebox.askyesno("非文献记录", "当前记录不是 paper/thesis，仍要生成 AI 阅读笔记吗？"):
                return
        AIReadingDialog(self, rec)

    def _load_session(self):
        scan_dir = self._dir_var.get().strip()
        default = Path(scan_dir) / OUTPUT_DIR_NAME / "session.json" if scan_dir else None
        if default and default.exists():
            path = default
        else:
            selected = filedialog.askopenfilename(
                title="选择 session.json",
                filetypes=[("PDF Manager session", "session.json"), ("JSON", "*.json")],
            )
            if not selected:
                return
            path = Path(selected)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records = data.get("records", [])
            if not isinstance(records, list):
                raise ValueError("session.json 格式不正确")
            self._clear_table()
            self._records.extend(records)
            self._dir_var.set(data.get("scan_dir") or str(path.parents[1]))
            cfg = data.get("config") or {}
            if cfg.get("citation_style") in STYLE_LABEL_BY_KEY:
                self._style_var.set(STYLE_LABEL_BY_KEY[cfg["citation_style"]])
            self._recursive_var.set(bool(cfg.get("recursive", False)))
            self._network_var.set(bool(cfg.get("enable_network", True)))
            self._obsidian_var.set(bool(cfg.get("output_obsidian_notes", True)))
            self._obsidian_dir_var.set(cfg.get("obsidian_literature_dir") or "02_literature")
            self._obsidian_template_var.set(cfg.get("obsidian_note_template") or "")
            for rec in self._records:
                self._add_row(rec)
            self._last_output = path.parent
            self._update_summary()
            self._status_var.set(f"已加载缓存：{path}")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def _export(self):
        out = self._write_current_export()
        if out:
            messagebox.showinfo("导出完成", f"索引、引用、BibTeX、Obsidian 笔记和 session.json 已输出到：\n{out}")
            self._status_var.set(f"已导出：{out}")

    def _write_current_export(self) -> Path | None:
        scan_dir = self._dir_var.get().strip()
        if not scan_dir or not self._records:
            messagebox.showinfo("没有可导出内容", "请先扫描或加载上次结果。")
            return None
        try:
            from pdf_manager import writers

            out = writers.write_all(self._records, scan_dir, self._cfg())
            self._last_output = out
            return out
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))
            return None

    def _ensure_export(self) -> Path | None:
        scan_dir = self._dir_var.get().strip()
        if not scan_dir:
            messagebox.showinfo("未选择文件夹", "请先选择扫描文件夹。")
            return None
        target = self._last_output or Path(scan_dir) / OUTPUT_DIR_NAME
        if target.exists() and (target / "session.json").exists():
            return target
        if not self._records:
            messagebox.showinfo("没有可导入内容", "请先扫描或加载上次结果。")
            return None
        return self._write_current_export()

    def _import_zotero(self):
        out = self._write_current_export()
        if not out:
            return
        from pdf_manager import integrations

        summary = integrations.zotero_export_summary(self._records)
        ris = out / "references.ris"
        bib = out / "references.bib"
        target = ris if ris.exists() and ris.stat().st_size else bib
        if summary["omitted"]:
            report = out / "zotero_import_report.md"
            prompt = ZoteroImportPrompt(self, summary, report)
            self.wait_window(prompt)
            if prompt.result == "review":
                self._open_zotero_review_dialog()
                return
            if prompt.result == "report":
                self._open_zotero_report(out)
                return
            if prompt.result != "continue":
                return
        if not target.exists() or not target.stat().st_size:
            messagebox.showinfo("没有可导入文献", "当前结果中没有论文或学位论文。请先在 Zotero 检查面板中复核 skipped 条目。")
            return
        try:
            os.startfile(str(target))
            self._status_var.set(f"已打开 Zotero 导入文件：{target.name}")
        except Exception as exc:
            messagebox.showerror("打开失败", f"请在 Zotero 中手动导入：\n{target}\n\n{exc}")

    def _import_obsidian(self):
        out = self._write_current_export()
        if not out:
            return
        vault = filedialog.askdirectory(title="选择 Obsidian Vault 根目录")
        if not vault:
            return
        try:
            from pdf_manager import integrations

            subdir = self._obsidian_dir_var.get().strip() or "02_literature"
            count = integrations.copy_obsidian_notes(out, Path(vault), subdir)
            messagebox.showinfo("导入 Obsidian 完成", f"已复制 {count} 篇文献笔记到：\n{Path(vault) / subdir}")
            self._status_var.set(f"已导入 Obsidian：{count} 篇笔记")
        except Exception as exc:
            messagebox.showerror("导入 Obsidian 失败", str(exc))

    def _open_zotero_review_dialog(self):
        if not self._records:
            messagebox.showinfo("没有记录", "请先扫描或加载上次结果。")
            return
        ZoteroReviewDialog(self)

    def _open_zotero_report(self, out: Path | None = None):
        target = out or self._write_current_export()
        if not target:
            return
        report = target / "zotero_import_report.md"
        try:
            os.startfile(str(report))
            self._status_var.set(f"已打开 Zotero 导入报告：{report.name}")
        except Exception as exc:
            messagebox.showerror("打开失败", f"请手动打开：\n{report}\n\n{exc}")

    def _open_batch_review_dialog(self):
        rows = self._selected_rows()
        if not rows:
            rows = [
                (item, rec, self._tree.item(item, "values"))
                for item, rec in self._row_by_file.items()
                if rec.get("needs_review") or rec.get("detected_type") == "unknown"
            ]
        if not rows:
            messagebox.showinfo("没有待复核记录", "请先勾选记录，或扫描出待复核 PDF。")
            return
        BatchReviewDialog(self, rows)

    def _open_duplicate_dialog(self):
        if not self._records:
            messagebox.showinfo("没有记录", "请先扫描或加载上次结果。")
            return
        DuplicateDialog(self)

    def _write_rename_plan(self):
        scan_dir = self._dir_var.get().strip()
        if not scan_dir or not self._records:
            messagebox.showinfo("没有可导出内容", "请先扫描或加载上次结果。")
            return
        out = Path(scan_dir) / OUTPUT_DIR_NAME
        out.mkdir(parents=True, exist_ok=True)
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo("未选择文件", "请勾选需要进入重命名计划的 PDF。")
            return
        plan = out / "rename_plan.md"
        with open(plan, "w", encoding="utf-8") as f:
            f.write("# Rename Plan\n\n")
            f.write("| Status | Original | Suggested |\n|---|---|---|\n")
            for _item, rec, values in rows:
                f.write(f"| {_status_label(rec)} | {rec.get('original_filename', '')} | {values[7]} |\n")
        self._last_output = out
        messagebox.showinfo("重命名计划已生成", f"请先复核计划，再决定是否应用重命名。\n\n{plan}")

    def _apply_rename(self):
        rows = self._selected_rows()
        to_rename = []
        for item, rec, values in rows:
            new_name = _clean_filename(str(values[7]).strip())
            original = rec.get("original_filename", "")
            if not new_name or new_name == original:
                continue
            if Path(new_name).suffix.lower() != ".pdf":
                new_name += ".pdf"
            to_rename.append((item, rec, new_name))
        if not to_rename:
            messagebox.showinfo("无需重命名", "没有勾选需要重命名的文件，或建议文件名与原名一致。")
            return
        if not messagebox.askyesno("确认重命名", f"即将重命名 {len(to_rename)} 个 PDF。\n建议先生成并复核 rename_plan.md。是否继续？"):
            return
        success = failed = skipped = 0
        out = Path(self._dir_var.get().strip()) / OUTPUT_DIR_NAME
        out.mkdir(parents=True, exist_ok=True)
        for item, rec, new_name in to_rename:
            src = Path(rec["absolute_path"])
            dst = src.parent / new_name
            if dst.exists():
                skipped += 1
                continue
            try:
                src.rename(dst)
                from pdf_manager import renamer

                renamer.append_log(out, src, dst)
                rec["original_filename"] = new_name
                rec["absolute_path"] = str(dst.resolve())
                try:
                    rec["relative_path"] = str(dst.relative_to(self._dir_var.get().strip()))
                except ValueError:
                    rec["relative_path"] = str(dst)
                self._refresh_row(item)
                success += 1
            except Exception as exc:
                rec["error"] = str(exc)
                failed += 1
        try:
            from pdf_manager import renamer

            renamer.write_markdown_log(out)
        except Exception:
            pass
        self._status_var.set(f"重命名完成：成功 {success}，跳过 {skipped}，失败 {failed}")
        self._update_summary()

    def _undo_rename(self):
        scan_dir = self._dir_var.get().strip()
        if not scan_dir:
            messagebox.showinfo("未选择文件夹", "请先选择扫描文件夹。")
            return
        out = Path(scan_dir) / OUTPUT_DIR_NAME
        try:
            from pdf_manager import renamer

            results = renamer.undo_last_batch(out)
            undone = sum(1 for r in results if r.get("undo_status") == "undone")
            blocked = len(results) - undone
            renamer.write_markdown_log(out)
            messagebox.showinfo("撤销重命名完成", f"已撤销 {undone} 个文件；跳过 {blocked} 个。")
            self._status_var.set(f"撤销重命名：成功 {undone}，跳过 {blocked}")
        except Exception as exc:
            messagebox.showerror("撤销失败", str(exc))

    def _open_output(self):
        scan_dir = self._dir_var.get().strip()
        target = self._last_output or (Path(scan_dir) / OUTPUT_DIR_NAME if scan_dir else None)
        if target and target.exists():
            os.startfile(str(target))
            return
        messagebox.showinfo("输出目录不存在", "请先导出索引 / 引用。")

    def _update_detail(self):
        selected = self._selected_item()
        if not selected:
            return
        _item, rec = selected
        authors = _authors_to_text(rec.get("authors")) or "未知作者"
        identity = rec.get("doi") or rec.get("arxiv_id") or "无 DOI / arXiv"
        review = "需要人工复核" if rec.get("needs_review") else "无需复核"
        reason = rec.get("classification_reason") or "无识别理由"
        error = f"；错误：{rec['error']}" if rec.get("error") else ""
        self._detail_var.set(f"{_status_label(rec)} | {authors} | {identity} | {review} | {reason}{error}")

    def _update_summary(self):
        total = len(self._records)
        papers = sum(1 for rec in self._records if rec.get("detected_type") in {"paper", "thesis"})
        review = sum(1 for rec in self._records if rec.get("needs_review") or rec.get("detected_type") == "unknown")
        errors = sum(1 for rec in self._records if rec.get("error"))
        self._summary_vars["all"].set(f"{total}\nPDF")
        self._summary_vars["paper"].set(f"{papers}\n论文")
        self._summary_vars["review"].set(f"{review}\n待复核")
        self._summary_vars["error"].set(f"{errors}\n失败")

    def _summary_text(self) -> str:
        total = len(self._records)
        papers = sum(1 for rec in self._records if rec.get("detected_type") in {"paper", "thesis"})
        docs = sum(1 for rec in self._records if rec.get("detected_type") == "document")
        review = sum(1 for rec in self._records if rec.get("needs_review") or rec.get("detected_type") == "unknown")
        errors = sum(1 for rec in self._records if rec.get("error"))
        return f"完成：共 {total} 个 PDF，论文 {papers}，普通 PDF {docs}，待复核 {review}，失败 {errors}"


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
