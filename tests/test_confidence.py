from app.services.confidence import compute_document_confidence


def test_compute_document_confidence_high_for_multiple_strong_chunks():
    confidence = compute_document_confidence(
        chunks_used_for_prompt=[
            {"score": 0.9, "lexical_score": 0.8},
            {"score": 0.84, "lexical_score": 0.7},
            {"score": 0.8, "lexical_score": 0.6},
            {"score": 0.78, "lexical_score": 0.6},
            {"score": 0.76, "lexical_score": 0.6},
            {"score": 0.74, "lexical_score": 0.6},
        ],
        retrieval_metrics={"verification_status": "passed", "bounded_negative_mode": False},
        retrieval_error=None,
        coverage_mode="coverage_required",
        coverage_truncated=False,
        skip_llm=False,
    )

    assert confidence is not None
    assert confidence["label"] == "high"


def test_compute_document_confidence_penalizes_low_evidence_coverage_query():
    confidence = compute_document_confidence(
        chunks_used_for_prompt=[{"score": 0.62, "lexical_score": 0.52}],
        retrieval_metrics={"verification_status": "passed", "bounded_negative_mode": False},
        retrieval_error=None,
        coverage_mode="coverage_required",
        coverage_truncated=False,
        skip_llm=False,
    )

    assert confidence is not None
    assert confidence["label"] != "high"
    assert "coverage_query_with_limited_evidence" in confidence["reason_codes"]


def test_compute_document_confidence_penalizes_truncation():
    confidence = compute_document_confidence(
        chunks_used_for_prompt=[
            {"score": 0.8, "lexical_score": 0.7},
            {"score": 0.75, "lexical_score": 0.65},
            {"score": 0.7, "lexical_score": 0.6},
        ],
        retrieval_metrics={"verification_status": "passed", "bounded_negative_mode": False},
        retrieval_error=None,
        coverage_mode="coverage_required",
        coverage_truncated=True,
        skip_llm=False,
    )

    assert confidence is not None
    assert "coverage_truncated" in confidence["reason_codes"]
