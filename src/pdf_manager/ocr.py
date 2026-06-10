from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_LANG = "chi_sim+eng"


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


def extract_text(path: Path, *, max_pages: int = 2, lang: str = DEFAULT_LANG) -> dict:
    engine = best_engine()
    if not engine:
        return {"text": "", "engine": None, "error": "No OCR engine detected."}
    if engine == "tesseract":
        return _extract_tesseract(path, max_pages=max_pages, lang=lang)
    return {
        "text": "",
        "engine": engine,
        "error": f"{engine} is installed but automatic OCR extraction is not bundled yet; use tesseract for lightweight OCR.",
    }


def _can_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _extract_tesseract(path: Path, *, max_pages: int, lang: str) -> dict:
    try:
        import fitz
    except ImportError:
        return {"text": "", "engine": "tesseract", "error": "PyMuPDF is required for OCR rendering."}
    if not shutil.which("tesseract"):
        return {"text": "", "engine": "tesseract", "error": "tesseract executable not found."}

    chunks: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="pdf_manager_ocr_") as tmp:
            tmp_dir = Path(tmp)
            with fitz.open(str(path)) as doc:
                for idx in range(min(max_pages, len(doc))):
                    pix = doc[idx].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = tmp_dir / f"page_{idx + 1}.png"
                    output_base = tmp_dir / f"page_{idx + 1}"
                    pix.save(str(image))
                    cmd = ["tesseract", str(image), str(output_base), "-l", lang, "--psm", "6"]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                    if result.returncode != 0:
                        return {
                            "text": "\n".join(chunks).strip(),
                            "engine": "tesseract",
                            "error": (result.stderr or result.stdout or "tesseract failed").strip(),
                        }
                    txt = output_base.with_suffix(".txt")
                    if txt.exists():
                        chunks.append(txt.read_text(encoding="utf-8", errors="ignore"))
        return {"text": "\n\n".join(chunks).strip(), "engine": "tesseract", "error": None}
    except Exception as exc:
        return {"text": "\n".join(chunks).strip(), "engine": "tesseract", "error": str(exc)}
