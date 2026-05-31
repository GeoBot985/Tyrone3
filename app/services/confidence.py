from __future__ import annotations

from typing import Any

from app.config import CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _confidence_label(score: float) -> str:
    if score >= CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if score >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def compute_document_confidence(
    *,
    chunks_used_for_prompt: list[dict],
    retrieval_metrics: dict[str, Any] | None,
    retrieval_error: str | None,
    coverage_mode: str,
    coverage_truncated: bool,
    skip_llm: bool,
) -> dict[str, Any] | None:
    if not chunks_used_for_prompt and not retrieval_error:
        return None

    metrics = retrieval_metrics or {}
    reason_codes: list[str] = []

    if retrieval_error:
        score = 0.1
        reason_codes.append("retrieval_error")
    elif not chunks_used_for_prompt:
        score = 0.15 if skip_llm else 0.2
        reason_codes.append("no_verified_chunks")
    else:
        used_count = len(chunks_used_for_prompt)
        avg_score = sum(max(0.0, min(1.0, float(chunk.get("score", 0.0)))) for chunk in chunks_used_for_prompt) / used_count
        lexical_strength = sum(1 for chunk in chunks_used_for_prompt if float(chunk.get("lexical_score", 0.0)) >= 0.5) / used_count
        evidence_count_factor = min(1.0, used_count / (6.0 if coverage_mode == "coverage_required" else 2.0))

        score = (0.55 * avg_score) + (0.2 * evidence_count_factor) + (0.15 * lexical_strength) + 0.1

        if used_count == 1:
            score -= 0.18
            reason_codes.append("single_chunk_only")
        else:
            reason_codes.append("multiple_verified_chunks")

        if avg_score >= 0.72:
            reason_codes.append("strong_top_scores")
        elif avg_score < 0.4:
            score -= 0.15
            reason_codes.append("weak_score_tail")

        if coverage_mode == "coverage_required":
            if used_count < 5:
                score -= 0.18
                reason_codes.append("coverage_query_with_limited_evidence")
            if coverage_truncated:
                score -= 0.14
                reason_codes.append("coverage_truncated")
        elif used_count >= 2:
            reason_codes.append("sufficient_for_narrow_lookup")

        if metrics.get("verification_status") == "all_discarded":
            score -= 0.2
            reason_codes.append("verification_losses")

        if metrics.get("bounded_negative_mode"):
            score -= 0.08
            reason_codes.append("weak_lexical_support")

    score = _clamp(score)
    return {
        "score": round(score, 2),
        "label": _confidence_label(score),
        "coverage_mode": coverage_mode,
        "coverage_truncated": coverage_truncated,
        "reason_codes": reason_codes,
    }
