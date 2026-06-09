PUBLISHER_KW = {"ieee", "acm", "springer", "elsevier", "wiley", "nature", "science"}
THESIS_KW = {
    "学位论文", "硕士", "博士", "硕士学位", "博士学位",
    "dissertation", "thesis", "ph.d", "phd", "master thesis",
    "doctoral dissertation", "degree of master", "degree of doctor",
}


def classify(extracted: dict, cfg: dict) -> dict:
    text_lower = extracted.get("text", "").lower()
    text_raw = extracted.get("text", "")
    score = 0.0
    reasons = []
    is_thesis = any(kw in text_lower or kw in text_raw for kw in THESIS_KW)
    thesis_type = None
    if is_thesis:
        if any(kw in text_lower or kw in text_raw for kw in {"博士", "博士学位", "ph.d", "phd", "doctor", "doctoral"}):
            thesis_type = "doctoral"
        elif any(kw in text_lower or kw in text_raw for kw in {"硕士", "硕士学位", "master"}):
            thesis_type = "master"
        else:
            thesis_type = "unknown"

    if is_thesis:
        score += 0.45
        reasons.append("Thesis/dissertation signal found")
    if extracted.get("doi"):
        score += 0.3
        reasons.append("DOI detected")
    if extracted.get("arxiv_id"):
        score += 0.3
        reasons.append("arXiv ID detected")
    if "abstract" in text_lower and "references" in text_lower:
        score += 0.2
        reasons.append("Abstract and References found")
    if "introduction" in text_lower:
        score += 0.1
        reasons.append("Introduction section found")
    has_publisher = any(kw in text_lower for kw in PUBLISHER_KW)
    if has_publisher:
        score += 0.1
        reasons.append("Publisher keyword found")
    if extracted.get("needs_review"):
        reasons.append("Text extraction weak or failed")
    if not reasons:
        reasons.append("No strong scholarly signal")

    score = min(score, 1.0)

    paper_thresh = cfg.get("min_paper_confidence", 0.75)
    review_thresh = cfg.get("review_confidence_threshold", 0.45)

    needs_review = extracted.get("needs_review", False)
    has_identifier = bool(extracted.get("doi") or extracted.get("arxiv_id"))
    has_article_structure = "abstract" in text_lower and "references" in text_lower
    has_section_signal = "introduction" in text_lower or has_publisher
    strong_paper_signal = has_identifier and has_article_structure and has_section_signal

    if is_thesis and score >= review_thresh:
        detected_type = "thesis"
    elif score >= paper_thresh or strong_paper_signal:
        detected_type = "paper"
    elif score >= review_thresh:
        detected_type = "unknown"
        needs_review = True
    else:
        detected_type = "document"

    return {
        "detected_type": detected_type,
        "confidence": round(score, 3),
        "needs_review": needs_review,
        "classification_reason": "; ".join(reasons),
        "thesis_type": thesis_type,
    }
