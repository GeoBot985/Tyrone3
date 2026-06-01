from __future__ import annotations

import re
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
    Metric("tests", [sys.executable, "-m", "pytest", "-q"], "100% pass"),
    Metric("coverage", [sys.executable, "-m", "pytest", "--cov=app", "--cov=rag"], ">=90%"),
    Metric("lint", [sys.executable, "-m", "ruff", "check", "."], "0 errors"),
    Metric("types", [sys.executable, "-m", "mypy", "app", "rag"], "0 errors"),
    Metric(
        "dead_code",
        [sys.executable, "-m", "vulture", "--min-confidence", "80", "app", "rag"],
        "0 findings",
    ),
    Metric("retrieval_recall", [sys.executable, "-m", "eval.retrieval_eval"], ">=90%"),
    Metric("faithfulness", [sys.executable, "-m", "eval.faithfulness_eval"], ">=90%"),
    Metric("refusal_accuracy", [sys.executable, "-m", "eval.refusal_eval"], ">=90%"),
    Metric("confidence_calibration", [sys.executable, "-m", "eval.confidence_eval"], ">=90%"),
    Metric("intent_routing", [sys.executable, "-m", "eval.intent_eval"], ">=90%"),
    Metric("latency", [sys.executable, "-m", "eval.perf_eval"], "p95 within budget"),
]


def _pct(raw: str) -> str:
    """Render a 0..1 ratio token as a percentage."""
    try:
        return f"{float(raw) * 100:.1f}%"
    except ValueError:
        return raw


def extract_detail(name: str, stdout: str) -> str:
    """Best-effort pull of the headline number from an eval's stdout."""
    text = stdout or ""

    def search(pattern: str) -> str | None:
        match = re.search(pattern, text)
        return match.group(1) if match else None

    if name == "tests":
        passed = search(r"(\d+) passed")
        return f"{passed} passed" if passed else "-"
    if name == "coverage":
        total = search(r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?%)")
        return total or "-"
    if name == "lint":
        return "all checks passed" if "All checks passed" in text else "-"
    if name == "types":
        files = search(r"no issues found in (\d+) source files")
        return f"0 errors / {files} files" if files else "-"
    if name == "dead_code":
        return "0 findings" if not text.strip() else f"{len(text.strip().splitlines())} findings"
    if name == "retrieval_recall":
        recall = search(r"recall@k=([\d.]+)")
        mrr = search(r"mrr=([\d.]+)")
        if recall:
            return f"recall@k={_pct(recall)} mrr={mrr}" if mrr else f"recall@k={_pct(recall)}"
        return "-"
    if name == "faithfulness":
        val = search(r"faithfulness_accuracy=([\d.]+)")
        return _pct(val) if val else "-"
    if name == "refusal_accuracy":
        val = search(r"refusal_accuracy=([\d.]+)")
        return _pct(val) if val else "-"
    if name == "confidence_calibration":
        val = search(r"confidence_agreement=([\d.]+)")
        return _pct(val) if val else "-"
    if name == "intent_routing":
        val = search(r"routing_accuracy=([\d.]+)")
        return _pct(val) if val else "-"
    if name == "latency":
        warm_p95s = re.findall(r"warm\s+p50=[\d.]+ p95=([\d.]+)", text)
        if len(warm_p95s) >= 2:
            return f"retrieval p95={warm_p95s[0]}ms chat p95={warm_p95s[1]}ms"
        if warm_p95s:
            return f"warm p95={warm_p95s[0]}ms"
        return "-"
    return "-"


def run_metric(metric: Metric) -> tuple[str, str, int]:
    if metric.command is None:
        return "SKIPPED", "not implemented", 0

    cp = subprocess.run(metric.command, cwd=ROOT, capture_output=True, text=True)
    status = "PASS" if cp.returncode == 0 else "FAIL"
    detail = extract_detail(metric.name, cp.stdout)
    return status, detail, cp.returncode


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

    rows: list[tuple[str, str, str, str]] = []
    exit_code = 0
    for metric in METRICS:
        status, detail, code = run_metric(metric)
        rows.append((metric.name, status, detail, metric.target))
        if metric.gated and code != 0:
            exit_code = 1

    print("=" * 78)
    print(" Tyrone 3.0 - Portfolio Quality Scorecard")
    print("=" * 78)
    print(f"{'Metric':<24} {'Status':<8} {'Value':<26} Target")
    print("-" * 78)
    for name, status, detail, target in rows:
        print(f"{name:<24} {status:<8} {detail:<26} {target}")
    print("-" * 78)
    overall = "ALL GATES PASS" if exit_code == 0 else "GATE FAILURES PRESENT"
    print(f"Result: {overall}")
    print("=" * 78)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
