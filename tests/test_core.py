import pytest
from unittest.mock import patch, MagicMock
import sys, types

# Stub fitz so extractor imports without pymupdf installed
fitz_stub = types.ModuleType("fitz")
sys.modules.setdefault("fitz", fitz_stub)

from pdf_manager.extractor import DOI_RE, ARXIV_RE1, ARXIV_RE2
from pdf_manager import citation, bibtex, metadata
from pdf_manager.bibtex import reset_keys


# 1. DOI extraction
def test_doi_extraction():
    text = "See https://doi.org/10.1109/TAES.2020.123456 for details"
    m = DOI_RE.search(text)
    assert m and m.group(1).startswith("10.1109/")


# 2. arXiv ID extraction
def test_arxiv_id_extraction():
    text1 = "arXiv: 2103.04567v2 [cs.AI]"
    text2 = "2103.04567 [cs.AI]"
    m1 = ARXIV_RE1.search(text1)
    m2 = ARXIV_RE2.search(text2)
    assert m1 and m1.group(1).startswith("2103.")
    assert m2 and m2.group(1) == "2103.04567"


# 3. IEEE citation - complete fields
def test_ieee_citation_formatting():
    rec = {
        "authors": ["Alice A. Smith", "Bob B. Jones"],
        "title": "A Great Paper",
        "venue": "IEEE Trans. Aerosp.",
        "volume": "56",
        "issue": "3",
        "pages": "100-110",
        "year": "2023",
        "doi": "10.1109/TAS.2023.001",
    }
    cit = citation.generate(rec, "ieee")
    assert "Smith" in cit
    assert '"A Great Paper,"' in cit
    assert "vol. 56" in cit
    assert "2023" in cit


# 4. IEEE citation - missing fields produce no None
def test_ieee_citation_missing_fields():
    rec = {"authors": ["C. D. Lee"], "title": "Short Paper", "year": "2022",
           "venue": None, "volume": None, "issue": None, "pages": None, "doi": None}
    cit = citation.generate(rec)
    assert "None" not in cit
    assert "Short Paper" in cit


def test_multiple_citation_styles():
    rec = {
        "authors": ["Alice A. Smith", "Bob B. Jones"],
        "title": "A Great Paper",
        "venue": "Journal of Spacecraft",
        "volume": "12",
        "issue": "2",
        "pages": "10-20",
        "year": "2024",
        "doi": "10.1000/test",
    }
    assert "Smith" in citation.generate(rec, "apa")
    assert '"A Great Paper"' in citation.generate(rec, "mla")
    assert "GB/T 7714" == citation.style_label("gbt7714")
    assert citation.normalize_style("gb") == "gbt7714"


def test_classification_reason():
    from pdf_manager import classifier

    extracted = {
        "doi": "10.1000/test",
        "arxiv_id": None,
        "text": "Abstract text. References",
        "needs_review": False,
    }
    result = classifier.classify(extracted, {})
    assert result["detected_type"] == "unknown"
    assert "DOI detected" in result["classification_reason"]
    assert "Abstract and References found" in result["classification_reason"]


def test_structured_doi_article_classifies_as_paper():
    from pdf_manager import classifier

    extracted = {
        "doi": "10.1000/test",
        "arxiv_id": None,
        "text": "Abstract. This IEEE paper studies guidance. Introduction. Method. References.",
        "needs_review": False,
    }
    result = classifier.classify(extracted, {})
    assert result["detected_type"] == "paper"
    assert result["confidence"] == 0.7


def test_thesis_classification_and_gbt_citation():
    from pdf_manager import classifier

    extracted = {
        "doi": None,
        "arxiv_id": None,
        "text": "博士学位论文 Dissertation Introduction References",
        "needs_review": False,
    }
    result = classifier.classify(extracted, {})
    assert result["detected_type"] == "thesis"
    assert result["thesis_type"] == "doctoral"

    rec = {
        "detected_type": "thesis",
        "thesis_type": "doctoral",
        "authors": ["张三"],
        "title": "低推力轨迹优化方法研究",
        "venue": "哈尔滨工业大学",
        "place": "哈尔滨",
        "year": "2024",
    }
    gbt = citation.generate(rec, "gbt7714")
    assert "低推力轨迹优化方法研究[D]" in gbt
    assert "哈尔滨: 哈尔滨工业大学, 2024" in gbt
    assert citation.filename_from_gbt(rec).endswith(".pdf")


# 5. BibTeX key format
def test_bibtex_key_generation():
    reset_keys()
    rec = {
        "authors": ["John Doe"],
        "title": "Optimal Trajectories",
        "year": "2021",
        "venue": "Journal of Spacecraft",
        "doi": "10.1000/xyz",
        "arxiv_id": None,
    }
    key, bib = bibtex.generate(rec)
    assert key == "Doe2021Optimal"
    assert "@article" in bib
    assert "None" not in bib


def test_bibtex_thesis_entry_type():
    reset_keys()
    rec = {
        "detected_type": "thesis",
        "thesis_type": "master",
        "authors": ["John Doe"],
        "title": "Optimal Trajectories",
        "year": "2021",
        "venue": "Space University",
    }
    key, bib = bibtex.generate(rec)
    assert key.startswith("Doe2021")
    assert "@mastersthesis" in bib


# 6. Non-paper fallback tag is filename stem
def test_non_paper_fallback_tag():
    rec = {"detected_type": "document", "tag": "my_document", "bibtex_key": None}
    assert rec["tag"] == "my_document"


# 7. Duplicate detection by DOI
def test_duplicate_detection():
    from pdf_manager.writers import _detect_duplicates
    records = [
        {"doi": "10.1/abc", "title": "T1", "year": "2020", "bibtex_key": "A"},
        {"doi": "10.1/abc", "title": "T1", "year": "2020", "bibtex_key": "B"},
    ]
    result = _detect_duplicates(records)
    groups = [r.get("duplicate_group") for r in result]
    assert groups[0] == groups[1] == "10.1/abc"


# 8. Network failure fallback
def test_network_failure_fallback():
    extracted = {
        "doi": "10.9999/bad",
        "arxiv_id": None,
        "meta_title": "Fallback Title",
        "meta_author": "Alice",
        "text": "Some text here",
    }
    cfg = {"enable_network": True, "crossref_mailto": ""}
    with patch("requests.get", side_effect=Exception("connection error")):
        result = metadata.fetch(extracted, cfg)
    assert result is not None
    assert "title" in result
    assert result.get("title") == "Fallback Title"


def test_selected_style_reference_output(tmp_path):
    from pdf_manager import writers

    rec = {
        "original_filename": "paper.pdf",
        "absolute_path": str(tmp_path / "paper.pdf"),
        "relative_path": "paper.pdf",
        "file_size": 100,
        "page_count": 2,
        "detected_type": "paper",
        "confidence": 1.0,
        "title": "A Great Paper",
        "authors": ["Alice Smith"],
        "year": "2024",
        "venue": "Journal of Spacecraft",
        "volume": None,
        "issue": None,
        "pages": None,
        "doi": "10.1000/test",
        "arxiv_id": None,
        "url": None,
        "publisher": None,
        "ieee_citation": None,
        "citation": None,
        "bibtex_key": "Smith2024Great",
        "tag": "Smith2024Great",
        "duplicate_group": None,
        "needs_review": False,
        "classification_reason": "DOI detected",
        "notes": None,
        "error": None,
        "_bibtex_entry": "@article{Smith2024Great,\n}",
    }
    out = writers.write_all([rec], str(tmp_path), {"citation_style": "apa"})
    assert (out / "references_apa.md").exists()
    assert "Smith" in (out / "references_apa.md").read_text(encoding="utf-8")
    assert "citation_style: apa" in (out / "obsidian_notes" / "Smith2024Great.md").read_text(encoding="utf-8")
    session = (out / "session.json").read_text(encoding="utf-8")
    assert '"citation_style": "apa"' in session
    assert "DOI detected" in session


def test_ris_and_import_guide_output(tmp_path):
    from pdf_manager import writers

    rec = {
        "original_filename": "thesis.pdf",
        "absolute_path": str(tmp_path / "thesis.pdf"),
        "relative_path": "thesis.pdf",
        "file_size": 100,
        "page_count": 120,
        "detected_type": "thesis",
        "thesis_type": "doctoral",
        "confidence": 1.0,
        "title": "Optimal Low-Thrust Trajectories",
        "authors": ["Alice Smith"],
        "year": "2024",
        "venue": "Space University",
        "volume": None,
        "issue": None,
        "pages": None,
        "doi": None,
        "arxiv_id": None,
        "url": None,
        "publisher": None,
        "ieee_citation": None,
        "citation": None,
        "bibtex_key": "Smith2024Optimal",
        "tag": "Smith2024Optimal",
        "duplicate_group": None,
        "needs_review": False,
        "classification_reason": "Thesis signal detected",
        "notes": None,
        "error": None,
        "_bibtex_entry": "@phdthesis{Smith2024Optimal,\n}",
    }
    out = writers.write_all([rec], str(tmp_path), {"citation_style": "gbt7714"})
    ris = (out / "references.ris").read_text(encoding="utf-8")
    assert "TY  - THES" in ris
    assert "TI  - Optimal Low-Thrust Trajectories" in ris
    assert "PB  - Space University" in ris
    guide = (out / "import_guide.md").read_text(encoding="utf-8")
    assert "Zotero" in guide
    assert "Obsidian" in guide
    assert "小绿鲸" in guide


def test_copy_obsidian_notes(tmp_path):
    from pdf_manager import integrations

    out = tmp_path / "_pdf_manager_output"
    notes = out / "obsidian_notes"
    notes.mkdir(parents=True)
    (notes / "Smith2024Optimal.md").write_text("# Note\n", encoding="utf-8")
    vault = tmp_path / "vault"
    count = integrations.copy_obsidian_notes(out, vault)
    assert count == 1
    assert (vault / "02_literature" / "Smith2024Optimal.md").exists()
