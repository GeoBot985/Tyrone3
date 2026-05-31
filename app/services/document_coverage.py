from __future__ import annotations


_COVERAGE_TERMS = (
    " all ",
    " summary ",
    " summarize ",
    " every ",
    " full list ",
    " complete ",
    " tabulate ",
    " show all ",
    " extract all ",
    " list all ",
)


def detect_document_coverage_mode(query: str, response_format: str) -> str:
    normalized = f" {(query or '').strip().lower()} "

    if response_format in {"list", "table", "summary", "comparison"}:
        return "coverage_required"

    if any(term in normalized for term in _COVERAGE_TERMS):
        return "coverage_required"

    return "narrow_lookup"


def explain_document_coverage_reason(query: str, response_format: str) -> str:
    normalized = f" {(query or '').strip().lower()} "

    if response_format in {"list", "table", "summary", "comparison"}:
        return "format_requires_coverage"

    if any(term in normalized for term in _COVERAGE_TERMS):
        return "matched_coverage_keyword"

    return "default_narrow_lookup"
