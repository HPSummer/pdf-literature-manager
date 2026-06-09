import sys
import logging
from pathlib import Path

from pdf_manager.cli import parse_args
from pdf_manager.config import load_config
from pdf_manager import scanner, extractor, classifier, metadata, citation, bibtex, writers


def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent)
    return str(Path(sys.argv[0]).parent)


def main():
    if len(sys.argv) == 1:
        from pdf_manager.gui import main as gui_main
        gui_main()
        return

    args = parse_args()
    double_click = False

    cfg = load_config(args.config)
    if args.no_network:
        cfg["enable_network"] = False
    if args.recursive:
        cfg["recursive"] = True
    if args.style:
        cfg["citation_style"] = args.style

    scan_dir = args.path or _exe_dir()

    logging.basicConfig(level=logging.WARNING)

    files = scanner.scan(scan_dir, cfg.get("recursive", False))
    records: list[dict] = []

    n_papers = n_docs = n_review = n_failed = 0

    for f in files:
        path: Path = f["path"]
        rec: dict = {
            "original_filename": path.name,
            "absolute_path": str(path.resolve()),
            "relative_path": str(path.relative_to(scan_dir) if path.is_relative_to(scan_dir) else path),
            "file_size": f["file_size"],
            "page_count": 0,
            "detected_type": "document",
            "confidence": 0.0,
            "title": None,
            "authors": [],
            "year": None,
            "venue": None,
            "volume": None,
            "issue": None,
            "pages": None,
            "doi": None,
            "arxiv_id": None,
            "url": None,
            "publisher": None,
            "ieee_citation": None,
            "bibtex_key": None,
            "tag": path.stem,
            "duplicate_group": None,
            "needs_review": False,
            "classification_reason": None,
            "thesis_type": None,
            "notes": None,
            "error": None,
            "_bibtex_entry": None,
        }
        try:
            ext = extractor.extract(path)
            rec.update({k: ext[k] for k in ext if k in rec or k in ("text", "meta_title", "meta_author")})
            rec["page_count"] = ext.get("page_count", 0)
            rec["doi"] = ext.get("doi")
            rec["arxiv_id"] = ext.get("arxiv_id")
            rec["needs_review"] = ext.get("needs_review", False)

            cls = classifier.classify(ext, cfg)
            rec["detected_type"] = cls["detected_type"]
            rec["confidence"] = cls["confidence"]
            rec["needs_review"] = cls["needs_review"]
            rec["classification_reason"] = cls.get("classification_reason")
            rec["thesis_type"] = cls.get("thesis_type")

            meta = metadata.fetch(ext, cfg)
            for k in ("title", "authors", "year", "venue", "volume", "issue", "pages", "publisher"):
                if meta.get(k):
                    rec[k] = meta[k]
            if meta.get("summary"):
                rec["notes"] = meta["summary"]

            if rec["detected_type"] in {"paper", "thesis"}:
                rec["ieee_citation"] = citation.generate(rec, "ieee")
                rec["citation"] = citation.generate(rec, cfg.get("citation_style", "gbt7714"))
                key, bib_entry = bibtex.generate(rec)
                rec["bibtex_key"] = key
                rec["_bibtex_entry"] = bib_entry
                rec["tag"] = key
                n_papers += 1
            else:
                n_docs += 1

            if rec["needs_review"]:
                n_review += 1

        except Exception as e:
            rec["error"] = str(e)
            n_failed += 1

        records.append(rec)

    out_dir = writers.write_all(records, scan_dir, cfg)

    if args.rename_plan:
        _write_rename_plan(records, out_dir)

    print(f"\nPDF Manager Summary")
    print(f"  Scanned:      {len(files)}")
    print(f"  Papers:       {n_papers}")
    print(f"  Documents:    {n_docs}")
    print(f"  Need review:  {n_review}")
    print(f"  Failed:       {n_failed}")
    print(f"  Output:       {out_dir}")

    if double_click:
        input("\nPress Enter to exit...")


def _write_rename_plan(records: list[dict], out_dir: Path):
    with open(out_dir / "rename_plan.md", "w", encoding="utf-8") as f:
        f.write("# Rename Plan\n\n")
        f.write("| Original | Suggested |\n|---|---|\n")
        for rec in records:
            orig = rec.get("original_filename", "")
            key = rec.get("bibtex_key")
            if key:
                suffix = Path(orig).suffix
                f.write(f"| {orig} | {key}{suffix} |\n")


if __name__ == "__main__":
    main()
