from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from fastapi.testclient import TestClient

from eval.common import DB_PATH, GOLDEN_PATH, load_jsonl, temporary_eval_db
from eval.faithfulness_eval import _grade_case, _run_answer_case, _select_model


def _is_correct_answer(reply: str, grade: dict[str, Any]) -> bool:
    return bool(grade.get("overall_pass")) and not reply.strip().startswith("Insufficient information")


def _bucket(label: str | None) -> str:
    return label or "missing"


def _is_refusal_reply(reply: str, case: dict[str, Any]) -> bool:
    if case.get("should_refuse"):
        return True
    return reply.strip().startswith("Insufficient information")


def main() -> int:
    cases = [
        case
        for case in load_jsonl(GOLDEN_PATH)
        if case.get("confidence_eval", case.get("faithfulness_eval", False) or case.get("should_refuse", False))
    ]
    if not cases:
        print("No confidence calibration cases found.")
        return 1

    model = _select_model()
    totals = Counter()
    by_confidence = defaultdict(lambda: Counter())

    with temporary_eval_db(DB_PATH):
        from main import app

        with TestClient(app) as client:
            for case in cases:
                answer_payload = _run_answer_case(client, model, case)
                reply = answer_payload.get("reply") or ""
                evidence = answer_payload.get("evidence") or []
                confidence = answer_payload.get("confidence") or {}
                if _is_refusal_reply(reply, case):
                    grade = {
                        "grounded_in_evidence": False,
                        "answers_question": False,
                        "overall_pass": False,
                        "rationale": "refusal bucket",
                    }
                    actual_correct = False
                else:
                    grade = _grade_case(model, case["question"], reply, evidence, case)
                    actual_correct = _is_correct_answer(reply, grade)
                predicted_high = confidence.get("label") == "high"
                predicted_low = confidence.get("label") == "low"
                predicted_medium = confidence.get("label") == "medium"

                totals["cases"] += 1
                totals["correct"] += int(actual_correct)
                totals["pred_high"] += int(predicted_high)
                totals["pred_low"] += int(predicted_low)
                totals["pred_medium"] += int(predicted_medium)

                if actual_correct and predicted_high:
                    totals["agree"] += 1
                elif not actual_correct and predicted_low:
                    totals["agree"] += 1
                else:
                    totals["disagree"] += 1

                by_confidence[_bucket(confidence.get("label"))]["total"] += 1
                by_confidence[_bucket(confidence.get("label"))]["correct"] += int(actual_correct)
                by_confidence[_bucket(confidence.get("label"))]["incorrect"] += int(not actual_correct)

                status = "PASS" if actual_correct else "FAIL"
                print(f"{status} {case['question']}")
                print(f"  confidence={json.dumps(confidence, sort_keys=True)}")
                print(f"  reply={reply[:180]}")
                print(f"  faithfulness={json.dumps(grade, sort_keys=True)}")

    agreement = totals["agree"] / totals["cases"] if totals["cases"] else 0.0
    accuracy = totals["correct"] / totals["cases"] if totals["cases"] else 0.0

    print("reliability_table:")
    for label in ("high", "medium", "low", "missing"):
        bucket = by_confidence[label]
        if not bucket["total"]:
            continue
        print(
            f"  {label:<7} total={bucket['total']:<3} correct={bucket['correct']:<3} incorrect={bucket['incorrect']:<3}"
        )
    print(f"answer_correctness={accuracy:.3f}")
    print(f"confidence_agreement={agreement:.3f}")
    return 0 if agreement >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
