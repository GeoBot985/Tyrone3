from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import DEFAULT_MODEL
from app.config import CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD
from eval.common import DB_PATH, GOLDEN_PATH, cache_path, load_jsonl, temporary_eval_db
from ollama_client import chat as ollama_chat
from ollama_client import get_models

ANSWER_CACHE_VERSION = "confidence-v2"


def _select_model() -> str:
    env_model = os.environ.get("OLLAMA_MODEL")
    if env_model:
        return env_model

    models, error = asyncio.run(get_models())
    if error:
        raise RuntimeError(error)
    preferred = [
        "granite4:1b",
        "gemma3:1b",
        "granite4:3b",
        "granite3.3:8b",
        "qwen3:8b",
        "phi3:14b",
        "deepseek-r1:7b",
    ]
    for candidate in preferred:
        if candidate in models:
            return candidate
    if models:
        return models[0]
    return DEFAULT_MODEL


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _run_answer_case(client: TestClient, model: str, case: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": model,
        "message": case["question"],
        "mode": "document",
        "document_ids": case.get("expected_doc_ids") or None,
        "cache_version": ANSWER_CACHE_VERSION,
        "confidence_thresholds": {
            "high": CONFIDENCE_HIGH_THRESHOLD,
            "medium": CONFIDENCE_MEDIUM_THRESHOLD,
        },
    }
    cache_key = cache_path("answer", payload)
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    response = client.post("/api/chat", json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"chat request failed: {response.status_code} {response.text}")

    data = response.json()
    _write_cache(cache_key, data)
    return data


def _grade_case(
    model: str,
    question: str,
    answer: str,
    evidence: list[dict[str, Any]] | None,
    case: dict[str, Any],
) -> dict[str, Any]:
    prompt = Path(__file__).with_name("grader_prompt.txt").read_text(encoding="utf-8")
    grader_input = {
        "question": question,
        "answer": answer,
        "expected_doc_ids": case.get("expected_doc_ids") or [],
        "expected_chunk_substrings": case.get("expected_chunk_substrings") or [],
        "answer_must_contain": case.get("answer_must_contain") or [],
        "answer_must_not_contain": case.get("answer_must_not_contain") or [],
        "retrieved_evidence": evidence or [],
    }
    cache_key = cache_path("grade", {"model": model, **grader_input})
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    grader_prompt = (
        f"{prompt}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"EVIDENCE JSON:\n{json.dumps(evidence or [], indent=2, sort_keys=True)}\n\n"
        f"GOLD JSON:\n{json.dumps(grader_input, indent=2, sort_keys=True)}\n\n"
        "Return JSON only."
    )
    result, request_summary, error = asyncio.run(ollama_chat(model, grader_prompt, temperature=0.0))
    if error:
        raise RuntimeError(error)

    content = result.get("message", {}).get("content", "")
    parsed = _extract_json(content)
    parsed["_request_summary"] = request_summary
    parsed["_raw"] = content
    _write_cache(cache_key, parsed)
    return parsed


def main() -> int:
    cases = [
        case
        for case in load_jsonl(GOLDEN_PATH)
        if not case.get("should_refuse") and case.get("faithfulness_eval", True)
    ]
    if not cases:
        print("No faithfulness cases found.")
        return 1

    model = _select_model()
    passes = 0
    total = 0

    with temporary_eval_db(DB_PATH):
        from main import app

        with TestClient(app) as client:
            for case in cases:
                answer_payload = _run_answer_case(client, model, case)
                reply = answer_payload.get("reply") or ""
                evidence = answer_payload.get("evidence") or []
                grade = _grade_case(model, case["question"], reply, evidence, case)
                overall = bool(grade.get("overall_pass"))
                total += 1
                passes += int(overall)
                status = "PASS" if overall else "FAIL"
                print(f"{status} {case['question']}")
                print(f"  reply={reply[:180]}")
                print(f"  grade={json.dumps(grade, sort_keys=True)}")

    accuracy = passes / total if total else 0.0
    print(f"faithfulness_accuracy={accuracy:.3f}")
    return 0 if accuracy >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
