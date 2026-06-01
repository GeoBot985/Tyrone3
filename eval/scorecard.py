from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Metric:
    name: str
    command: list[str] | None
    target: str
    gated: bool = True


METRICS = [
    Metric("tests", [sys.executable, "-m", "pytest", "-q"], "100%"),
    Metric("coverage", [sys.executable, "-m", "pytest", "--cov=app", "--cov=rag"], ">=90%"),
    Metric("lint", [sys.executable, "-m", "ruff", "check", "."], "0"),
    Metric("types", [sys.executable, "-m", "mypy", "app", "rag"], "0"),
    Metric(
        "dead_code",
        [sys.executable, "-m", "vulture", "--min-confidence", "80", "app", "rag"],
        "0",
    ),
    Metric("retrieval_recall", [sys.executable, "-m", "eval.retrieval_eval"], ">=90%"),
    Metric("faithfulness", [sys.executable, "-m", "eval.faithfulness_eval"], ">=90%"),
    Metric("refusal_accuracy", [sys.executable, "-m", "eval.refusal_eval"], ">=90%"),
    Metric("confidence_calibration", [sys.executable, "-m", "eval.confidence_eval"], ">=90%"),
    Metric("intent_routing", [sys.executable, "-m", "eval.intent_eval"], ">=90%"),
]


def run_metric(metric: Metric) -> tuple[str, int]:
    if metric.command is None:
        return "SKIPPED (not implemented)", 0

    cp = subprocess.run(metric.command, cwd=ROOT, capture_output=True, text=True)
    status = "PASS" if cp.returncode == 0 else "FAIL"
    return status, cp.returncode


def main() -> int:
    eval_metric_names = {"retrieval_recall", "faithfulness", "refusal_accuracy"}
    if any(metric.name in eval_metric_names for metric in METRICS):
        prereq = subprocess.run(
            [sys.executable, "-m", "eval.build_index"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if prereq.returncode != 0:
            print(prereq.stdout)
            print(prereq.stderr, file=sys.stderr)
            return prereq.returncode

    rows: list[tuple[str, str, str]] = []
    exit_code = 0
    for metric in METRICS:
        status, code = run_metric(metric)
        rows.append((metric.name, status, metric.target))
        if metric.gated and code != 0:
            exit_code = 1

    print(f"{'Metric':<20} {'Status':<24} Target")
    for name, status, target in rows:
        print(f"{name:<20} {status:<24} {target}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
