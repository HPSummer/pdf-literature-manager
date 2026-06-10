from __future__ import annotations

import json
from pathlib import Path

from pdf_manager import classifier, extractor, metadata


def run_samples(samples_dir: Path, out_dir: Path, cfg: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for pdf in sorted(samples_dir.glob("*.pdf")):
        row = {"file": pdf.name, "status": "ok"}
        try:
            ext = extractor.extract(pdf, cfg)
            cls = classifier.classify(ext, cfg)
            meta = metadata.fetch(ext, cfg)
            row.update(
                {
                    "type": cls.get("detected_type"),
                    "confidence": cls.get("confidence"),
                    "needs_review": cls.get("needs_review"),
                    "reason": cls.get("classification_reason"),
                    "title": meta.get("title"),
                    "authors": meta.get("authors") or [],
                    "year": meta.get("year"),
                    "venue": meta.get("venue"),
                    "ocr_engine": ext.get("ocr_engine"),
                    "ocr_error": ext.get("ocr_error"),
                }
            )
        except Exception as exc:
            row.update({"status": "failed", "error": str(exc)})
        rows.append(row)
    report = out_dir / "sample_regression_report.md"
    _write_report(report, rows)
    (out_dir / "sample_regression_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _write_report(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Sample Regression Report",
        "",
        "| File | Status | Type | Confidence | Review | OCR | Title | Reason |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {_cell(row.get('file'))} | {_cell(row.get('status'))} | {_cell(row.get('type'))} | "
            f"{row.get('confidence') or ''} | {_cell(row.get('needs_review'))} | "
            f"{_cell(row.get('ocr_engine') or row.get('ocr_error'))} | {_cell(row.get('title'))} | "
            f"{_cell(row.get('reason') or row.get('error'))} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()
