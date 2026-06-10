from __future__ import annotations

import yaml
from pathlib import Path

DEFAULTS = {
    "recursive": False,
    "enable_network": True,
    "output_obsidian_notes": True,
    "output_bibtex": True,
    "output_ieee": True,
    "citation_style": "gbt7714",
    "min_paper_confidence": 0.75,
    "review_confidence_threshold": 0.45,
    "crossref_mailto": "",
    "obsidian_links": ["trajectory_optimization_kb", "02_literature"],
    "obsidian_literature_dir": "02_literature",
    "obsidian_note_template": "",
}


def load_config(path: str | None = None) -> dict:
    cfg = dict(DEFAULTS)
    if path:
        p = Path(path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            cfg.update(user)
    return cfg
