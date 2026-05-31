from __future__ import annotations

import re


RESPONSE_FORMATS = {"binary", "list", "table", "summary", "comparison", "default"}

_BINARY_PREFIXES = ("is ", "are ", "does ", "do ", "did ", "can ", "should ", "has ", "have ", "was ", "were ")
_LIST_PHRASES = (
    "list",
    "show all",
    "extract all",
    "enumerate",
    "what are all",
    "give me all",
    "which items",
    "all occurrences",
    "all examples",
)
_TABLE_PHRASES = (
    "table",
    "tabulate",
    "columns",
    "rows",
    "date and amount",
    "list with dates",
    "show in a table",
)
_SUMMARY_PHRASES = ("summarize", "summary", "overview", "explain briefly", "high level", "key points")
_COMPARISON_PHRASES = ("compare", "difference", "versus", " vs ", "similarities", "contrast")
_TABLE_FIELDS = ("date", "amount", "provider", "member", "description", "control", "owner", "status")


def _normalize(query: str) -> str:
    normalized = re.sub(r"\s+", " ", (query or "").strip().lower())
    return f"{normalized} "


def detect_document_response_format(query: str) -> str:
    normalized = _normalize(query)

    if normalized.startswith(_BINARY_PREFIXES):
        return "binary"

    if any(phrase in normalized for phrase in _COMPARISON_PHRASES) or re.search(r"how does .+ differ from .+", normalized):
        return "comparison"

    if any(phrase in normalized for phrase in _SUMMARY_PHRASES):
        return "summary"

    table_keyword_match = any(phrase in normalized for phrase in _TABLE_PHRASES)
    list_keyword_match = any(phrase in normalized for phrase in _LIST_PHRASES)
    field_hits = sum(1 for field in _TABLE_FIELDS if re.search(rf"\b{re.escape(field)}s?\b", normalized))

    if table_keyword_match or (list_keyword_match and field_hits >= 2):
        return "table"

    if list_keyword_match:
        return "list"

    return "default"


def explain_document_response_format_rule(query: str) -> str:
    normalized = _normalize(query)

    if normalized.startswith(_BINARY_PREFIXES):
        return "matched_binary_prefix"

    if any(phrase in normalized for phrase in _COMPARISON_PHRASES) or re.search(r"how does .+ differ from .+", normalized):
        return "matched_comparison_keyword"

    if any(phrase in normalized for phrase in _SUMMARY_PHRASES):
        return "matched_summary_keyword"

    table_keyword_match = any(phrase in normalized for phrase in _TABLE_PHRASES)
    list_keyword_match = any(phrase in normalized for phrase in _LIST_PHRASES)
    field_hits = sum(1 for field in _TABLE_FIELDS if re.search(rf"\b{re.escape(field)}s?\b", normalized))

    if table_keyword_match:
        return "matched_table_keyword"

    if list_keyword_match and field_hits >= 2:
        return "matched_list_plus_field_pair"

    if list_keyword_match:
        return "matched_list_keyword"

    return "fallback_default"
