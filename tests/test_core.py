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


def test_complete_doi_metadata_auto_accepts_unknown_paper():
    from pdf_manager import record_utils

    rec = {
        "detected_type": "unknown",
        "confidence": 0.5,
        "needs_review": True,
        "classification_reason": "DOI detected; Introduction section found; Publisher keyword found",
        "doi": "10.1109/TAES.2025.3575552",
        "title": "Adaptive Control for Test Mass Capture and Drag-Free Mode",
        "authors": ["Yankai Wang", "Yingjie Chen"],
        "year": "2025",
        "venue": "IEEE Transactions on Aerospace and Electronic Systems",
    }
    assert record_utils.auto_accept_literature(rec) is True
    assert rec["detected_type"] == "paper"
    assert rec["needs_review"] is False
    assert rec["confidence"] >= 0.82
    assert "auto accepted" in rec["classification_reason"]


def test_incomplete_literature_metadata_requires_review_before_rename():
    from pdf_manager import record_utils

    rec = {
        "detected_type": "thesis",
        "confidence": 0.82,
        "needs_review": False,
        "classification_reason": "Thesis/dissertation signal found",
        "title": "",
        "authors": [],
        "year": "2024",
        "venue": "",
    }
    assert record_utils.require_metadata_for_literature(rec) is True
    assert rec["needs_review"] is True
    assert record_utils.ready_for_automatic_rename(rec) is False
    assert "missing metadata" in rec["classification_reason"]


def test_thesis_auto_accept_requires_school():
    from pdf_manager import record_utils

    rec = {
        "detected_type": "thesis",
        "title": "Low-Thrust Trajectory Optimization",
        "authors": ["Alice Smith"],
        "year": "2026",
        "venue": "",
        "publisher": None,
        "needs_review": False,
        "classification_reason": "Thesis/dissertation signal found",
    }
    assert record_utils.auto_accept_literature(rec) is False
    assert record_utils.require_metadata_for_literature(rec) is True
    assert rec["needs_review"] is True


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
    assert len(citation.filename_from_gbt(rec)) <= 114


def test_gbt_filename_is_windows_path_friendly():
    from pdf_manager import citation

    rec = {
        "detected_type": "paper",
        "authors": ["Yankai Wang", "Yingjie Chen", "Ti Chen", "Zhengtao Wei"],
        "title": "Adaptive Control for Test Mass Capture and Drag-Free Mode in Drag-Free Satellite",
        "venue": "IEEE Transactions on Aerospace and Electronic Systems",
        "year": "2025",
        "doi": "10.1109/TAES.2025.3575552",
    }
    name = citation.filename_from_gbt(rec)
    assert name.endswith(".pdf")
    assert len(name) <= 114
    assert not any(ch in name for ch in '<>:"/\\|?*')


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


def test_bibtex_chinese_key_is_stable_and_useful():
    reset_keys()
    rec = {
        "detected_type": "thesis",
        "thesis_type": "doctoral",
        "authors": ["张三"],
        "title": "低推力轨迹优化方法研究",
        "year": "2024",
        "venue": "哈尔滨工业大学",
        "place": "哈尔滨",
        "advisor": "李四",
    }
    key, bib = bibtex.generate(rec)
    assert key.startswith("ref2024_")
    assert "@phdthesis" in bib
    assert "address = {哈尔滨}" in bib
    assert "advisor = {李四}" in bib


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
    assert groups[0] == groups[1] == "doi:10.1/abc"


def test_duplicate_merge_marks_primary():
    from pdf_manager import duplicates

    records = [
        {"doi": "10.1/abc", "title": "T1", "year": "2020", "bibtex_key": "A"},
        {"doi": "10.1/abc", "title": "T1", "year": "", "bibtex_key": ""},
    ]
    duplicates.mark_duplicates(records)
    assert records[0]["duplicate_group"] == "doi:10.1/abc"
    assert records[1]["merged_into"] == "A"
    assert records[1]["needs_review"] is True
    assert "duplicate candidate" in records[1]["classification_reason"]


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


def test_ai_reading_openai_compatible_call_and_note_do_not_store_key(tmp_path):
    from pdf_manager import ai_reading

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "## 粗读\n值得精读。"}}]}

    with patch("requests.post", return_value=FakeResponse()) as post:
        content = ai_reading.call_openai_compatible(
            api_key="secret-test-key",
            base_url="https://example.test/v1",
            model="gpt-5.4",
            prompt="Read this paper",
        )
    assert "值得精读" in content
    args, kwargs = post.call_args
    assert args[0] == "https://example.test/v1/chat/completions"
    assert kwargs["json"]["model"] == "gpt-5.4"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-test-key"

    rec = {"bibtex_key": "Smith2026", "title": "A Paper", "original_filename": "paper.pdf"}
    note = ai_reading.write_note(tmp_path, rec, "rough", "gpt-5.4", "https://example.test/v1", content)
    text = note.read_text(encoding="utf-8")
    assert "gpt-5.4" in text
    assert "secret-test-key" not in text
    assert "## 粗读" in text


def test_preferences_persist_safe_values_only(tmp_path):
    from pdf_manager import preferences

    path = tmp_path / "prefs.json"
    preferences.save_preferences(
        {
            "ai_model": "gpt-5.4",
            "ai_base_url": "https://api.example.test/v1",
            "ai_env_name": "OPENAI_API_KEY",
            "api_key": "secret-test-key",
            "OPENAI_API_KEY": "secret-test-key",
            "unknown": "drop-me",
        },
        path,
    )
    loaded = preferences.load_preferences(path)
    raw = path.read_text(encoding="utf-8")
    assert loaded["ai_model"] == "gpt-5.4"
    assert loaded["ai_env_name"] == "OPENAI_API_KEY"
    assert "api_key" not in loaded
    assert "OPENAI_API_KEY" not in loaded
    assert "secret-test-key" not in raw
    assert "drop-me" not in raw


def test_ocr_status_text_is_stable():
    from pdf_manager import ocr

    status = ocr.status_text()
    assert "OCR" in status
    assert isinstance(ocr.availability(), dict)


def test_extractor_uses_ocr_fallback_when_text_is_empty(tmp_path):
    from pdf_manager import extractor

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class FakePage:
        def get_text(self):
            return ""

    class FakeDoc:
        metadata = {}

        def __len__(self):
            return 1

        def __getitem__(self, index):
            return FakePage()

        def close(self):
            return None

    with patch("pdf_manager.extractor.fitz.open", return_value=FakeDoc()), patch(
        "pdf_manager.ocr.extract_text",
        return_value={"text": "OCR Title\nAbstract\nReferences", "engine": "tesseract", "error": None},
    ):
        info = extractor.extract(pdf, {"enable_ocr": True, "ocr_lang": "chi_sim+eng"})
    assert info["text"].startswith("OCR Title")
    assert info["ocr_engine"] == "tesseract"
    assert info["needs_review"] is False


def test_zotero_api_plan_filters_citable_records(tmp_path):
    from pdf_manager import zotero_api

    records = [
        {"detected_type": "paper", "title": "Ready", "authors": ["Alice"], "doi": "10.1/a", "needs_review": False},
        {"detected_type": "thesis", "title": "Review", "authors": ["Bob"], "needs_review": True},
        {"detected_type": "document", "title": "Manual", "authors": []},
    ]
    with patch("pdf_manager.zotero_api.is_available", return_value=False):
        plan = zotero_api.import_report_placeholder(tmp_path, records, "http://127.0.0.1:23119/api")
    text = plan.read_text(encoding="utf-8")
    assert '"status": "unavailable"' in text
    assert "Ready" in text
    assert "Review" not in text
    assert "Manual" not in text


def test_zotero_api_item_mapping_and_unavailable_report(tmp_path):
    from pdf_manager import zotero_api

    rec = {
        "detected_type": "thesis",
        "thesis_type": "doctoral",
        "title": "Low-Thrust Trajectory Optimization",
        "authors": ["Alice Smith"],
        "year": "2026",
        "venue": "Space University",
        "place": "Beijing",
        "advisor": "Bob Lee",
        "doi": "10.1/thesis",
        "bibtex_key": "Smith2026Low",
        "citation": "GB citation",
        "ieee_citation": "IEEE citation",
        "needs_review": False,
    }
    item = zotero_api.to_zotero_item(rec)
    assert item["itemType"] == "thesis"
    assert item["university"] == "Space University"
    assert item["thesisType"] == "PhD thesis"
    assert "Advisor: Bob Lee" in item["extra"]
    assert "Citation Key: Smith2026Low" in item["extra"]
    with patch("pdf_manager.zotero_api.is_available", return_value=False):
        report = zotero_api.import_records(tmp_path, [rec])
    text = report.read_text(encoding="utf-8")
    assert '"status": "unavailable"' in text
    assert '"attempted": 1' in text


def test_zotero_api_dedupes_and_attaches_existing_pdf(tmp_path):
    from pdf_manager import zotero_api

    pdf = tmp_path / "paper.pdf"
    pdf.write_text("pdf", encoding="utf-8")
    rec = {
        "detected_type": "paper",
        "title": "Existing Paper",
        "authors": ["Alice"],
        "year": "2026",
        "doi": "10.1/existing",
        "needs_review": False,
        "absolute_path": str(pdf),
    }

    def fake_get(url, **kwargs):
        class Response:
            status_code = 200

            def json(self):
                return [{"key": "ABC123", "data": {"key": "ABC123", "DOI": "10.1/existing", "title": "Existing Paper"}}]

        return Response()

    class PostResponse:
        status_code = 201

    with patch("pdf_manager.zotero_api.is_available", return_value=True), patch(
        "requests.get", side_effect=fake_get
    ), patch("requests.post", return_value=PostResponse()) as post:
        report = zotero_api.import_records(tmp_path, [rec], attach_pdf=True, dedupe=True)
    text = report.read_text(encoding="utf-8")
    assert '"status": "deduped"' in text
    assert '"existing": 1' in text
    assert '"attached": 1' in text
    assert rec["zotero_key"] == "ABC123"
    assert post.call_args.kwargs["json"][0]["parentItem"] == "ABC123"


def test_ai_batch_rough_report_orders_research_priorities(tmp_path):
    from pdf_manager import ai_reading

    records = [
        {"detected_type": "paper", "title": "Trajectory Optimization Control", "original_filename": "a.pdf"},
        {"detected_type": "paper", "title": "General Literature Survey", "original_filename": "b.pdf"},
        {"detected_type": "paper", "title": "Needs Review Control", "original_filename": "c.pdf", "needs_review": True},
        {"detected_type": "document", "title": "Manual Control", "original_filename": "d.pdf"},
    ]
    rows = ai_reading.heuristic_batch_rows(records)
    assert [r["file"] for r in rows] == ["a.pdf", "b.pdf"]
    assert rows[0]["priority"] == "高"
    report = ai_reading.write_batch_rough_report(tmp_path, rows, "gpt-5.4", "https://example.test/v1")
    text = report.read_text(encoding="utf-8")
    assert "Trajectory Optimization Control" in text
    assert "c.pdf" not in text


def test_ai_batch_generation_writes_summary_without_storing_key(tmp_path):
    from pdf_manager import ai_reading

    pdf = tmp_path / "paper.pdf"
    pdf.write_text("fake", encoding="utf-8")
    rec = {
        "detected_type": "paper",
        "title": "A Paper",
        "original_filename": "paper.pdf",
        "absolute_path": str(pdf),
        "needs_review": False,
    }
    with patch("pdf_manager.ai_reading.extract_text", return_value="Abstract text"), patch(
        "pdf_manager.ai_reading.call_openai_compatible", return_value="rough note"
    ):
        rows = ai_reading.generate_batch_readings(
            records=[rec],
            out_dir=tmp_path,
            mode="rough",
            model="gpt-5.4",
            base_url="https://example.test/v1",
            api_key="secret-test-key",
            preference="control",
        )
    assert rows[0]["status"] == "generated"
    summary = (tmp_path / "ai_reading_notes" / "batch_ai_rough_summary.md").read_text(encoding="utf-8")
    assert "paper.pdf" in summary
    assert "secret-test-key" not in summary


def test_sample_regression_empty_directory(tmp_path):
    from pdf_manager import sample_regression

    report = sample_regression.run_samples(tmp_path / "samples", tmp_path / "out", {"enable_network": False})
    assert report.exists()
    assert "Sample Regression Report" in report.read_text(encoding="utf-8")


def test_chinese_thesis_metadata_fallback():
    extracted = {
        "meta_title": None,
        "meta_author": None,
        "text": "\n低推力轨迹优化方法研究\n博士学位论文\n作者：张三\n导师：李四\n哈尔滨工业大学\n2024年\n摘要",
    }
    result = metadata.fetch(extracted, {"enable_network": False})
    assert result["title"] == "低推力轨迹优化方法研究"
    assert result["authors"] == ["张三"]
    assert result["advisor"] == "李四"
    assert result["venue"] == "哈尔滨工业大学"
    assert result["place"] == "哈尔滨"
    assert result["year"] == "2024"


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
    assert 'citation_style: "apa"' in (out / "obsidian_notes" / "Smith2024Great.md").read_text(encoding="utf-8")
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
    doc = dict(rec)
    doc.update({
        "original_filename": "manual.pdf",
        "absolute_path": str(tmp_path / "manual.pdf"),
        "relative_path": "manual.pdf",
        "detected_type": "document",
        "title": "Manual",
        "authors": [],
        "bibtex_key": None,
        "tag": "Manual",
        "needs_review": True,
        "_bibtex_entry": None,
    })
    out = writers.write_all([rec, doc], str(tmp_path), {"citation_style": "gbt7714"})
    ris = (out / "references.ris").read_text(encoding="utf-8")
    assert "TY  - THES" in ris
    assert "TI  - Optimal Low-Thrust Trajectories" in ris
    assert "PB  - Space University" in ris
    assert "Manual" not in ris
    guide = (out / "import_guide.md").read_text(encoding="utf-8")
    assert "Zotero" in guide
    assert "Obsidian" in guide
    assert "小绿鲸" not in guide
    report = (out / "zotero_import_report.md").read_text(encoding="utf-8")
    assert "Exported to Zotero: 1" in report
    assert "Skipped: 1" in report
    assert "manual.pdf" in report
    assert "needs review" in report


def test_writer_generates_missing_bibtex_for_reviewed_record(tmp_path):
    from pdf_manager import writers

    rec = {
        "original_filename": "reviewed.pdf",
        "absolute_path": str(tmp_path / "reviewed.pdf"),
        "relative_path": "reviewed.pdf",
        "file_size": 100,
        "page_count": 10,
        "detected_type": "paper",
        "confidence": 0.6,
        "title": "Reviewed Paper",
        "authors": ["Alice Smith"],
        "year": "2026",
        "venue": "Journal of Testing",
        "doi": "10.1000/reviewed",
        "arxiv_id": None,
        "url": None,
        "publisher": None,
        "bibtex_key": "Smith2026Reviewed",
        "tag": None,
        "needs_review": False,
        "_bibtex_entry": None,
    }
    out = writers.write_all([rec], str(tmp_path), {"citation_style": "gbt7714"})
    bib = (out / "references.bib").read_text(encoding="utf-8")
    assert "@article{Smith2026Reviewed" in bib
    assert "Reviewed Paper" in bib
    assert rec["tag"] == "Smith2026Reviewed"


def test_needs_review_literature_is_not_exported_to_zotero(tmp_path):
    from pdf_manager import integrations, writers

    rec = {
        "original_filename": "paper.pdf",
        "absolute_path": str(tmp_path / "paper.pdf"),
        "relative_path": "paper.pdf",
        "file_size": 100,
        "page_count": 10,
        "detected_type": "paper",
        "confidence": 0.82,
        "title": "Needs Review Paper",
        "authors": ["Alice Smith"],
        "year": "2026",
        "venue": "Journal",
        "doi": "10.1000/review",
        "publisher": None,
        "bibtex_key": "Smith2026Review",
        "tag": "Smith2026Review",
        "needs_review": True,
        "classification_reason": "duplicate candidate; confirm merge target",
        "_bibtex_entry": "@article{Smith2026Review,\n}",
    }
    out = writers.write_all([rec], str(tmp_path), {"citation_style": "gbt7714"})
    assert integrations.zotero_export_summary([rec])["citable"] == 0
    assert "Smith2026Review" not in (out / "references.bib").read_text(encoding="utf-8")
    report = (out / "zotero_import_report.md").read_text(encoding="utf-8")
    assert "Skipped: 1" in report
    assert "needs review" in report


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


def test_obsidian_template_rendering(tmp_path):
    from pdf_manager import obsidian

    tpl = tmp_path / "template.md"
    tpl.write_text(
        "# {title}\n{authors}\n{citation}\n{place}\n"
        "{zotero_key}\n{citation_gbt}\n{citation_ieee}\n{school}\n{thesis_type}\n{advisor}\n",
        encoding="utf-8",
    )
    rec = {
        "bibtex_key": "Smith2024",
        "title": "A Great Paper",
        "authors": ["Alice Smith"],
        "citation": "Alice Smith. A Great Paper[J]. 2024.",
        "venue": "Space University",
        "place": "Beijing",
        "thesis_type": "doctoral",
        "advisor": "Bob Lee",
    }
    note = obsidian.generate_note(rec, {"obsidian_note_template": str(tpl), "citation_style": "gbt7714"})
    assert "# A Great Paper" in note
    assert "Alice Smith" in note
    assert "Beijing" in note
    assert "Smith2024" in note
    assert "Space University" in note
    assert "doctoral" in note
    assert "Bob Lee" in note


def test_rename_log_and_undo(tmp_path):
    from pdf_manager import renamer

    out = tmp_path / "_pdf_manager_output"
    old = tmp_path / "old.pdf"
    new = tmp_path / "new.pdf"
    old.write_text("pdf", encoding="utf-8")
    old.rename(new)
    renamer.append_log(out, old, new)
    results = renamer.undo_last_batch(out)
    assert results[0]["undo_status"] == "undone"
    assert old.exists()
    assert not new.exists()
    assert (out / "rename_log.jsonl").exists()
