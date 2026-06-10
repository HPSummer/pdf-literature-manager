from __future__ import annotations

import shutil
from pathlib import Path


def citable_records(records: list[dict]) -> list[dict]:
    return [
        r for r in records
        if r.get("detected_type") in {"paper", "thesis"} and not r.get("needs_review")
    ]


def omitted_zotero_records(records: list[dict]) -> list[dict]:
    return [
        r for r in records
        if r.get("detected_type") not in {"paper", "thesis"} or r.get("needs_review")
    ]


def zotero_export_summary(records: list[dict]) -> dict:
    citable = citable_records(records)
    omitted = omitted_zotero_records(records)
    return {
        "total": len(records),
        "citable": len(citable),
        "omitted": len(omitted),
        "omitted_records": omitted,
    }


def write_zotero_import_report(out_dir: Path, records: list[dict]) -> Path:
    report = out_dir / "zotero_import_report.md"
    summary = zotero_export_summary(records)
    lines = [
        "# Zotero Import Report",
        "",
        f"- Total PDFs: {summary['total']}",
        f"- Exported to Zotero: {summary['citable']}",
        f"- Skipped: {summary['omitted']}",
        "",
        "Only records classified as `paper` or `thesis` are exported to `references.ris` and `references.bib`.",
        "Use batch review to fix metadata/type and clear `needs_review`, then export again.",
        "",
    ]
    if summary["omitted_records"]:
        lines.extend([
            "## Skipped Records",
            "",
            "| Filename | Type | Needs Review | Reason | Title |",
            "|---|---|---|---|---|",
        ])
        for rec in summary["omitted_records"]:
            lines.append(
                f"| {_md_cell(rec.get('original_filename'))} | "
                f"{_md_cell(rec.get('detected_type'))} | "
                f"{'yes' if rec.get('needs_review') else 'no'} | "
                f"{_md_cell(_zotero_skip_reason(rec))} | "
                f"{_md_cell(rec.get('title') or rec.get('tag'))} |"
            )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def _zotero_skip_reason(rec: dict) -> str:
    if rec.get("error"):
        return f"processing error: {rec.get('error')}"
    if rec.get("needs_review"):
        reason = rec.get("classification_reason") or ""
        return f"needs review before bibliographic export: {reason}" if reason else "needs review before bibliographic export"
    dtype = rec.get("detected_type") or "unknown"
    if dtype == "document":
        return "classified as ordinary PDF"
    if dtype == "unknown":
        return "literature type is unknown"
    return f"classified as {dtype}"


def ris_type(rec: dict) -> str:
    if rec.get("detected_type") == "thesis":
        return "THES"
    venue = (rec.get("venue") or "").lower()
    if any(k in venue for k in ("conference", "proceedings", "symposium", "workshop")):
        return "CONF"
    return "JOUR"


def records_to_ris(records: list[dict]) -> str:
    entries: list[str] = []
    for rec in citable_records(records):
        lines = [f"TY  - {ris_type(rec)}"]
        for author in rec.get("authors") or []:
            if author:
                lines.append(f"AU  - {author}")
        _add(lines, "TI", rec.get("title"))
        _add(lines, "PY", rec.get("year"))
        if rec.get("detected_type") == "thesis":
            _add(lines, "PB", rec.get("venue") or rec.get("publisher"))
        else:
            _add(lines, "JO", rec.get("venue"))
            _add(lines, "T2", rec.get("venue"))
        _add(lines, "VL", rec.get("volume"))
        _add(lines, "IS", rec.get("issue"))
        _add(lines, "SP", _first_page(rec.get("pages")))
        _add(lines, "EP", _last_page(rec.get("pages")))
        _add(lines, "DO", rec.get("doi"))
        _add(lines, "UR", rec.get("url"))
        if rec.get("arxiv_id") and not rec.get("url"):
            lines.append(f"UR  - https://arxiv.org/abs/{rec['arxiv_id']}")
        lines.append("ER  -")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + ("\n" if entries else "")


def write_import_guide(out_dir: Path) -> Path:
    guide = out_dir / "import_guide.md"
    guide.write_text(
        """# Third-party Import Guide

## Zotero

Import `references.bib` or `references.ris` from Zotero: File -> Import.
If fewer items appear in Zotero than expected, check `zotero_import_report.md` and use batch review to fix metadata/type and clear `needs_review`.

## Obsidian

Copy the Markdown files in `obsidian_notes/` into your vault, for example:
`02_literature/`.
""",
        encoding="utf-8",
    )
    return guide


def copy_obsidian_notes(out_dir: Path, vault_dir: Path, subdir: str = "02_literature") -> int:
    notes_dir = out_dir / "obsidian_notes"
    if not notes_dir.exists():
        raise FileNotFoundError(f"Obsidian notes directory not found: {notes_dir}")
    target = vault_dir / subdir
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in notes_dir.glob("*.md"):
        shutil.copy2(src, target / src.name)
        count += 1
    return count


def _add(lines: list[str], tag: str, value) -> None:
    if value:
        lines.append(f"{tag}  - {value}")


def _md_cell(value) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _first_page(pages) -> str:
    if not pages:
        return ""
    text = str(pages)
    return text.split("-")[0].strip()


def _last_page(pages) -> str:
    if not pages:
        return ""
    text = str(pages)
    parts = text.split("-")
    return parts[-1].strip() if len(parts) > 1 else ""
