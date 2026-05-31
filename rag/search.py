import numpy as np
import re

from .db import get_all_embeddings
from .embedder import embed_text


_QUERY_FOCUS_STOPWORDS = {
    "show", "list", "extract", "summarize", "summary", "what", "which", "give", "provide",
    "find", "from", "with", "that", "this", "there", "here", "into", "about", "under",
    "records", "record", "rows", "entries", "all", "our", "the", "and", "for", "are",
    "any", "please", "table", "tabulate",
}


def _query_region_mode(query: str) -> str:
    q = (query or "").lower()
    if any(term in q for term in ("top", "highest", "largest", "transactions", "expenses")):
        return "table_row_preferred"
    if any(term in q for term in ("total", "sum", "percentage")):
        return "summary_allowed"
    return "neutral"


def detect_retrieval_mode(query: str) -> str:
    q = (query or "").strip().lower()
    if not q:
        return "default"

    enumeration_patterns = (
        r"\b(list|show|enumerate|which|what are|give me|provide|find all)\b",
        r"\b(references?|mentions?|occurrences?|entries|rows|transactions)\b",
        r"\b(any .+\?)",
    )
    if any(re.search(pattern, q) for pattern in enumeration_patterns):
        return "enumeration"
    return "default"


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def _tokenize(s: str | None) -> set[str]:
    if not s:
        return set()
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return set(s.split())


def normalize_token(token: str) -> str:
    token = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", (token or "").lower())
    if len(token) < 4:
        return token

    if token.endswith("ies") and len(token) >= 5:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) >= 5:
        stem = token[:-2]
        if stem.endswith(("s", "x", "z", "ch", "sh")):
            return stem
        if stem.endswith("e"):
            return stem
    if token.endswith("s") and len(token) >= 5 and not token.endswith("ss"):
        return token[:-1]
    return token


def normalize_tokens(tokens: set[str]) -> set[str]:
    return {normalize_token(token) for token in tokens if token}


def tokenize_for_lexical_matching(text: str | None) -> tuple[set[str], set[str]]:
    original = _tokenize(text)
    normalized = normalize_tokens(original)
    return original, normalized


def _normalize_identifier(term: str) -> str:
    return re.sub(r"[^a-z0-9]", "", term.lower())


def _detect_identifier_like_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"\b[A-Za-z0-9-]+\b", query or "")
    detected = []
    for term in raw_terms:
        normalized = _normalize_identifier(term)
        if len(normalized) < 4:
            continue
        if re.search(r"[a-zA-Z]", term) and re.search(r"\d", term):
            detected.append(term)
    return list(dict.fromkeys(detected))


def _extract_query_phrases(query: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', query or "")
    if quoted:
        return [phrase.strip() for phrase in quoted if phrase.strip()]

    query = (query or "").strip()
    if len(query.split()) >= 3:
        return [query]
    return []


def _extract_focus_tokens(query: str) -> set[str]:
    original_tokens = _tokenize(query)
    normalized = normalize_tokens(original_tokens)
    focus_tokens = set()
    for token in normalized:
        if len(token) < 5:
            continue
        if token in _QUERY_FOCUS_STOPWORDS:
            continue
        if token.isdigit():
            continue
        focus_tokens.add(token)
    return focus_tokens


def score_lexical(query: str, text: str | None, document_name: str | None = None) -> float:
    if not query:
        return 0.0

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    text_tokens = _tokenize(text)
    matches = query_tokens.intersection(text_tokens)
    score = len(matches) / len(query_tokens)

    if document_name:
        doc_tokens = _tokenize(document_name)
        doc_matches = query_tokens.intersection(doc_tokens)
        if doc_matches:
            score += 0.1 * (len(doc_matches) / len(query_tokens))

    return min(score, 1.0)


def _score_lexical_full_corpus(query: str, item: dict) -> tuple[float, list[str], dict]:
    text = item.get("text") or ""
    text_lower = text.lower()
    match_types: list[str] = []
    lexical_score = score_lexical(query, text, item.get("document_name"))
    query_tokens = _tokenize(query)
    normalized_query_tokens = normalize_tokens(query_tokens)
    text_tokens, normalized_text_tokens = tokenize_for_lexical_matching(text)
    doc_tokens, normalized_doc_tokens = tokenize_for_lexical_matching(item.get("document_name") or "")
    matched_tokens_original = sorted(query_tokens.intersection(text_tokens))
    matched_tokens_normalized = sorted(
        normalized_query_tokens.intersection(normalized_text_tokens) - set(matched_tokens_original)
    )

    identifier_like_terms = _detect_identifier_like_terms(query)
    normalized_text = _normalize_identifier(text)
    normalized_doc_name = _normalize_identifier(item.get("document_name") or "")

    for term in identifier_like_terms:
        pattern = rf"\b{re.escape(term.lower())}\b"
        if re.search(pattern, text_lower):
            lexical_score = max(lexical_score, 1.0)
            match_types.append("exact_token")
        elif _normalize_identifier(term) and _normalize_identifier(term) in normalized_text:
            lexical_score = max(lexical_score, 0.95)
            match_types.append("normalized_token")
        elif _normalize_identifier(term) and _normalize_identifier(term) in normalized_doc_name:
            lexical_score = max(lexical_score, 0.85)
            match_types.append("filename_match")

    for phrase in _extract_query_phrases(query):
        phrase_lower = phrase.lower()
        if phrase_lower in text_lower:
            lexical_score = max(lexical_score, 1.0)
            match_types.append("exact_phrase")

    if matched_tokens_normalized:
        lexical_score = max(lexical_score, 0.7)
        match_types.append("normalized_token")

    if normalized_query_tokens.intersection(normalized_doc_tokens):
        lexical_score = max(lexical_score, 0.3)
        match_types.append("filename_match")

    debug = {
        "matched_tokens_original": matched_tokens_original,
        "matched_tokens_normalized": matched_tokens_normalized,
    }
    return min(lexical_score, 1.0), list(dict.fromkeys(match_types)), debug


def _strong_lexical_hit(match_types: list[str]) -> bool:
    strong = {"exact_token", "normalized_token", "exact_phrase", "focus_token"}
    return any(match_type in strong for match_type in match_types)


def _collect_corpus_focus_tokens(all_items: list[dict], focus_tokens: set[str]) -> set[str]:
    supported = set()
    for item in all_items:
        text_tokens, normalized_text_tokens = tokenize_for_lexical_matching(item.get("text"))
        doc_tokens, normalized_doc_tokens = tokenize_for_lexical_matching(item.get("document_name"))
        available = text_tokens | normalized_text_tokens | doc_tokens | normalized_doc_tokens
        for token in focus_tokens:
            if token in available:
                supported.add(token)
    return supported


def _collect_lexical_candidates(all_items: list[dict], query: str) -> tuple[list[dict], dict]:
    exact_hits = 0
    normalized_hits = 0
    phrase_hits = 0
    forced_hits = []
    lexical_candidates = []

    normalized_query_tokens = sorted(normalize_tokens(_tokenize(query)))
    focus_tokens = _extract_focus_tokens(query)
    supported_focus_tokens = _collect_corpus_focus_tokens(all_items, focus_tokens)

    for item in all_items:
        lexical_score, match_types, debug = _score_lexical_full_corpus(query, item)
        if lexical_score <= 0:
            continue

        matched_focus_tokens = sorted(
            supported_focus_tokens.intersection(set(debug["matched_tokens_original"]) | set(debug["matched_tokens_normalized"]))
        )
        missing_focus_tokens = sorted(supported_focus_tokens - set(matched_focus_tokens))

        if matched_focus_tokens:
            lexical_score = min(1.0, lexical_score + min(0.25, 0.12 * len(matched_focus_tokens)))
            match_types = list(dict.fromkeys(match_types + ["focus_token"]))
        elif supported_focus_tokens:
            lexical_score = max(0.0, lexical_score - min(0.25, 0.08 * len(supported_focus_tokens)))
            match_types = list(dict.fromkeys(match_types + ["missing_focus_token"]))

        candidate = {
            "item": item,
            "lexical_score": lexical_score,
            "match_types": match_types,
            "forced_include": _strong_lexical_hit(match_types),
            "lexical_debug": debug,
            "matched_focus_tokens": matched_focus_tokens,
            "missing_focus_tokens": missing_focus_tokens,
        }
        lexical_candidates.append(candidate)

        if "exact_token" in match_types:
            exact_hits += 1
        if "normalized_token" in match_types:
            normalized_hits += 1
        if "exact_phrase" in match_types:
            phrase_hits += 1
        if candidate["forced_include"]:
            forced_hits.append(candidate)

    lexical_candidates.sort(
        key=lambda candidate: (candidate["forced_include"], candidate["lexical_score"]),
        reverse=True,
    )

    metrics = {
        "identifier_like_terms": _detect_identifier_like_terms(query),
        "lexical_normalization_enabled": True,
        "normalized_query_tokens": normalized_query_tokens,
        "focus_tokens": sorted(focus_tokens),
        "supported_focus_tokens": sorted(supported_focus_tokens),
        "exact_lexical_hits": exact_hits,
        "normalized_lexical_hits": normalized_hits,
        "phrase_hits": phrase_hits,
        "forced_included_chunks": len(forced_hits),
    }
    return lexical_candidates, metrics


def _merge_candidates(lexical_candidates: list[dict], vector_candidates: list[dict], candidate_pool_size: int) -> list[dict]:
    merged = {}

    for candidate in lexical_candidates:
        if candidate["forced_include"]:
            item = candidate["item"]
            key = (item["document_id"], item["chunk_index"], item["text"])
            merged[key] = {
                "item": item,
                "lexical_score": candidate["lexical_score"],
                "vector_score": 0.0,
                "match_types": candidate["match_types"],
                "forced_include": True,
                "lexical_debug": candidate["lexical_debug"],
                "matched_focus_tokens": candidate["matched_focus_tokens"],
            }

    for candidate in vector_candidates[:candidate_pool_size]:
        item = candidate["item"]
        key = (item["document_id"], item["chunk_index"], item["text"])
        existing = merged.get(key)
        if existing:
            existing["vector_score"] = candidate["vector_score"]
        else:
            merged[key] = {
                "item": item,
                "lexical_score": 0.0,
                "vector_score": candidate["vector_score"],
                "match_types": [],
                "forced_include": False,
                "lexical_debug": {"matched_tokens_original": [], "matched_tokens_normalized": []},
                "matched_focus_tokens": [],
            }

    for candidate in lexical_candidates:
        item = candidate["item"]
        key = (item["document_id"], item["chunk_index"], item["text"])
        if key in merged:
            merged[key]["lexical_score"] = max(merged[key]["lexical_score"], candidate["lexical_score"])
            merged[key]["match_types"] = list(dict.fromkeys(merged[key]["match_types"] + candidate["match_types"]))
            merged[key]["lexical_debug"]["matched_tokens_original"] = sorted(set(
                merged[key]["lexical_debug"]["matched_tokens_original"] + candidate["lexical_debug"]["matched_tokens_original"]
            ))
            merged[key]["lexical_debug"]["matched_tokens_normalized"] = sorted(set(
                merged[key]["lexical_debug"]["matched_tokens_normalized"] + candidate["lexical_debug"]["matched_tokens_normalized"]
            ))
            merged[key]["matched_focus_tokens"] = sorted(set(
                merged[key].get("matched_focus_tokens", []) + candidate.get("matched_focus_tokens", [])
            ))
            continue
        if len(merged) >= candidate_pool_size + len([c for c in lexical_candidates if c["forced_include"]]):
            break
            merged[key] = {
                "item": item,
                "lexical_score": candidate["lexical_score"],
                "vector_score": 0.0,
                "match_types": candidate["match_types"],
                "forced_include": candidate["forced_include"],
                "lexical_debug": candidate["lexical_debug"],
                "matched_focus_tokens": candidate["matched_focus_tokens"],
            }

    return list(merged.values())


def _collect_enumeration_results(
    scored_results: list[dict],
    top_k: int,
    per_doc_cap: int,
    lexical_match_cap: int,
) -> list[dict]:
    final_results = []
    doc_counts = {}

    lexical_first = [
        result for result in scored_results
        if {"exact_phrase", "exact_token", "normalized_token", "focus_token"}.intersection(result["match_types"])
    ]

    for result in lexical_first[:lexical_match_cap]:
        doc_id = result["document_id"]
        count = doc_counts.get(doc_id, 0)
        if count >= per_doc_cap:
            continue
        final_results.append(result)
        doc_counts[doc_id] = count + 1
        if len(final_results) >= top_k:
            return final_results

    for result in scored_results:
        key = (result["document_id"], result["chunk_index"], result["text"])
        if any((item["document_id"], item["chunk_index"], item["text"]) == key for item in final_results):
            continue
        doc_id = result["document_id"]
        count = doc_counts.get(doc_id, 0)
        if count >= per_doc_cap:
            continue
        final_results.append(result)
        doc_counts[doc_id] = count + 1
        if len(final_results) >= top_k:
            break

    return final_results


def search(conn, query: str, top_k=5, document_ids: list[str] | None = None,
           vector_weight=0.7, lexical_weight=0.3, candidate_pool_size=20, per_doc_cap=2,
           retrieval_mode: str = "default", lexical_match_cap: int = 100):
    all_embeddings_with_meta = get_all_embeddings(conn, document_ids=document_ids)
    region_mode = _query_region_mode(query)

    eligible_items = []
    for item in all_embeddings_with_meta:
        if region_mode == "table_row_preferred" and item.get("region_type") in {"summary_block", "pivot_like"}:
            continue
        eligible_items.append(item)

    lexical_candidates, lexical_metrics = _collect_lexical_candidates(eligible_items, query)

    query_embedding = embed_text(query)
    vector_candidates = []
    for item in eligible_items:
        v_score = cosine_similarity(query_embedding, item["embedding"])
        vector_candidates.append({
            "item": item,
            "vector_score": float(v_score),
        })
    vector_candidates.sort(key=lambda candidate: candidate["vector_score"], reverse=True)

    merged_candidates = _merge_candidates(lexical_candidates, vector_candidates, candidate_pool_size)

    scored_results = []
    for candidate in merged_candidates:
        item = candidate["item"]
        v_score = candidate["vector_score"]
        l_score = max(candidate["lexical_score"], score_lexical(query, item.get("text"), item.get("document_name")))
        region_boost = 0.0
        if region_mode == "table_row_preferred":
            if item.get("region_type") == "table_row":
                region_boost = 0.15
            elif item.get("region_type") == "header":
                region_boost = -0.05
        elif region_mode == "summary_allowed" and item.get("region_type") in {"summary_block", "pivot_like"}:
            region_boost = 0.1

        lexical_priority_boost = 0.25 if candidate["forced_include"] else 0.0
        focus_token_boost = min(0.2, 0.1 * len(candidate.get("matched_focus_tokens", [])))
        final_score = (vector_weight * v_score) + (lexical_weight * l_score) + region_boost + lexical_priority_boost + focus_token_boost

        scored_results.append({
            "document_id": item["document_id"],
            "document_name": item["document_name"],
            "ingested_at": item["ingested_at"],
            "chunk_index": item["chunk_index"],
            "text": item["text"],
            "region_type": item.get("region_type"),
            "sheet_name": item.get("sheet_name"),
            "row_index": item.get("row_index"),
            "cell_range": item.get("cell_range"),
            "vector_score": v_score,
            "lexical_score": l_score,
            "region_boost": region_boost,
            "lexical_priority_boost": lexical_priority_boost,
            "focus_token_boost": focus_token_boost,
            "match_types": candidate["match_types"],
            "forced_include": candidate["forced_include"],
            "matched_tokens_original": candidate["lexical_debug"]["matched_tokens_original"],
            "matched_tokens_normalized": candidate["lexical_debug"]["matched_tokens_normalized"],
            "matched_focus_tokens": candidate.get("matched_focus_tokens", []),
            "score": float(final_score),
        })

    scored_results.sort(
        key=lambda result: (
            len(result.get("matched_focus_tokens", [])),
            result["forced_include"],
            "focus_token" in result["match_types"],
            "exact_phrase" in result["match_types"],
            "exact_token" in result["match_types"],
            "normalized_token" in result["match_types"],
            result["lexical_score"],
            result["score"],
        ),
        reverse=True,
    )

    if retrieval_mode == "enumeration":
        final_top_k = _collect_enumeration_results(
            scored_results,
            top_k=top_k,
            per_doc_cap=per_doc_cap,
            lexical_match_cap=lexical_match_cap,
        )
    else:
        final_top_k = []
        doc_counts = {}
        for result in scored_results:
            doc_id = result["document_id"]
            count = doc_counts.get(doc_id, 0)
            if count < per_doc_cap:
                final_top_k.append(result)
                doc_counts[doc_id] = count + 1
            if len(final_top_k) >= top_k:
                break

    return {
        "results": final_top_k,
        "metrics": {
            "eligible_docs": len(set(item["document_id"] for item in eligible_items)),
            "eligible_chunk_count": len(eligible_items),
            "candidate_count": len(all_embeddings_with_meta),
            "pool_size": min(candidate_pool_size, len(vector_candidates)),
            "region_mode": region_mode,
            "lexical_prepass_run": True,
            "lexical_normalization_enabled": lexical_metrics["lexical_normalization_enabled"],
            "normalized_query_tokens": lexical_metrics["normalized_query_tokens"],
            "focus_tokens": lexical_metrics["focus_tokens"],
            "supported_focus_tokens": lexical_metrics["supported_focus_tokens"],
            "identifier_like_terms": lexical_metrics["identifier_like_terms"],
            "exact_lexical_hits": lexical_metrics["exact_lexical_hits"],
            "normalized_lexical_hits": lexical_metrics["normalized_lexical_hits"],
            "phrase_hits": lexical_metrics["phrase_hits"],
            "forced_included_chunks": lexical_metrics["forced_included_chunks"],
            "vector_candidate_count": len(vector_candidates[:candidate_pool_size]),
            "merged_candidate_count": len(merged_candidates),
            "bounded_negative_mode": lexical_metrics["exact_lexical_hits"] == 0 and lexical_metrics["normalized_lexical_hits"] == 0,
            "retrieval_mode": retrieval_mode,
            "lexical_match_cap": lexical_match_cap,
        }
    }
