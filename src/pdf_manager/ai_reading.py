from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import requests


DEFAULT_MODEL = "gpt-5.4"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def extract_text(path: Path, mode: str) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to read PDF text.") from exc

    max_pages = 8 if mode == "rough" else 24
    max_chars = 18000 if mode == "rough" else 52000
    chunks: list[str] = []
    with fitz.open(str(path)) as doc:
        for i in range(min(max_pages, len(doc))):
            chunks.append(doc[i].get_text())
            if sum(len(c) for c in chunks) >= max_chars:
                break
    text = "\n\n".join(chunks).strip()
    return text[:max_chars]


def build_prompt(rec: dict, text: str, mode: str, preference: str = "") -> str:
    title = rec.get("title") or rec.get("original_filename") or "Untitled"
    authors = "; ".join(rec.get("authors") or [])
    year = rec.get("year") or ""
    venue = rec.get("venue") or ""
    doi = rec.get("doi") or rec.get("arxiv_id") or ""
    preference = preference.strip() or "优先关注研究问题、方法、结论、局限，以及是否值得精读。"
    if mode == "deep":
        task = (
            "请做精读笔记，面向科研选题和文献管理。输出包含：\n"
            "1. 一句话结论\n2. 研究问题\n3. 方法框架\n4. 关键假设与公式/算法线索\n"
            "5. 实验/验证方式\n6. 主要贡献\n7. 局限与风险\n8. 与用户偏好的关系\n"
            "9. 可放入 Obsidian 的双链关键词\n10. 是否值得继续精读/引用"
        )
    else:
        task = (
            "请做粗读筛选笔记，帮助用户快速判断是否值得精读。输出包含：\n"
            "1. 30字以内一句话概括\n2. 研究主题\n3. 方法关键词\n4. 可能价值\n"
            "5. 不确定或需复核处\n6. 精读优先级：高/中/低，并给出理由"
        )
    return f"""你是严谨的科研文献阅读助手。请只依据给定 PDF 文本，不要编造不存在的信息。

用户偏好：
{preference}

文献信息：
- Title: {title}
- Authors: {authors}
- Year: {year}
- Venue/School: {venue}
- DOI/arXiv: {doi}

任务：
{task}

PDF 文本节选：
---
{text}
---"""


def call_openai_compatible(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    timeout: int = 90,
) -> str:
    if not api_key:
        raise ValueError("API key is missing.")
    endpoint = _chat_endpoint(base_url)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是可靠、简洁、面向科研工作的中文文献阅读助手。"},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected AI response format.") from exc


def generate_reading(
    *,
    rec: dict,
    pdf_path: Path,
    out_dir: Path,
    mode: str,
    model: str,
    base_url: str,
    api_key: str,
    preference: str = "",
) -> Path:
    text = extract_text(pdf_path, mode)
    if not text:
        raise RuntimeError("No extractable text found in this PDF.")
    prompt = build_prompt(rec, text, mode, preference)
    content = call_openai_compatible(
        api_key=api_key,
        base_url=base_url,
        model=model,
        prompt=prompt,
    )
    return write_note(out_dir, rec, mode, model, base_url, content)


def write_note(out_dir: Path, rec: dict, mode: str, model: str, base_url: str, content: str) -> Path:
    notes_dir = out_dir / "ai_reading_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    key = rec.get("bibtex_key") or rec.get("tag") or Path(rec.get("original_filename", "paper")).stem
    path = notes_dir / f"{_safe_name(str(key))}_{mode}.md"
    title = rec.get("title") or rec.get("original_filename") or "Untitled"
    label = "精读" if mode == "deep" else "粗读"
    markdown = [
        "---",
        f"title: {_yaml_scalar(title)}",
        f"source_file: {_yaml_scalar(rec.get('original_filename') or '')}",
        f"mode: {_yaml_scalar(mode)}",
        f"model: {_yaml_scalar(model)}",
        f"base_url: {_yaml_scalar(_redact_base_url(base_url))}",
        f"created_at: {_yaml_scalar(datetime.now().isoformat(timespec='seconds'))}",
        "---",
        "",
        f"# AI {label}: {title}",
        "",
        content.strip(),
        "",
    ]
    path.write_text("\n".join(markdown), encoding="utf-8")
    return path


def write_batch_rough_report(out_dir: Path, rows: list[dict], model: str, base_url: str) -> Path:
    notes_dir = out_dir / "ai_reading_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / "batch_rough_reading.md"
    lines = [
        "---",
        f"model: {_yaml_scalar(model)}",
        f"base_url: {_yaml_scalar(_redact_base_url(base_url))}",
        f"created_at: {_yaml_scalar(datetime.now().isoformat(timespec='seconds'))}",
        "---",
        "",
        "# AI 批量粗读排序",
        "",
        "| Priority | Title | File | Note |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {_md_cell(row.get('priority') or '')} | "
            f"{_md_cell(row.get('title') or '')} | "
            f"{_md_cell(row.get('file') or '')} | "
            f"{_md_cell(row.get('note') or '')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generate_batch_readings(
    *,
    records: list[dict],
    out_dir: Path,
    mode: str,
    model: str,
    base_url: str,
    api_key: str,
    preference: str = "",
    limit: int = 8,
) -> list[dict]:
    rows: list[dict] = []
    for rec in records[: max(0, limit)]:
        if rec.get("detected_type") not in {"paper", "thesis"} or rec.get("needs_review"):
            rows.append(_batch_result(rec, "skipped", "", "not ready for AI reading"))
            continue
        pdf_path = Path(rec.get("absolute_path") or "")
        if not pdf_path.exists():
            rows.append(_batch_result(rec, "failed", "", "PDF path not found"))
            continue
        try:
            note = generate_reading(
                rec=rec,
                pdf_path=pdf_path,
                out_dir=out_dir,
                mode=mode,
                model=model,
                base_url=base_url,
                api_key=api_key,
                preference=preference,
            )
            rows.append(_batch_result(rec, "generated", str(note), ""))
        except Exception as exc:
            rows.append(_batch_result(rec, "failed", "", str(exc)))
    write_batch_ai_summary(out_dir, rows, mode, model, base_url)
    return rows


def write_batch_ai_summary(out_dir: Path, rows: list[dict], mode: str, model: str, base_url: str) -> Path:
    notes_dir = out_dir / "ai_reading_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / f"batch_ai_{mode}_summary.md"
    lines = [
        "---",
        f"mode: {_yaml_scalar(mode)}",
        f"model: {_yaml_scalar(model)}",
        f"base_url: {_yaml_scalar(_redact_base_url(base_url))}",
        f"created_at: {_yaml_scalar(datetime.now().isoformat(timespec='seconds'))}",
        "---",
        "",
        f"# 批量 AI {('精读' if mode == 'deep' else '粗读')}结果",
        "",
        "| Status | File | Note | Error |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {_md_cell(row.get('status'))} | {_md_cell(row.get('file'))} | "
            f"{_md_cell(row.get('note_path'))} | {_md_cell(row.get('error'))} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def heuristic_batch_rows(records: list[dict]) -> list[dict]:
    rows = []
    for rec in records:
        if rec.get("detected_type") not in {"paper", "thesis"} or rec.get("needs_review"):
            continue
        text = " ".join(
            str(rec.get(k) or "")
            for k in ("title", "venue", "notes", "classification_reason")
        ).lower()
        high_terms = ("control", "trajectory", "optimization", "drag-free", "adrc", "rtbp", "低推力", "轨迹", "控制")
        score = sum(1 for term in high_terms if term in text)
        priority = "高" if score >= 2 else "中" if score == 1 else "低"
        rows.append({
            "priority": priority,
            "title": rec.get("title") or rec.get("tag") or rec.get("original_filename"),
            "file": rec.get("original_filename"),
            "note": "启发式排序；可用 AI 阅读生成更细笔记。",
        })
    order = {"高": 0, "中": 1, "低": 2}
    return sorted(rows, key=lambda r: order.get(r["priority"], 9))


def _batch_result(rec: dict, status: str, note_path: str, error: str) -> dict:
    return {
        "status": status,
        "file": rec.get("original_filename") or "",
        "title": rec.get("title") or rec.get("tag") or "",
        "note_path": note_path,
        "error": error,
    }


def resolve_api_key(env_name: str, temporary_key: str = "") -> str:
    return temporary_key.strip() or os.environ.get(env_name.strip() or "OPENAI_API_KEY", "").strip()


def _chat_endpoint(base_url: str) -> str:
    url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


def _safe_name(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:90] or "ai_reading"


def _yaml_scalar(value) -> str:
    text = str(value or "")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _md_cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _redact_base_url(base_url: str) -> str:
    return (base_url or DEFAULT_BASE_URL).strip()
