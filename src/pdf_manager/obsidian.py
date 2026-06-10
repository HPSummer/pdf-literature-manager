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
    gbt_citation = rec.get("gbt_citation") or citation.generate(rec, "gbt7714")
    ieee_citation = rec.get("ieee_citation") or citation.generate(rec, "ieee")
    zotero_key = rec.get("zotero_key") or rec.get("bibtex_key") or key
    school = rec.get("school") or (rec.get("venue") if rec.get("detected_type") == "thesis" else "") or ""
    place = rec.get("place") or ""
    context = _SafeDict({
        "citekey": key,
        "bibtex_key": key,
        "zotero_key": zotero_key,
        "title": title,
        "authors": authors_str,
        "year": year,
        "venue": venue,
        "school": school,
        "place": place,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "style": style,
        "style_label": style_label,
        "citation": selected_citation,
        "citation_gbt": gbt_citation,
        "ieee_citation": ieee_citation,
        "citation_ieee": ieee_citation,
        "summary": rec.get("summary") or rec.get("notes") or "",
        "type": rec.get("detected_type") or "",
        "thesis_type": rec.get("thesis_type") or "",
        "advisor": rec.get("advisor") or "",
        "date_added": today,
    })
    template = _load_template(cfg.get("obsidian_note_template"))
    if template:
        return template.format_map(context)

    lines = [
        "---",
        f"citekey: {_yaml_scalar(key)}",
        f"zotero_key: {_yaml_scalar(zotero_key)}",
        f"title: {_yaml_scalar(title)}",
        *_yaml_list_field("authors", authors),
        f"year: {_yaml_scalar(year)}",
        f"venue: {_yaml_scalar(venue)}",
        f"school: {_yaml_scalar(school)}",
        f"place: {_yaml_scalar(place)}",
        f"type: {_yaml_scalar(rec.get('detected_type') or '')}",
        f"thesis_type: {_yaml_scalar(rec.get('thesis_type') or '')}",
        f"advisor: {_yaml_scalar(rec.get('advisor') or '')}",
        f"citation_style: {_yaml_scalar(style)}",
    ]
    if doi:
        lines.append(f"doi: {_yaml_scalar(doi)}")
    if arxiv_id:
        lines.append(f"arxiv: {_yaml_scalar(arxiv_id)}")
    lines.append(f"date_added: {_yaml_scalar(today)}")
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
        "GB/T 7714:",
        f"> {gbt_citation}",
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


def _yaml_scalar(value) -> str:
    text = str(value or "")
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _yaml_list(values) -> list[str]:
    items = values or []
    if not items:
        return []
    return [f"  - {_yaml_scalar(v)}" for v in items]


def _yaml_list_field(key: str, values) -> list[str]:
    items = values or []
    if not items:
        return [f"{key}: []"]
    return [f"{key}:"] + _yaml_list(items)
