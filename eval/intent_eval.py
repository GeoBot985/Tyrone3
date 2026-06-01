from __future__ import annotations

from collections import defaultdict
from typing import Any

from eval.common import ROOT, load_jsonl
from tools.gobook_tools import detect_rpa_intent
from tools.workspace_tools import detect_workspace_intent

INTENT_PATH = ROOT / "eval" / "intents.jsonl"


def _detect(case: dict[str, Any]) -> str | None:
    detector = case["detector"]
    if detector == "rpa":
        return detect_rpa_intent(case["text"])
    if detector == "workspace":
        return detect_workspace_intent(case["text"])
    raise ValueError(f"Unknown detector: {detector}")


def main() -> int:
    cases = load_jsonl(INTENT_PATH)
    if not cases:
        print("No intent cases found.")
        return 1

    matrix: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    correct = 0

    for case in cases:
        expected = case.get("expected")
        actual = _detect(case)
        matrix[case["detector"]][str(expected)][str(actual)] += 1
        ok = actual == expected
        correct += int(ok)
        status = "PASS" if ok else "FAIL"
        print(f"{status} [{case['detector']}] {case['text']}")
        print(f"  expected={expected} actual={actual}")

    accuracy = correct / len(cases)
    print("confusion_matrix:")
    for detector in sorted(matrix):
        print(f"  {detector}:")
        for expected in sorted(matrix[detector]):
            actuals = matrix[detector][expected]
            parts = ", ".join(f"{actual}={count}" for actual, count in sorted(actuals.items()))
            print(f"    expected={expected}: {parts}")
    print(f"routing_accuracy={accuracy:.3f}")
    return 0 if accuracy >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
