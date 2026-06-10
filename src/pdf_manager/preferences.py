from __future__ import annotations

import json
import os
from pathlib import Path


SAFE_KEYS = {
    "ai_base_url",
    "ai_model",
    "ai_env_name",
    "citation_style",
    "enable_network",
    "obsidian_literature_dir",
    "obsidian_note_template",
    "output_obsidian_notes",
    "recursive",
}


def preferences_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "PDFLiteratureManager" / "preferences.json"


def load_preferences(path: Path | None = None) -> dict:
    target = path or preferences_path()
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: v for k, v in data.items() if k in SAFE_KEYS}


def save_preferences(values: dict, path: Path | None = None) -> Path:
    target = path or preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in values.items() if k in SAFE_KEYS}
    target.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
