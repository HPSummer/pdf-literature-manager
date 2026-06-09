from __future__ import annotations

import shutil
from pathlib import Path


def citable_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("detected_type") in {"paper", "thesis"}]


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

## Obsidian

Copy the Markdown files in `obsidian_notes/` into your vault, for example:
`02_literature/`.

## 小绿鲸

Use the reference import feature and select `references.ris` first. If RIS is not accepted by your version, use `references.bib`.
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
