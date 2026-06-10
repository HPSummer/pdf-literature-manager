from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

log = logging.getLogger(__name__)

SCHOOL_RE = re.compile(r"([\u4e00-\u9fff]{2,30}(?:大学|学院|研究院|研究所))")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b|((?:19|20)\d{2})\s*年")
AUTHOR_RE = re.compile(r"(?:作者|研究生|学生姓名|姓名)\s*[:：]\s*([\u4e00-\u9fffA-Za-z .;；、,，-]{2,80})")
SUPERVISOR_RE = re.compile(r"(?:导师|指导教师)\s*[:：]\s*([\u4e00-\u9fffA-Za-z .;；、,，-]{2,80})")

CITY_HINTS = {
    "哈尔滨工业大学": "哈尔滨",
    "北京大学": "北京",
    "清华大学": "北京",
    "北京航空航天大学": "北京",
    "南京航空航天大学": "南京",
    "西北工业大学": "西安",
    "上海交通大学": "上海",
    "浙江大学": "杭州",
    "中国科学院": "北京",
}


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
    text = extracted.get("text", "")
    authors = _split_authors(author) if author else _infer_authors(text)
    if not title:
        title = _infer_title(text)
    school = _infer_school(text)
    return {
        "title": title,
        "authors": authors,
        "year": _infer_year(text),
        "venue": school,
        "place": _infer_place(text, school),
        "advisor": _infer_advisor(text),
    }


def _merge_metadata(primary: dict | None, fallback: dict) -> dict:
    result = dict(primary or {})
    for key, value in fallback.items():
        if value and not result.get(key):
            result[key] = value
    return result


def _split_authors(text: str | None) -> list[str]:
    if not text:
        return []
    return [a.strip() for a in re.split(r";|；|、|,|，|\n", text) if a.strip()]


def _infer_authors(text: str) -> list[str]:
    match = AUTHOR_RE.search(text or "")
    return _split_authors(match.group(1)) if match else []


def _infer_advisor(text: str) -> str | None:
    match = SUPERVISOR_RE.search(text or "")
    return match.group(1).strip() if match else None


def _infer_title(text: str) -> str | None:
    skip = {
        "abstract", "摘要", "关键词", "key words", "references", "参考文献",
        "introduction", "目录", "致谢", "作者", "导师",
    }
    for raw in (text or "").splitlines():
        line = raw.strip(" \t\r\n-—")
        if not line:
            continue
        lower = line.lower()
        if any(k in lower or k in line for k in skip):
            continue
        if 4 <= len(line) <= 120:
            return line
    return None


def _infer_year(text: str) -> str | None:
    match = YEAR_RE.search(text or "")
    if not match:
        return None
    return match.group(0).replace("年", "").strip()


def _infer_school(text: str) -> str | None:
    match = SCHOOL_RE.search(text or "")
    return match.group(1).strip() if match else None


def _infer_place(text: str, school: str | None = None) -> str | None:
    if school and school in CITY_HINTS:
        return CITY_HINTS[school]
    match = re.search(r"(?:地点|授予地点|培养单位所在地)\s*[:：]\s*([\u4e00-\u9fff]{2,12})", text or "")
    return match.group(1).strip() if match else None


def fetch(extracted: dict, cfg: dict) -> dict[str, Any]:
    fallback = _local_fallback(extracted)
    if not cfg.get("enable_network", True):
        return fallback

    mailto = cfg.get("crossref_mailto", "")
    if extracted.get("doi"):
        result = _crossref(extracted["doi"], mailto)
        if result:
            return _merge_metadata(result, fallback)
    if extracted.get("arxiv_id"):
        result = _arxiv(extracted["arxiv_id"])
        if result:
            return _merge_metadata(result, fallback)
    return fallback
