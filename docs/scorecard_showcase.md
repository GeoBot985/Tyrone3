# Quality Scorecard — Showcase

One command runs the entire quality gate — static analysis, the full test suite with coverage,
the live RAG evaluation suite, and latency budgets — and prints a single pass/fail table:

```bash
python -m eval.scorecard
```

## Latest run

<!-- The block below is the verbatim console output of `python -m eval.scorecard`. -->
<!-- Regenerate with:  python -m eval.scorecard > docs/scorecard_output.txt -->

```text
==============================================================================
 Tyrone 3.0 - Portfolio Quality Scorecard
==============================================================================
Metric                   Status   Value                      Target
------------------------------------------------------------------------------
tests                    PASS     148 passed                 100% pass
coverage                 PASS     93%                        >=90%
lint                     PASS     all checks passed          0 errors
types                    PASS     0 errors / 29 files        0 errors
dead_code                PASS     0 findings                 0 findings
retrieval_recall         PASS     recall@k=100.0% mrr=0.974  >=90%
faithfulness             PASS     100.0%                     >=90%
refusal_accuracy         PASS     100.0%                     >=90%
confidence_calibration   PASS     100.0%                     >=90%
intent_routing           PASS     100.0%                     >=90%
latency                  PASS     retrieval p95=38.6ms chat p95=27.3ms p95 within budget
------------------------------------------------------------------------------
Result: ALL GATES PASS
==============================================================================
```

## How to capture the screenshot for your portfolio

You want a real terminal screenshot (it reads as authentic — sharper than a code block):

1. Open a clean terminal, maximize it, and pick a legible font/theme.
2. Run:
   ```bash
   python -m eval.scorecard
   ```
3. Wait for the `Result: ALL GATES PASS` banner, then screenshot the window.
4. Save it as `docs/img/05-scorecard.png` and reference it in `README.md`.

The verbatim text above is also saved at `docs/scorecard_output.txt` so you can paste it into
slides or a case-study writeup without re-running.

## What each row proves

| Row | Tool | Why it matters in a portfolio |
|---|---|---|
| `tests` | pytest | Every test passes — the system behaves as specified |
| `coverage` | pytest-cov | ≥90% line coverage on `app/` + `rag/` — the core is exercised, not just present |
| `lint` | ruff | Zero style/correctness lint errors — disciplined, readable code |
| `types` | mypy | Zero type errors on core modules — interfaces are sound |
| `dead_code` | vulture | No unused/dead code — the repo is tidy |
| `retrieval_recall` | custom eval | The RAG layer actually finds the right evidence |
| `faithfulness` | LLM-graded eval | Answers are grounded in evidence — no hallucination |
| `refusal_accuracy` | custom eval | Says "insufficient information" instead of inventing facts |
| `confidence_calibration` | custom eval | The confidence score can be trusted |
| `intent_routing` | custom eval | Personal-mode tools are dispatched correctly |
| `latency` | perf eval | Retrieval and chat paths stay within stated p95 budgets |

> **Note on the latency row:** measured with a deterministic fake LLM (`OLLAMA_FAKE=1`) so the
> numbers isolate Tyrone's own overhead (retrieval, orchestration, payload assembly) rather than
> model generation time. This keeps the budget reproducible across machines and in CI.

> **Note on the eval set:** the RAG metrics run against a curated golden set (small, hand-built
> corpus across all supported file types, including a scanned/OCR PDF). It demonstrates the
> evaluation *methodology* end-to-end; the harness scales to a larger corpus by dropping files into
> `eval/corpus/` and adding cases to `eval/golden.jsonl`.
