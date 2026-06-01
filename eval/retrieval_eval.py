from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eval.common import DB_PATH, GOLDEN_PATH, load_jsonl, temporary_eval_db
from app.services.rag_service import get_rag_context


@dataclass(frozen=True)
class RetrievalOutcome:
    question: str
    recall: float
    reciprocal_rank: float
    relevant_rank: int | None
    matched_chunk: str | None
    matched_doc_id: str | None


def _is_relevant_chunk(case: dict[str, Any], chunk: dict[str, Any]) -> bool:
    doc_ids = set(case.get("expected_doc_ids") or [])
    if doc_ids and chunk.get("document_id") not in doc_ids:
        return False
    text = (chunk.get("text") or "").lower()
    substrings = [sub.lower() for sub in case.get("expected_chunk_substrings") or []]
    return any(sub in text for sub in substrings)


def evaluate_case(case: dict[str, Any]) -> RetrievalOutcome:
    rag_result = get_rag_context(case["question"], top_k=5, response_format="default")
    chunks = rag_result.get("chunks") or []
    relevant_rank = None
    matched_chunk = None
    matched_doc_id = None
    expected_doc_ids = list(case.get("expected_doc_ids") or [])
    matched_docs: set[str] = set()

    for index, chunk in enumerate(chunks, start=1):
        if _is_relevant_chunk(case, chunk):
            doc_id = chunk.get("document_id")
            if doc_id:
                matched_docs.add(doc_id)
            if relevant_rank is None:
                relevant_rank = index
                matched_chunk = (chunk.get("text") or "").strip()
                matched_doc_id = doc_id

    if expected_doc_ids:
        recall = 1.0 if matched_docs.issuperset(expected_doc_ids) else 0.0
    else:
        recall = 1.0 if relevant_rank is not None else 0.0
    reciprocal_rank = 1.0 / relevant_rank if relevant_rank else 0.0
    return RetrievalOutcome(
        question=case["question"],
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        relevant_rank=relevant_rank,
        matched_chunk=matched_chunk,
        matched_doc_id=matched_doc_id,
    )


def main() -> int:
    cases = [case for case in load_jsonl(GOLDEN_PATH) if not case.get("should_refuse")]
    if not cases:
        print("No retrieval cases found.")
        return 1

    with temporary_eval_db(DB_PATH):
        outcomes = [evaluate_case(case) for case in cases]

    for outcome in outcomes:
        rank_display = outcome.relevant_rank if outcome.relevant_rank is not None else "MISS"
        print(f"[{rank_display}] {outcome.question}")
        if outcome.matched_chunk:
            print(f"  matched_doc_id={outcome.matched_doc_id}")
            print(f"  matched_chunk={outcome.matched_chunk[:180]}")

    recall_at_k = sum(outcome.recall for outcome in outcomes) / len(outcomes)
    mrr = sum(outcome.reciprocal_rank for outcome in outcomes) / len(outcomes)
    print(f"recall@k={recall_at_k:.3f}")
    print(f"mrr={mrr:.3f}")
    return 0 if recall_at_k >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
