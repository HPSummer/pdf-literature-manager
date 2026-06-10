from __future__ import annotations

import re
from pathlib import Path

DOI_RE = re.compile(r'\b(10\.\d{4,9}/[^\s",><]+)')
ARXIV_RE1 = re.compile(r'arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)', re.IGNORECASE)
ARXIV_RE2 = re.compile(r'(\d{4}\.\d{4,5})(?:v\d+)?\s*\[[\w.\-]+\]')

try:
    import fitz
    _FITZ = True
except ImportError:
    _FITZ = False


def extract(path: Path, cfg: dict | None = None) -> dict:
    cfg = cfg or {}
    info = {
        "page_count": 0,
        "text": "",
        "doi": None,
        "arxiv_id": None,
        "meta_title": None,
        "meta_author": None,
        "ocr_engine": None,
        "ocr_error": None,
        "needs_review": False,
    }
    try:
        if _FITZ:
            doc = fitz.open(str(path))
            info["page_count"] = len(doc)
            meta = doc.metadata or {}
            info["meta_title"] = meta.get("title") or None
            info["meta_author"] = meta.get("author") or None
            pages = min(3, len(doc))
            text = " ".join(doc[i].get_text() for i in range(pages))
            info["text"] = text
            doc.close()
        else:
            info["needs_review"] = True
            return info

        if not info["text"].strip() and cfg.get("enable_ocr", True):
            _apply_ocr_fallback(path, info, cfg)

        if not info["text"].strip():
            info["needs_review"] = True
            return info

        m = DOI_RE.search(info["text"])
        if m:
            info["doi"] = m.group(1).rstrip(".")
        m = ARXIV_RE1.search(info["text"])
        if m:
            info["arxiv_id"] = m.group(1)
        elif not info["arxiv_id"]:
            m = ARXIV_RE2.search(info["text"])
            if m:
                info["arxiv_id"] = m.group(1)
    except Exception as e:
        info["error"] = str(e)
        info["needs_review"] = True
    return info


def _apply_ocr_fallback(path: Path, info: dict, cfg: dict) -> None:
    try:
        from pdf_manager import ocr

        result = ocr.extract_text(
            path,
            max_pages=int(cfg.get("ocr_max_pages") or 2),
            lang=str(cfg.get("ocr_lang") or "chi_sim+eng"),
        )
        info["ocr_engine"] = result.get("engine")
        info["ocr_error"] = result.get("error")
        if result.get("text"):
            info["text"] = result["text"]
            info["needs_review"] = False
    except Exception as exc:
        info["ocr_error"] = str(exc)
