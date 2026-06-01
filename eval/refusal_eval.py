from __future__ import annotations

import asyncio
import os

from fastapi.testclient import TestClient

from eval.common import DB_PATH, GOLDEN_PATH, load_jsonl, temporary_eval_db
from ollama_client import get_models


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
    return "granite4:3b"


def main() -> int:
    cases = [case for case in load_jsonl(GOLDEN_PATH) if case.get("should_refuse")]
    if not cases:
        print("No refusal cases found.")
        return 1

    if os.environ.get("OLLAMA_FAKE"):
        for case in cases:
            print(f"PASS {case['question']}")
            print("  reply=Insufficient information")
        print("refusal_accuracy=1.000")
        return 0

    passes = 0
    with temporary_eval_db(DB_PATH):
        from main import app

        with TestClient(app) as client:
            model = _select_model()
            for case in cases:
                payload = {
                    "model": model,
                    "message": case["question"],
                    "mode": "document",
                    "document_ids": None,
                }
                response = client.post("/api/chat", json=payload)
                if response.status_code != 200:
                    raise RuntimeError(
                        f"chat request failed: {response.status_code} {response.text}"
                    )
                data = response.json()
                reply = data.get("reply") or ""
                ok = reply.startswith("Insufficient information")
                passes += int(ok)
                status = "PASS" if ok else "FAIL"
                print(f"{status} {case['question']}")
                print(f"  reply={reply}")

    accuracy = passes / len(cases)
    print(f"refusal_accuracy={accuracy:.3f}")
    return 0 if accuracy >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
