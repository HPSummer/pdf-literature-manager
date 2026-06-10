from __future__ import annotations

import json
from pathlib import Path

import requests

from pdf_manager import integrations


DEFAULT_BASE_URL = "http://127.0.0.1:23119/api"


def is_available(base_url: str = DEFAULT_BASE_URL, timeout: float = 1.5) -> bool:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/users/0/items/top", timeout=timeout)
        return response.status_code in {200, 300, 400, 403, 404}
    except Exception:
        return False


def import_report_placeholder(out_dir: Path, records: list[dict], base_url: str = DEFAULT_BASE_URL) -> Path:
    path = out_dir / "zotero_local_api_plan.json"
    payload = {
        "base_url": base_url,
        "status": "available" if is_available(base_url) else "unavailable",
        "items": [_plan_item(rec) for rec in integrations.citable_records(records)],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_records(out_dir: Path, records: list[dict], base_url: str = DEFAULT_BASE_URL, timeout: float = 8.0) -> Path:
    path = out_dir / "zotero_local_api_report.json"
    citable = integrations.citable_records(records)
    payload = {
        "base_url": base_url,
        "status": "unavailable",
        "total": len(records),
        "attempted": len(citable),
        "created": 0,
        "failed": 0,
        "items": [_plan_item(rec) for rec in citable],
        "errors": [],
    }
    if not is_available(base_url):
        payload["errors"].append("Zotero local API is not available. Start Zotero and enable the local API.")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    endpoint = f"{base_url.rstrip('/')}/users/0/items"
    headers = {"Zotero-API-Version": "3", "Content-Type": "application/json"}
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=[to_zotero_item(rec) for rec in citable],
            timeout=timeout,
        )
        payload["status_code"] = response.status_code
        if response.status_code in {200, 201}:
            data = response.json() if response.content else {}
            successful = data.get("successful") if isinstance(data, dict) else None
            payload["status"] = "imported"
            payload["created"] = len(successful) if isinstance(successful, dict) else len(citable)
            payload["failed"] = max(0, len(citable) - payload["created"])
            if isinstance(successful, dict):
                for idx, item in successful.items():
                    try:
                        citable[int(idx)]["zotero_key"] = item.get("key")
                    except Exception:
                        pass
        else:
            payload["status"] = "failed"
            payload["failed"] = len(citable)
            payload["errors"].append(response.text[:1000])
    except Exception as exc:
        payload["status"] = "failed"
        payload["failed"] = len(citable)
        payload["errors"].append(str(exc))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def to_zotero_item(rec: dict) -> dict:
    item_type = _item_type(rec)
    item = {
        "itemType": item_type,
        "title": rec.get("title") or rec.get("tag") or rec.get("original_filename") or "Untitled",
        "creators": [_creator(author) for author in rec.get("authors") or [] if str(author).strip()],
        "date": str(rec.get("year") or ""),
        "url": rec.get("url") or (_arxiv_url(rec) if rec.get("arxiv_id") else ""),
        "DOI": rec.get("doi") or "",
        "abstractNote": rec.get("notes") or "",
        "extra": _extra(rec),
    }
    if item_type == "thesis":
        item["thesisType"] = _thesis_type_label(rec.get("thesis_type"))
        item["university"] = rec.get("venue") or rec.get("publisher") or ""
        item["place"] = rec.get("place") or ""
    elif item_type == "conferencePaper":
        item["proceedingsTitle"] = rec.get("venue") or ""
        item["conferenceName"] = rec.get("venue") or ""
    else:
        item["publicationTitle"] = rec.get("venue") or ""
        item["volume"] = rec.get("volume") or ""
        item["issue"] = rec.get("issue") or ""
        item["pages"] = rec.get("pages") or ""
    return {k: v for k, v in item.items() if v not in ("", [], None)}


def _plan_item(rec: dict) -> dict:
    return {
        "title": rec.get("title"),
        "type": rec.get("detected_type"),
        "doi": rec.get("doi"),
        "year": rec.get("year"),
        "authors": rec.get("authors") or [],
    }


def _item_type(rec: dict) -> str:
    if rec.get("detected_type") == "thesis":
        return "thesis"
    venue = (rec.get("venue") or "").lower()
    if any(word in venue for word in ("conference", "proceedings", "symposium", "workshop")):
        return "conferencePaper"
    return "journalArticle"


def _creator(author: str) -> dict:
    return {"creatorType": "author", "name": str(author).strip()}


def _arxiv_url(rec: dict) -> str:
    return f"https://arxiv.org/abs/{rec['arxiv_id']}"


def _extra(rec: dict) -> str:
    lines = []
    if rec.get("bibtex_key"):
        lines.append(f"Citation Key: {rec['bibtex_key']}")
    if rec.get("arxiv_id"):
        lines.append(f"arXiv: {rec['arxiv_id']}")
    if rec.get("advisor"):
        lines.append(f"Advisor: {rec['advisor']}")
    if rec.get("citation"):
        lines.append(f"GB/T 7714: {rec['citation']}")
    if rec.get("ieee_citation"):
        lines.append(f"IEEE: {rec['ieee_citation']}")
    return "\n".join(lines)


def _thesis_type_label(value) -> str:
    return {"master": "Master's thesis", "doctoral": "PhD thesis"}.get(str(value or "").lower(), "Thesis")
