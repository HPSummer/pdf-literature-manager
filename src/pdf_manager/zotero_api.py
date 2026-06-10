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


def import_records(
    out_dir: Path,
    records: list[dict],
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 8.0,
    *,
    collection_key: str = "",
    attach_pdf: bool = True,
    dedupe: bool = True,
) -> Path:
    path = out_dir / "zotero_local_api_report.json"
    citable = integrations.citable_records(records)
    payload = {
        "base_url": base_url,
        "status": "unavailable",
        "total": len(records),
        "attempted": len(citable),
        "created": 0,
        "existing": 0,
        "attached": 0,
        "failed": 0,
        "items": [_plan_item(rec) for rec in citable],
        "errors": [],
    }
    if not is_available(base_url):
        payload["errors"].append("Zotero local API is not available. Start Zotero and enable the local API.")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    root = base_url.rstrip("/")
    endpoint = f"{root}/users/0/items"
    headers = {"Zotero-API-Version": "3", "Content-Type": "application/json"}
    try:
        to_create: list[tuple[int, dict]] = []
        for idx, rec in enumerate(citable):
            existing = find_existing(rec, root, timeout=timeout) if dedupe else None
            if existing:
                rec["zotero_key"] = existing.get("key")
                payload["existing"] += 1
                if attach_pdf and _attach_pdf(root, rec, existing.get("key"), timeout):
                    payload["attached"] += 1
                continue
            item = to_zotero_item(rec)
            if collection_key:
                item["collections"] = [collection_key]
            to_create.append((idx, item))

        if to_create:
            response = requests.post(
                endpoint,
                headers=headers,
                json=[item for _idx, item in to_create],
                timeout=timeout,
            )
            payload["status_code"] = response.status_code
            if response.status_code in {200, 201}:
                data = response.json() if response.content else {}
                successful = data.get("successful") if isinstance(data, dict) else None
                payload["status"] = "imported"
                payload["created"] = len(successful) if isinstance(successful, dict) else len(to_create)
                payload["failed"] = max(0, len(to_create) - payload["created"])
                if isinstance(successful, dict):
                    for pos, item in successful.items():
                        try:
                            rec_idx = to_create[int(pos)][0]
                            key = item.get("key")
                            citable[rec_idx]["zotero_key"] = key
                            if attach_pdf and _attach_pdf(root, citable[rec_idx], key, timeout):
                                payload["attached"] += 1
                        except Exception as exc:
                            payload["errors"].append(f"attachment failed: {exc}")
            else:
                payload["status"] = "failed"
                payload["failed"] = len(to_create)
                payload["errors"].append(response.text[:1000])
        else:
            payload["status"] = "deduped"
    except Exception as exc:
        payload["status"] = "failed"
        payload["failed"] = len(citable)
        payload["errors"].append(str(exc))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def find_existing(rec: dict, base_url: str = DEFAULT_BASE_URL, timeout: float = 4.0) -> dict | None:
    root = base_url.rstrip("/")
    query = (rec.get("doi") or rec.get("title") or "").strip()
    if not query:
        return None
    try:
        response = requests.get(
            f"{root}/users/0/items/top",
            params={"q": query, "limit": 10},
            headers={"Zotero-API-Version": "3"},
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        for item in response.json():
            data = item.get("data", {}) if isinstance(item, dict) else {}
            if _same_record(rec, data):
                return {"key": item.get("key") or data.get("key"), "data": data}
    except Exception:
        return None
    return None


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


def _same_record(rec: dict, data: dict) -> bool:
    doi = (rec.get("doi") or "").strip().lower()
    if doi and doi == (data.get("DOI") or data.get("doi") or "").strip().lower():
        return True
    return _norm(rec.get("title")) and _norm(rec.get("title")) == _norm(data.get("title"))


def _norm(text) -> str:
    import re

    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(text or "").lower())


def _attach_pdf(base_url: str, rec: dict, parent_key: str | None, timeout: float) -> bool:
    if not parent_key:
        return False
    path = Path(rec.get("absolute_path") or "")
    if not path.exists():
        return False
    item = {
        "itemType": "attachment",
        "parentItem": parent_key,
        "linkMode": "linked_file",
        "title": path.name,
        "path": str(path),
        "contentType": "application/pdf",
    }
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/users/0/items",
            headers={"Zotero-API-Version": "3", "Content-Type": "application/json"},
            json=[item],
            timeout=timeout,
        )
        return response.status_code in {200, 201}
    except Exception:
        return False
