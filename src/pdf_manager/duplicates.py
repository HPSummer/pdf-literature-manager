from __future__ import annotations

import re
from collections import defaultdict


def normalize_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (title or "").lower())


def duplicate_key(rec: dict) -> str:
    doi = (rec.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = normalize_title(rec.get("title"))
    year = rec.get("year") or ""
    if title:
        return f"title:{title[:80]}:{year}"
    return ""


def build_groups(records: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        key = duplicate_key(rec)
        if key:
            buckets[key].append(rec)

    groups = []
    for key, items in buckets.items():
        if len(items) > 1:
            groups.append({"key": key, "records": items})
    return groups


def mark_duplicates(records: list[dict]) -> list[dict]:
    for group in build_groups(records):
        keep = choose_primary(group["records"])
        group_id = group["key"]
        for rec in group["records"]:
            rec["duplicate_group"] = group_id
            if rec is not keep:
                rec["merged_into"] = keep.get("bibtex_key") or keep.get("original_filename")
                rec["needs_review"] = True
    return records


def choose_primary(records: list[dict]) -> dict:
    def score(rec: dict) -> tuple:
        return (
            1 if rec.get("doi") else 0,
            1 if rec.get("bibtex_key") else 0,
            1 if rec.get("year") else 0,
            len(rec.get("authors") or []),
            len(rec.get("title") or ""),
        )

    return max(records, key=score)
