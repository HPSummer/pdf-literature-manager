from __future__ import annotations

import re


STYLE_LABELS = {
    "ieee": "IEEE",
    "apa": "APA",
    "mla": "MLA",
    "chicago": "Chicago",
    "gbt7714": "GB/T 7714",
}


def normalize_style(style: str | None) -> str:
    key = (style or "gbt7714").strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "gb": "gbt7714",
        "gbt": "gbt7714",
        "gbt7714": "gbt7714",
        "gbt77142015": "gbt7714",
        "chicagoauthor": "chicago",
    }
    key = aliases.get(key, key)
    return key if key in STYLE_LABELS else "gbt7714"


def style_label(style: str | None) -> str:
    return STYLE_LABELS[normalize_style(style)]


def supported_styles() -> list[str]:
    return list(STYLE_LABELS)


def generate(rec: dict, style: str | None = "gbt7714") -> str:
    style = normalize_style(style)
    if style == "apa":
        return _apa(rec)
    if style == "mla":
        return _mla(rec)
    if style == "chicago":
        return _chicago(rec)
    if style == "ieee":
        return _ieee(rec)
    return _gbt7714(rec)


def generate_all(rec: dict) -> dict[str, str]:
    return {style: generate(rec, style) for style in supported_styles()}


def filename_from_gbt(rec: dict) -> str:
    text = generate(rec, "gbt7714")
    text = text.rstrip(".")
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    text = text.replace("[", "［").replace("]", "］")
    return (text[:150] or "untitled") + ".pdf"


def _clean(value) -> str:
    return str(value).strip() if value is not None else ""


def _title(rec: dict) -> str:
    return _clean(rec.get("title") or rec.get("original_filename"))


def _venue(rec: dict) -> str:
    return _clean(rec.get("venue"))


def _year(rec: dict) -> str:
    return _clean(rec.get("year")) or "n.d."


def _doi_suffix(rec: dict, prefix: str = "doi: ") -> str:
    doi = _clean(rec.get("doi"))
    return f"{prefix}{doi}" if doi else ""


def _join_sentences(parts: list[str]) -> str:
    cleaned = [p.strip(" ,.") for p in parts if p and p.strip(" ,.")]
    return ". ".join(cleaned) + "." if cleaned else ""


def _author_initials(parts: list[str]) -> str:
    return " ".join(f"{p[0].upper()}." for p in parts if p)


def _ieee_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    if len(authors) > 3:
        return _ieee_name(authors[0]) + " et al."
    return " and ".join(_ieee_name(a) for a in authors)


def _ieee_name(name: str) -> str:
    parts = name.strip().split()
    if len(parts) < 2:
        return name.strip()
    return f"{_author_initials(parts[:-1])} {parts[-1]}"


def _apa_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    names = []
    for author in authors[:20]:
        parts = author.strip().split()
        if len(parts) < 2:
            names.append(author.strip())
        else:
            names.append(f"{parts[-1]}, {_author_initials(parts[:-1])}")
    if len(authors) > 20:
        names.append("...")
        names.append(_apa_authors([authors[-1]]))
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def _plain_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    return ", ".join(authors[:-1]) + f", and {authors[-1]}"


def _mla_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]}, and {authors[1]}"
    return f"{authors[0]}, et al."


def _gbt_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    if len(authors) > 3:
        return ", ".join(authors[:3]) + ", 等"
    return ", ".join(authors)


def _article_tail(rec: dict, style: str) -> str:
    volume = _clean(rec.get("volume"))
    issue = _clean(rec.get("issue"))
    pages = _clean(rec.get("pages"))
    if style == "apa":
        tail = ""
        if volume:
            tail += volume
        if issue:
            tail += f"({issue})"
        if pages:
            tail += f", {pages}"
        return tail
    if style == "gbt":
        tail = ""
        if volume:
            tail += volume
        if issue:
            tail += f"({issue})"
        if pages:
            tail += f": {pages}" if tail else pages
        return tail
    parts = []
    if volume:
        parts.append(f"vol. {volume}")
    if issue:
        parts.append(f"no. {issue}")
    if pages:
        parts.append(f"pp. {pages}")
    return ", ".join(parts)


def _ieee(rec: dict) -> str:
    parts = []
    authors = _ieee_authors(rec.get("authors") or [])
    if authors:
        parts.append(authors + ",")
    title = _title(rec)
    if title:
        parts.append(f'"{title},"')
    venue = _venue(rec)
    if venue:
        parts.append(venue + ",")
    tail = _article_tail(rec, "ieee")
    if tail:
        parts.append(tail + ",")
    year = _clean(rec.get("year"))
    if year:
        parts.append(year + ",")
    doi = _doi_suffix(rec)
    if doi:
        parts.append(doi + ".")
    return " ".join(parts).rstrip(" ,")


def _apa(rec: dict) -> str:
    authors = _apa_authors(rec.get("authors") or [])
    year = _year(rec)
    title = _title(rec)
    venue = _venue(rec)
    tail = _article_tail(rec, "apa")
    doi = _doi_suffix(rec, "https://doi.org/")
    parts = []
    if authors:
        parts.append(authors)
    parts.append(f"({year})")
    if title:
        parts.append(title)
    journal = venue
    if tail:
        journal = f"{journal}, {tail}" if journal else tail
    if journal:
        parts.append(journal)
    if doi:
        parts.append(doi)
    return _join_sentences(parts)


def _mla(rec: dict) -> str:
    authors = _mla_authors(rec.get("authors") or [])
    title = _title(rec)
    venue = _venue(rec)
    tail = _article_tail(rec, "mla")
    year = _year(rec)
    doi = _doi_suffix(rec)
    parts = []
    if authors:
        parts.append(authors)
    if title:
        parts.append(f'"{title}"')
    if venue:
        venue_part = venue
        if tail:
            venue_part += f", {tail}"
        venue_part += f", {year}"
        parts.append(venue_part)
    elif year:
        parts.append(year)
    if doi:
        parts.append(doi)
    return _join_sentences(parts)


def _chicago(rec: dict) -> str:
    authors = _plain_authors(rec.get("authors") or [])
    title = _title(rec)
    venue = _venue(rec)
    tail = _article_tail(rec, "chicago")
    year = _year(rec)
    doi = _doi_suffix(rec)
    parts = []
    if authors:
        parts.append(authors)
    if title:
        parts.append(f'"{title}"')
    source = venue
    if tail:
        source = f"{source} {tail}" if source else tail
    if year and year != "n.d.":
        source = f"{source} ({year})" if source else year
    if source:
        parts.append(source)
    if doi:
        parts.append(doi)
    return _join_sentences(parts)


def _gbt7714(rec: dict) -> str:
    authors = _gbt_authors(rec.get("authors") or [])
    title = _title(rec)
    venue = _venue(rec)
    year = _year(rec)
    doi = _doi_suffix(rec)
    parts = []
    if authors:
        parts.append(authors)
    if title:
        mark = "[D]" if rec.get("detected_type") == "thesis" else "[J]"
        parts.append(f"{title}{mark}")
    if rec.get("detected_type") == "thesis":
        place = _clean(rec.get("place"))
        school = venue or _clean(rec.get("publisher"))
        source = f"{place}: {school}" if place and school else (school or place)
        if year and year != "n.d.":
            source = f"{source}, {year}" if source else year
    else:
        source = venue
        if year and year != "n.d.":
            source = f"{source}, {year}" if source else year
        tail = _article_tail(rec, "gbt")
        if tail:
            source = f"{source}, {tail}" if source else tail
    if source:
        parts.append(source)
    if doi:
        parts.append(doi)
    return ". ".join(p.strip(" .") for p in parts if p and p.strip(" .")) + "."
