from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from app.services.rag_service import get_rag_context
from fastapi.testclient import TestClient

from eval.build_index import build_index
from eval.common import DB_PATH, GOLDEN_PATH, load_jsonl, temporary_eval_db

os.environ.setdefault("OLLAMA_FAKE", "1")


RETRIEVAL_BUDGET_MS = {
    "cold_p95": 1000.0,
    "warm_p95": 500.0,
}
CHAT_BUDGET_MS = {
    "cold_p95": 1500.0,
    "warm_p95": 1000.0,
}


@dataclass(frozen=True)
class LatencySummary:
    samples_ms: list[float]

    @property
    def p50(self) -> float:
        return _percentile(self.samples_ms, 50)

    @property
    def p95(self) -> float:
        return _percentile(self.samples_ms, 95)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _measure_retrieval_cases(cases: list[dict[str, Any]]) -> tuple[LatencySummary, LatencySummary]:
    cold: list[float] = []
    warm: list[float] = []
    for index, case in enumerate(cases):
        start = time.perf_counter()
        get_rag_context(case["question"], top_k=5, response_format="default")
        elapsed_ms = (time.perf_counter() - start) * 1000
        if index == 0:
            cold.append(elapsed_ms)
        else:
            warm.append(elapsed_ms)
    return LatencySummary(cold), LatencySummary(warm)


def _measure_chat_cases(cases: list[dict[str, Any]]) -> tuple[LatencySummary, LatencySummary]:
    from main import app

    cold: list[float] = []
    warm: list[float] = []
    with TestClient(app) as client:
        for index, case in enumerate(cases):
            payload = {
                "model": "fake-model",
                "message": case["question"],
                "mode": case.get("mode", "document"),
                "document_ids": case.get("expected_doc_ids") or None,
            }
            start = time.perf_counter()
            response = client.post("/api/chat", json=payload)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if response.status_code != 200:
                raise RuntimeError(f"chat request failed: {response.status_code} {response.text}")
            if index == 0:
                cold.append(elapsed_ms)
            else:
                warm.append(elapsed_ms)
    return LatencySummary(cold), LatencySummary(warm)


def _budget_status(summary: LatencySummary, budget_ms: float) -> str:
    return "PASS" if summary.p95 <= budget_ms else "FAIL"


def main() -> int:
    build_index()
    cases = load_jsonl(GOLDEN_PATH)
    if not cases:
        print("No performance cases found.")
        return 1

    with temporary_eval_db(DB_PATH):
        retrieval_cold, retrieval_warm = _measure_retrieval_cases(cases)
        chat_cold, chat_warm = _measure_chat_cases(cases)

    print("retrieval_latency_ms:")
    print(
        f"  cold  p50={retrieval_cold.p50:.1f} p95={retrieval_cold.p95:.1f} budget_p95={RETRIEVAL_BUDGET_MS['cold_p95']:.1f} status={_budget_status(retrieval_cold, RETRIEVAL_BUDGET_MS['cold_p95'])}"
    )
    print(
        f"  warm  p50={retrieval_warm.p50:.1f} p95={retrieval_warm.p95:.1f} budget_p95={RETRIEVAL_BUDGET_MS['warm_p95']:.1f} status={_budget_status(retrieval_warm, RETRIEVAL_BUDGET_MS['warm_p95'])}"
    )
    print("chat_latency_ms:")
    print(
        f"  cold  p50={chat_cold.p50:.1f} p95={chat_cold.p95:.1f} budget_p95={CHAT_BUDGET_MS['cold_p95']:.1f} status={_budget_status(chat_cold, CHAT_BUDGET_MS['cold_p95'])}"
    )
    print(
        f"  warm  p50={chat_warm.p50:.1f} p95={chat_warm.p95:.1f} budget_p95={CHAT_BUDGET_MS['warm_p95']:.1f} status={_budget_status(chat_warm, CHAT_BUDGET_MS['warm_p95'])}"
    )

    all_pass = all(
        [
            retrieval_cold.p95 <= RETRIEVAL_BUDGET_MS["cold_p95"],
            retrieval_warm.p95 <= RETRIEVAL_BUDGET_MS["warm_p95"],
            chat_cold.p95 <= CHAT_BUDGET_MS["cold_p95"],
            chat_warm.p95 <= CHAT_BUDGET_MS["warm_p95"],
        ]
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
