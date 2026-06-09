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
            ("venue", "期刊 / 会议", tk.StringVar(value=self._rec.get("venue") or "")),
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
        ttk.Checkbutton(options, text="递归子目录", variable=self._recursive_var).pack(side=tk.LEFT)
        ttk.Checkbutton(options, text="联网补全 DOI / arXiv", variable=self._network_var).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Checkbutton(options, text="生成 Obsidian 文献笔记", variable=self._obsidian_var).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Label(options, text="引用风格", style="Muted.TLabel").pack(side=tk.LEFT, padx=(18, 6))
        ttk.Combobox(options, textvariable=self._style_var, values=list(STYLE_OPTIONS), state="readonly", width=12).pack(side=tk.LEFT)
        ttk.Label(options, text="默认按 GB/T 7714 引用格式命名，待复核项不会被静默当作论文处理。", style="Muted.TLabel").pack(side=tk.RIGHT)

        self._progress = ttk.Progressbar(shell, mode="determinate")
        self._progress.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 0))

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
            ("打开输出目录", self._open_output, "Toolbutton.TButton"),
            ("导入 Zotero", self._import_zotero, "Toolbutton.TButton"),
            ("导入 Obsidian", self._import_obsidian, "Toolbutton.TButton"),
            ("导入小绿鲸", self._import_xiaolvjing, "Toolbutton.TButton"),
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
        }

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
                for key in ("title", "authors", "year", "venue", "volume", "issue", "pages", "publisher"):
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
            "ieee_citation": None,
            "citation": None,
            "bibtex_key": None,
            "tag": path.stem,
            "duplicate_group": None,
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
            for rec in self._records:
                self._add_row(rec)
            self._last_output = path.parent
            self._update_summary()
            self._status_var.set(f"已加载缓存：{path}")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def _export(self):
        scan_dir = self._dir_var.get().strip()
        if not scan_dir or not self._records:
            messagebox.showinfo("没有可导出内容", "请先扫描或加载上次结果。")
            return
        try:
            from pdf_manager import writers

            out = writers.write_all(self._records, scan_dir, self._cfg())
            self._last_output = out
            messagebox.showinfo("导出完成", f"索引、引用、BibTeX、Obsidian 笔记和 session.json 已输出到：\n{out}")
            self._status_var.set(f"已导出：{out}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

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
        try:
            from pdf_manager import writers

            out = writers.write_all(self._records, scan_dir, self._cfg())
            self._last_output = out
            return out
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))
            return None

    def _import_zotero(self):
        out = self._ensure_export()
        if not out:
            return
        ris = out / "references.ris"
        bib = out / "references.bib"
        target = ris if ris.exists() and ris.stat().st_size else bib
        if not target.exists():
            messagebox.showinfo("没有可导入文献", "当前结果中没有论文或学位论文。")
            return
        try:
            os.startfile(str(target))
            self._status_var.set(f"已打开 Zotero 导入文件：{target.name}")
        except Exception as exc:
            messagebox.showerror("打开失败", f"请在 Zotero 中手动导入：\n{target}\n\n{exc}")

    def _import_xiaolvjing(self):
        out = self._ensure_export()
        if not out:
            return
        ris = out / "references.ris"
        bib = out / "references.bib"
        if not ris.exists() or not ris.stat().st_size:
            messagebox.showinfo("没有可导入文献", "当前结果中没有论文或学位论文。")
            return
        try:
            os.startfile(str(ris))
            self._status_var.set("已打开小绿鲸兼容 RIS 文件")
        except Exception as exc:
            messagebox.showerror("打开失败", f"请在小绿鲸中手动导入 references.ris；若不兼容可导入 references.bib。\n\n{ris}\n{bib}\n\n{exc}")

    def _import_obsidian(self):
        out = self._ensure_export()
        if not out:
            return
        vault = filedialog.askdirectory(title="选择 Obsidian Vault 根目录")
        if not vault:
            return
        try:
            from pdf_manager import integrations

            count = integrations.copy_obsidian_notes(out, Path(vault), "02_literature")
            messagebox.showinfo("导入 Obsidian 完成", f"已复制 {count} 篇文献笔记到：\n{Path(vault) / '02_literature'}")
            self._status_var.set(f"已导入 Obsidian：{count} 篇笔记")
        except Exception as exc:
            messagebox.showerror("导入 Obsidian 失败", str(exc))

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
        for item, rec, new_name in to_rename:
            src = Path(rec["absolute_path"])
            dst = src.parent / new_name
            if dst.exists():
                skipped += 1
                continue
            try:
                src.rename(dst)
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
        self._status_var.set(f"重命名完成：成功 {success}，跳过 {skipped}，失败 {failed}")
        self._update_summary()

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
