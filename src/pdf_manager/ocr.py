from __future__ import annotations

import shutil


def availability() -> dict:
    return {
        "tesseract": bool(shutil.which("tesseract")),
        "paddleocr": _can_import("paddleocr"),
        "easyocr": _can_import("easyocr"),
    }


def best_engine() -> str | None:
    info = availability()
    for name in ("paddleocr", "easyocr", "tesseract"):
        if info.get(name):
            return name
    return None


def status_text() -> str:
    engine = best_engine()
    if engine:
        return f"OCR 可用：{engine}"
    return "OCR 未启用：未检测到 tesseract / paddleocr / easyocr"


def _can_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False
