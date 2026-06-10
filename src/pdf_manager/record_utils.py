from __future__ import annotations


def can_auto_accept_literature(rec: dict) -> bool:
    if rec.get("error"):
        return False
    if rec.get("detected_type") == "thesis":
        return _has_title(rec) and _has_authors(rec) and bool(rec.get("venue") or rec.get("publisher"))
    scholarly_id = bool(rec.get("doi") or rec.get("arxiv_id"))
    metadata_ready = _has_title(rec) and _has_authors(rec) and bool(rec.get("year"))
    venue_ready = bool(rec.get("venue") or rec.get("publisher"))
    return scholarly_id and metadata_ready and venue_ready


def auto_accept_literature(rec: dict) -> bool:
    if not can_auto_accept_literature(rec):
        return False
    if rec.get("detected_type") == "unknown":
        rec["detected_type"] = "paper"
    if rec.get("detected_type") not in {"paper", "thesis"}:
        return False
    rec["needs_review"] = False
    reason = rec.get("classification_reason") or ""
    marker = "metadata complete; auto accepted for rename/export"
    if marker not in reason:
        rec["classification_reason"] = f"{reason}; {marker}" if reason else marker
    rec["confidence"] = max(float(rec.get("confidence") or 0), 0.82)
    return True


def require_metadata_for_literature(rec: dict) -> bool:
    if rec.get("detected_type") not in {"paper", "thesis"} or rec.get("error"):
        return False
    missing = []
    if not _has_title(rec):
        missing.append("title")
    if not _has_authors(rec):
        missing.append("authors")
    if rec.get("detected_type") == "thesis" and not (rec.get("venue") or rec.get("publisher")):
        missing.append("school")
    if rec.get("detected_type") == "paper" and not (rec.get("doi") or rec.get("arxiv_id") or rec.get("venue")):
        missing.append("identifier/venue")
    if not missing:
        return False
    rec["needs_review"] = True
    reason = rec.get("classification_reason") or ""
    marker = f"missing metadata ({', '.join(missing)}); review before rename/export"
    if marker not in reason:
        rec["classification_reason"] = f"{reason}; {marker}" if reason else marker
    return True


def ready_for_automatic_rename(rec: dict) -> bool:
    return rec.get("detected_type") in {"paper", "thesis"} and not rec.get("needs_review") and not rec.get("error")


def _has_title(rec: dict) -> bool:
    return bool(str(rec.get("title") or "").strip())


def _has_authors(rec: dict) -> bool:
    authors = rec.get("authors")
    if isinstance(authors, list):
        return any(str(a).strip() for a in authors)
    return bool(str(authors or "").strip())
