import csv
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_RECORD_FIELDS = [
    "original_filename", "absolute_path", "relative_path", "file_size", "page_count",
    "detected_type", "confidence", "title", "authors", "year", "venue", "volume",
    "issue", "pages", "doi", "arxiv_id", "url", "publisher", "citation", "ieee_citation",
    "bibtex_key", "tag", "duplicate_group", "merged_into", "needs_review", "classification_reason",
    "thesis_type", "place", "advisor", "notes", "error",
]


def _detect_duplicates(records: list[dict]) -> list[dict]:
    from pdf_manager import duplicates

    return duplicates.mark_duplicates(records)


def write_all(records: list[dict], scan_dir: str, cfg: dict) -> Path:
    from pdf_manager import bibtex, citation, integrations
    from pdf_manager import obsidian as obs_mod

    out = Path(scan_dir) / "_pdf_manager_output"
    out.mkdir(parents=True, exist_ok=True)

    style = citation.normalize_style(cfg.get("citation_style", "gbt7714"))
    style_label = citation.style_label(style)
    records = _detect_duplicates(records)

    papers = [r for r in records if r.get("detected_type") in {"paper", "thesis"}]
    for rec in papers:
        if not rec.get("_bibtex_entry"):
            key, bib_entry = bibtex.generate(rec)
            rec["bibtex_key"] = key
            rec["_bibtex_entry"] = bib_entry
        rec["ieee_citation"] = rec.get("ieee_citation") or citation.generate(rec, "ieee")
        rec["citation"] = citation.generate(rec, style)
        rec["tag"] = rec.get("tag") or rec.get("bibtex_key")
    review = [r for r in records if r.get("needs_review")]
    errors = [r for r in records if r.get("error")]

    # pdf_index.csv
    with open(out / "pdf_index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_RECORD_FIELDS, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            row = {k: ("|".join(rec[k]) if k == "authors" and isinstance(rec.get(k), list) else rec.get(k, ""))
                   for k in _RECORD_FIELDS}
            w.writerow(row)

    # pdf_index.md
    with open(out / "pdf_index.md", "w", encoding="utf-8") as f:
        f.write("| Filename | Type | Confidence | Title | Year | DOI |\n")
        f.write("|---|---|---|---|---|---|\n")
        for rec in records:
            f.write(f"| {rec.get('original_filename','')} | {rec.get('detected_type','')} | "
                    f"{rec.get('confidence','')} | {rec.get('title','')} | "
                    f"{rec.get('year','')} | {rec.get('doi','')} |\n")

    # references_ieee.md
    if cfg.get("output_ieee", True):
        with open(out / "references_ieee.md", "w", encoding="utf-8") as f:
            f.write("# IEEE References\n\n")
            for i, rec in enumerate(papers, 1):
                cit = rec.get("ieee_citation") or ""
                f.write(f"[{i}] {cit}\n\n")

    # selected-style references
    with open(out / f"references_{style}.md", "w", encoding="utf-8") as f:
        f.write(f"# {style_label} References\n\n")
        for i, rec in enumerate(papers, 1):
            cit = rec.get("citation") or ""
            prefix = f"[{i}] " if style in {"ieee", "gbt7714"} else ""
            f.write(f"{prefix}{cit}\n\n")

    # references.bib
    if cfg.get("output_bibtex", True):
        with open(out / "references.bib", "w", encoding="utf-8") as f:
            for rec in papers:
                bib = rec.get("_bibtex_entry") or ""
                f.write(bib + "\n\n")

    # references.ris for Zotero and other reference managers
    (out / "references.ris").write_text(integrations.records_to_ris(records), encoding="utf-8")
    integrations.write_zotero_import_report(out, records)
    integrations.write_import_guide(out)

    # pdf_metadata.json
    serializable = []
    for rec in records:
        d = {k: rec.get(k) for k in _RECORD_FIELDS}
        serializable.append(d)
    with open(out / "pdf_metadata.json", "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    # session cache for GUI reload
    session = {
        "schema_version": 1,
        "scan_dir": str(Path(scan_dir).resolve()),
        "config": {
            "citation_style": style,
            "output_obsidian_notes": cfg.get("output_obsidian_notes", True),
            "recursive": cfg.get("recursive", False),
            "enable_network": cfg.get("enable_network", True),
            "obsidian_literature_dir": cfg.get("obsidian_literature_dir", "02_literature"),
            "obsidian_note_template": cfg.get("obsidian_note_template", ""),
        },
        "records": serializable,
    }
    with open(out / "session.json", "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    # review_needed.md
    with open(out / "review_needed.md", "w", encoding="utf-8") as f:
        f.write("# Files Needing Review\n\n")
        for rec in review:
            reason = rec.get("classification_reason") or ""
            f.write(f"- {rec.get('original_filename','')} (confidence={rec.get('confidence','')}; {reason})\n")

    # duplicate groups
    with open(out / "duplicates.md", "w", encoding="utf-8") as f:
        f.write("# Duplicate Groups\n\n")
        groups: dict[str, list[dict]] = {}
        for rec in records:
            if rec.get("duplicate_group"):
                groups.setdefault(rec["duplicate_group"], []).append(rec)
        if not groups:
            f.write("No duplicates detected.\n")
        for key, items in groups.items():
            f.write(f"## {key}\n\n")
            f.write("| File | Title | DOI | Merged into |\n|---|---|---|---|\n")
            for rec in items:
                f.write(
                    f"| {rec.get('original_filename','')} | {rec.get('title','')} | "
                    f"{rec.get('doi','')} | {rec.get('merged_into','')} |\n"
                )
            f.write("\n")

    # errors.log
    with open(out / "errors.log", "w", encoding="utf-8") as f:
        for rec in errors:
            f.write(f"{rec.get('absolute_path','')} | {rec.get('error','')}\n")

    # obsidian notes
    if cfg.get("output_obsidian_notes", True):
        notes_dir = out / "obsidian_notes"
        notes_dir.mkdir(exist_ok=True)
        for rec in papers:
            key = rec.get("bibtex_key") or "unknown"
            note = obs_mod.generate_note(rec, cfg)
            (notes_dir / f"{key}.md").write_text(note, encoding="utf-8")

    return out
