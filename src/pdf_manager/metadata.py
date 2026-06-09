from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import requests

log = logging.getLogger(__name__)


def _crossref(doi: str, mailto: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi}"
    params = {"mailto": mailto} if mailto else {}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        msg = r.json().get("message", {})
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in msg.get("author", [])
        ]
        date_parts = (msg.get("published-print") or msg.get("published-online") or {}).get("date-parts", [[None]])
        year = str(date_parts[0][0]) if date_parts and date_parts[0][0] else None
        title_list = msg.get("title", [])
        title = title_list[0] if title_list else None
        container = msg.get("container-title", [])
        venue = container[0] if container else None
        return {
            "title": title,
            "authors": authors,
            "year": year,
            "venue": venue,
            "volume": msg.get("volume"),
            "issue": msg.get("issue"),
            "pages": msg.get("page"),
            "publisher": msg.get("publisher"),
        }
    except Exception as e:
        log.warning("Crossref failed for %s: %s", doi, e)
        return None


def _arxiv(arxiv_id: str) -> dict | None:
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None else None
        authors = [
            a.find("atom:name", ns).text
            for a in entry.findall("atom:author", ns)
            if a.find("atom:name", ns) is not None
        ]
        published = entry.find("atom:published", ns)
        year = published.text[:4] if published is not None else None
        summary_el = entry.find("atom:summary", ns)
        summary = summary_el.text.strip() if summary_el is not None else None
        return {"title": title, "authors": authors, "year": year, "venue": "arXiv", "summary": summary}
    except Exception as e:
        log.warning("arXiv failed for %s: %s", arxiv_id, e)
        return None


def _local_fallback(extracted: dict) -> dict:
    title = extracted.get("meta_title") or None
    author = extracted.get("meta_author") or None
    authors = [a.strip() for a in author.split(";")] if author else []
    if not title:
        text = extracted.get("text", "")
        first_line = next((l.strip() for l in text.splitlines() if l.strip()), None)
        title = first_line[:120] if first_line else None
    return {"title": title, "authors": authors, "year": None, "venue": None}


def fetch(extracted: dict, cfg: dict) -> dict[str, Any]:
    if not cfg.get("enable_network", True):
        return _local_fallback(extracted)

    mailto = cfg.get("crossref_mailto", "")
    if extracted.get("doi"):
        result = _crossref(extracted["doi"], mailto)
        if result:
            return result
    if extracted.get("arxiv_id"):
        result = _arxiv(extracted["arxiv_id"])
        if result:
            return result
    return _local_fallback(extracted)
