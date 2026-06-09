import re
import unicodedata

_used_keys: set[str] = set()

CONF_KW = {"conf", "proc", "symposium", "workshop"}


def _ascii_clean(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-zA-Z0-9]", "", s.encode("ascii", "ignore").decode())


def _make_key(rec: dict) -> str:
    authors = rec.get("authors") or []
    first_last = ""
    if authors:
        parts = authors[0].strip().split()
        first_last = _ascii_clean(parts[-1]) if parts else ""
    year = rec.get("year") or ""
    title = rec.get("title") or ""
    first_word = _ascii_clean(title.split()[0]) if title.split() else ""
    base = f"{first_last}{year}{first_word}" or "unknown"
    key = base
    suffix_idx = ord("b")
    while key in _used_keys:
        key = base + "_" + chr(suffix_idx)
        suffix_idx += 1
    _used_keys.add(key)
    return key


def _entry_type(rec: dict) -> str:
    if rec.get("detected_type") == "thesis":
        return "phdthesis" if rec.get("thesis_type") == "doctoral" else "mastersthesis"
    venue = (rec.get("venue") or "").lower()
    if rec.get("arxiv_id") and not rec.get("doi"):
        return "misc"
    if any(kw in venue for kw in CONF_KW):
        return "inproceedings"
    if venue:
        return "article"
    return "misc"


def generate(rec: dict) -> tuple[str, str]:
    entry_type = _entry_type(rec)
    key = _make_key(rec)

    fields: list[str] = []

    def add(field, val):
        if val:
            fields.append(f"  {field} = {{{val}}}")

    authors = rec.get("authors") or []
    add("author", " and ".join(authors) if authors else None)
    add("title", rec.get("title"))
    add("year", rec.get("year"))
    venue = rec.get("venue")
    if entry_type in {"mastersthesis", "phdthesis"}:
        add("school", venue)
    elif entry_type == "article":
        add("journal", venue)
    elif entry_type == "inproceedings":
        add("booktitle", venue)
    else:
        add("howpublished", f"arXiv:{rec['arxiv_id']}" if rec.get("arxiv_id") else venue)
    add("volume", rec.get("volume"))
    add("number", rec.get("issue"))
    add("pages", rec.get("pages"))
    add("publisher", rec.get("publisher"))
    add("doi", rec.get("doi"))
    add("url", rec.get("url"))

    body = ",\n".join(fields)
    bibtex = f"@{entry_type}{{{key},\n{body}\n}}"
    return key, bibtex


def reset_keys():
    """Reset used keys registry (for testing)."""
    _used_keys.clear()
