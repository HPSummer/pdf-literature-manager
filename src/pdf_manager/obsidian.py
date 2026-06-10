from __future__ import annotations

from datetime import date
from pathlib import Path


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def generate_note(rec: dict, cfg: dict) -> str:
    from pdf_manager import citation

    key = rec.get("bibtex_key", "unknown")
    title = rec.get("title") or rec.get("original_filename", "")
    authors = rec.get("authors") or []
    year = rec.get("year") or ""
    venue = rec.get("venue") or ""
    doi = rec.get("doi") or ""
    arxiv_id = rec.get("arxiv_id") or ""
    tags = []
    for link in cfg.get("obsidian_links", []):
        tags.append(link)

    authors_str = "; ".join(authors)
    today = date.today().isoformat()
    style = citation.normalize_style(cfg.get("citation_style", "gbt7714"))
    style_label = citation.style_label(style)
    selected_citation = rec.get("citation") or citation.generate(rec, style)
    ieee_citation = rec.get("ieee_citation") or citation.generate(rec, "ieee")
    context = _SafeDict({
        "citekey": key,
        "title": title,
        "authors": authors_str,
        "year": year,
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "style": style,
        "style_label": style_label,
        "citation": selected_citation,
        "ieee_citation": ieee_citation,
        "summary": rec.get("summary") or rec.get("notes") or "",
        "type": rec.get("detected_type") or "",
        "thesis_type": rec.get("thesis_type") or "",
        "place": rec.get("place") or "",
        "advisor": rec.get("advisor") or "",
        "date_added": today,
    })
    template = _load_template(cfg.get("obsidian_note_template"))
    if template:
        return template.format_map(context)

    lines = [
        "---",
        f"citekey: {key}",
        f"title: \"{title}\"",
        f"authors: [{authors_str}]",
        f"year: {year}",
        f"venue: {venue}",
        f"citation_style: {style}",
    ]
    if doi:
        lines.append(f"doi: {doi}")
    if arxiv_id:
        lines.append(f"arxiv: {arxiv_id}")
    lines.append(f"date_added: {today}")
    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {t}")
    lines += [
        "---",
        "",
        f"# {title}",
        "",
        "## Abstract",
        "",
        rec.get("summary") or "_No abstract available._",
        "",
        "## Key Contributions",
        "",
        "- ",
        "",
        "## Notes",
        "",
        "",
        "## References",
        "",
        f"{style_label}:",
        f"> {selected_citation}",
        "",
        "IEEE:",
        f"> {ieee_citation}",
        "",
        f"BibTeX key: `{key}`",
    ]
    return "\n".join(lines)


def _load_template(template_ref: str | None) -> str:
    if not template_ref:
        return ""
    p = Path(template_ref)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return str(template_ref)
