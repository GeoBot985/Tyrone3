import os

from rag.db import (
    get_connection, list_documents, delete_document, clear_corpus,
    get_corpus_stats, get_document_by_id, get_all_chunks_for_document,
    find_exact_chunk
)
from rag.search import search, detect_retrieval_mode
from app.config import (
    DB_PATH, VECTOR_WEIGHT, LEXICAL_WEIGHT,
    CANDIDATE_POOL_SIZE, PER_DOC_CAP,
    SINGLE_DOC_CANDIDATE_POOL_SIZE, SINGLE_DOC_PER_DOC_CAP,
    ENUMERATION_TOP_K, ENUMERATION_PER_DOC_CAP, ENUMERATION_LEXICAL_MATCH_CAP,
    DOCUMENT_NARROW_TOP_K, DOCUMENT_COVERAGE_TOP_K, DOCUMENT_MAX_COVERAGE_CHUNKS,
    DOCUMENT_COVERAGE_SINGLE_DOC_PER_DOC_CAP, DOCUMENT_COVERAGE_MULTI_DOC_PER_DOC_CAP,
    DOCUMENT_COVERAGE_SCORE_DROP_THRESHOLD, DOCUMENT_COVERAGE_CONSECUTIVE_DROP_LIMIT,
    DOCUMENT_MIN_USEFUL_SCORE,
)
from app.services.document_coverage import detect_document_coverage_mode


def verify_retrieved_chunks(conn, chunks: list[dict]) -> tuple[list[dict], int]:
    verified_chunks = []
    discarded_count = 0

    for chunk in chunks:
        exact_match = find_exact_chunk(
            conn,
            chunk["document_id"],
            chunk["chunk_index"],
            chunk["text"],
        )
        if exact_match:
            verified_chunks.append(chunk)
        else:
            discarded_count += 1

    return verified_chunks, discarded_count


def compact_retrieved_chunks_for_prompt(chunks: list[dict], response_format: str) -> list[dict]:
    compacted = []
    seen = set()

    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue

        normalized_text = "\n".join(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
        dedupe_key = (
            chunk.get("document_id"),
            chunk.get("chunk_index"),
            normalized_text,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        compacted.append({
            **chunk,
            "text": normalized_text,
        })

    if response_format in {"list", "table"}:
        compacted.sort(
            key=lambda item: (
                item.get("document_name", ""),
                item.get("sheet_name") or "",
                item.get("row_index") if item.get("row_index") is not None else item.get("chunk_index", 0),
                item.get("chunk_index", 0),
            )
        )

    return compacted


def _apply_coverage_stabilization(chunks: list[dict], max_chunks: int) -> tuple[list[dict], bool, str]:
    if not chunks:
        return [], False, "no_verified_chunks"

    selected = []
    truncated = False
    reason = "candidate_pool_exhausted"
    consecutive_drops = 0
    previous_score = None

    for chunk in chunks:
        score = float(chunk.get("score", 0.0))

        if score < DOCUMENT_MIN_USEFUL_SCORE:
            truncated = True
            reason = "low_score_floor_reached"
            break

        if previous_score is not None and (previous_score - score) >= DOCUMENT_COVERAGE_SCORE_DROP_THRESHOLD:
            consecutive_drops += 1
        else:
            consecutive_drops = 0

        if consecutive_drops >= DOCUMENT_COVERAGE_CONSECUTIVE_DROP_LIMIT and len(selected) >= 5:
            truncated = True
            reason = "score_drop_stabilized"
            break

        selected.append(chunk)
        previous_score = score

        if len(selected) >= max_chunks:
            truncated = True
            reason = "max_coverage_chunks_reached"
            break

    return selected, truncated, reason


def get_rag_context(
    query: str,
    top_k: int = DOCUMENT_NARROW_TOP_K,
    document_ids: list[str] | None = None,
    response_format: str = "default",
) -> dict:
    """
    Returns:
    {
        "enabled": bool,
        "query": str,
        "chunks": list[dict],
        "chunks_for_prompt": list[dict],
        "metrics": dict | None,
        "error": str | None
    }
    """
    result = {
        "enabled": True,
        "query": query,
        "chunks": [],
        "chunks_for_prompt": [],
        "metrics": {
            "eligible_docs": 0,
            "candidate_count": 0,
            "pool_size": 0,
            "verification_attempts": 0,
            "verified_chunks": 0,
            "discarded_unverified_chunks": 0,
            "verification_status": "not_run",
            "coverage_mode": "narrow_lookup",
            "coverage_required": False,
            "coverage_truncated": False,
            "coverage_reason": "not_run",
            "retrieval_top_k_requested": top_k,
            "retrieval_verified_chunks_count": 0,
            "retrieval_chunks_used_for_prompt": 0,
        },
        "error": None
    }

    if not os.path.exists(DB_PATH):
        result["error"] = "knowledge base empty / unavailable"
        return result

    conn = None
    try:
        conn = get_connection(DB_PATH)

        single_doc_mode = bool(document_ids) and len(document_ids) == 1
        retrieval_mode = detect_retrieval_mode(query)
        coverage_mode = detect_document_coverage_mode(query, response_format)
        coverage_required = coverage_mode == "coverage_required"

        requested_top_k = DOCUMENT_COVERAGE_TOP_K if coverage_required else top_k
        max_chunks = DOCUMENT_MAX_COVERAGE_CHUNKS if coverage_required else max(top_k, DOCUMENT_NARROW_TOP_K)
        base_candidate_pool_size = SINGLE_DOC_CANDIDATE_POOL_SIZE if single_doc_mode else CANDIDATE_POOL_SIZE
        base_per_doc_cap = SINGLE_DOC_PER_DOC_CAP if single_doc_mode else PER_DOC_CAP

        if coverage_required:
            effective_top_k = min(max_chunks, max(requested_top_k, DOCUMENT_COVERAGE_TOP_K))
            effective_per_doc_cap = DOCUMENT_COVERAGE_SINGLE_DOC_PER_DOC_CAP if single_doc_mode else DOCUMENT_COVERAGE_MULTI_DOC_PER_DOC_CAP
        else:
            effective_top_k = max(top_k, ENUMERATION_TOP_K) if retrieval_mode == "enumeration" else top_k
            effective_per_doc_cap = max(base_per_doc_cap, ENUMERATION_PER_DOC_CAP) if retrieval_mode == "enumeration" else base_per_doc_cap

        candidate_pool_size = max(base_candidate_pool_size, effective_top_k)
        max_attempts = 4 if coverage_required else 3
        total_discarded = 0
        best_verified_chunks = []
        last_metrics = {}

        for attempt in range(1, max_attempts + 1):
            search_data = search(
                conn,
                query,
                top_k=min(max_chunks if coverage_required else effective_top_k, effective_top_k * attempt * 2),
                document_ids=document_ids,
                vector_weight=VECTOR_WEIGHT,
                lexical_weight=LEXICAL_WEIGHT,
                candidate_pool_size=candidate_pool_size,
                per_doc_cap=max(effective_per_doc_cap, effective_top_k * attempt if coverage_required else effective_top_k),
                retrieval_mode=retrieval_mode,
                lexical_match_cap=ENUMERATION_LEXICAL_MATCH_CAP if retrieval_mode == "enumeration" else max(effective_top_k * 2, 20),
            )

            raw_chunks = search_data.get("results", [])
            verified_chunks, discarded_count = verify_retrieved_chunks(conn, raw_chunks)
            total_discarded += discarded_count
            last_metrics = search_data.get("metrics") or {}

            if verified_chunks:
                best_verified_chunks = verified_chunks

            stabilized_chunks, coverage_truncated, coverage_reason = (
                _apply_coverage_stabilization(best_verified_chunks, max_chunks)
                if coverage_required
                else (best_verified_chunks[:effective_top_k], False, "narrow_lookup_limit")
            )

            prompt_chunks = compact_retrieved_chunks_for_prompt(stabilized_chunks, response_format)

            result["metrics"] = {
                "eligible_docs": last_metrics.get("eligible_docs", 0),
                "candidate_count": last_metrics.get("candidate_count", 0),
                "eligible_chunk_count": last_metrics.get("eligible_chunk_count", 0),
                "pool_size": last_metrics.get("pool_size", 0),
                "retrieval_mode": last_metrics.get("retrieval_mode", retrieval_mode),
                "region_mode": last_metrics.get("region_mode", "neutral"),
                "single_doc_mode": single_doc_mode,
                "per_doc_cap": max(effective_per_doc_cap, effective_top_k * attempt if coverage_required else effective_top_k),
                "requested_top_k": top_k,
                "effective_top_k": effective_top_k,
                "lexical_match_cap": last_metrics.get("lexical_match_cap", 0),
                "verification_attempts": attempt,
                "verified_chunks": len(best_verified_chunks),
                "discarded_unverified_chunks": total_discarded,
                "verification_status": "passed" if best_verified_chunks else "empty",
                "coverage_mode": coverage_mode,
                "coverage_required": coverage_required,
                "coverage_truncated": coverage_truncated,
                "coverage_reason": coverage_reason,
                "retrieval_top_k_requested": requested_top_k,
                "retrieval_verified_chunks_count": len(best_verified_chunks),
                "retrieval_chunks_used_for_prompt": len(prompt_chunks),
                "bounded_negative_mode": last_metrics.get("bounded_negative_mode", False),
                "lexical_normalization_enabled": last_metrics.get("lexical_normalization_enabled", False),
                "normalized_query_tokens": last_metrics.get("normalized_query_tokens", []),
                "identifier_like_terms": last_metrics.get("identifier_like_terms", []),
                "exact_lexical_hits": last_metrics.get("exact_lexical_hits", 0),
                "normalized_lexical_hits": last_metrics.get("normalized_lexical_hits", 0),
                "phrase_hits": last_metrics.get("phrase_hits", 0),
                "forced_included_chunks": last_metrics.get("forced_included_chunks", 0),
                "vector_candidate_count": last_metrics.get("vector_candidate_count", 0),
                "merged_candidate_count": last_metrics.get("merged_candidate_count", 0),
            }

            result["chunks"] = best_verified_chunks[:max_chunks] if coverage_required else best_verified_chunks[:effective_top_k]
            result["chunks_for_prompt"] = prompt_chunks

            if not coverage_required and len(result["chunks"]) >= effective_top_k:
                break

            if coverage_required:
                if len(prompt_chunks) >= max_chunks:
                    break
                candidate_count = last_metrics.get("candidate_count", 0)
                if candidate_count and candidate_pool_size >= candidate_count:
                    break
            else:
                candidate_count = last_metrics.get("candidate_count", 0)
                if candidate_count and candidate_pool_size >= candidate_count:
                    break

            candidate_pool_size = max(candidate_pool_size * 2, effective_top_k * (attempt + 1) * 2)

        if not result["chunks"] and total_discarded > 0:
            result["metrics"]["verification_status"] = "all_discarded"

    except Exception as e:
        result["error"] = str(e)
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

    return result


def get_full_document_content(document_id: str) -> dict:
    """
    Reconstructs the full document text from its chunks.
    Returns:
    {
        "document_id": str,
        "document_name": str,
        "full_text": str,
        "chunk_count": int,
        "error": str | None
    }
    """
    result = {
        "document_id": document_id,
        "document_name": None,
        "full_text": "",
        "chunk_count": 0,
        "error": None
    }

    if not os.path.exists(DB_PATH):
        result["error"] = "knowledge base empty / unavailable"
        return result

    conn = None
    try:
        conn = get_connection(DB_PATH)
        doc = get_document_by_id(conn, document_id)
        if not doc:
            result["error"] = f"Document with ID {document_id} not found."
            return result

        result["document_name"] = doc["document_name"]
        chunks = get_all_chunks_for_document(conn, document_id)
        result["chunk_count"] = len(chunks)
        text_parts = [c["text"] for c in chunks]
        result["full_text"] = "\n".join(text_parts)

    except Exception as e:
        result["error"] = str(e)
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

    return result


def delete_document_service(document_id: str) -> dict:
    try:
        conn = get_connection(DB_PATH)
        success = delete_document(conn, document_id)
        return {"ok": True, "deleted": success}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except:
            pass


def clear_corpus_service() -> dict:
    try:
        conn = get_connection(DB_PATH)
        clear_corpus(conn)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except:
            pass


def get_corpus_stats_service() -> dict:
    if not os.path.exists(DB_PATH):
        return {
            "ok": True,
            "stats": {
                "total_documents": 0,
                "total_chunks": 0,
                "last_ingestion_at": None
            }
        }
    try:
        conn = get_connection(DB_PATH)
        stats = get_corpus_stats(conn)
        return {"ok": True, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except:
            pass


def list_indexed_documents() -> dict:
    if not os.path.exists(DB_PATH):
        return {
            "ok": True,
            "documents": [],
            "error": None
        }

    try:
        conn = get_connection(DB_PATH)
        docs = list_documents(conn)
        return {
            "ok": True,
            "documents": docs,
            "error": None
        }
    except Exception as e:
        return {
            "ok": False,
            "documents": [],
            "error": str(e)
        }
    finally:
        try:
            conn.close()
        except:
            pass
