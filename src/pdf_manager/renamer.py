from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


LOG_NAME = "rename_log.jsonl"


def log_path(out_dir: Path) -> Path:
    return out_dir / LOG_NAME


def append_log(out_dir: Path, old_path: Path, new_path: Path, status: str = "renamed") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "old_path": str(old_path),
        "new_path": str(new_path),
        "status": status,
    }
    with open(log_path(out_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log(out_dir: Path) -> list[dict]:
    path = log_path(out_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def undo_last_batch(out_dir: Path) -> list[dict]:
    rows = [r for r in read_log(out_dir) if r.get("status") == "renamed"]
    results = []
    for row in reversed(rows):
        old_path = Path(row["old_path"])
        new_path = Path(row["new_path"])
        result = dict(row)
        if not new_path.exists():
            result["undo_status"] = "missing_new_path"
        elif old_path.exists():
            result["undo_status"] = "old_path_exists"
        else:
            new_path.rename(old_path)
            result["undo_status"] = "undone"
            append_log(out_dir, new_path, old_path, "undone")
        results.append(result)
    return results


def write_markdown_log(out_dir: Path) -> Path:
    rows = read_log(out_dir)
    md = out_dir / "rename_log.md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("# Rename Log\n\n")
        f.write("| Time | Status | Old | New |\n|---|---|---|---|\n")
        for row in rows:
            f.write(
                f"| {row.get('time','')} | {row.get('status','')} | "
                f"{row.get('old_path','')} | {row.get('new_path','')} |\n"
            )
    return md
