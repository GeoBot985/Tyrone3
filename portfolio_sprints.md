# Tyrone 3.0 — Portfolio Release Sprint Plan

**Goal:** Bring Tyrone 3.0 to **≥ 90 % on every portfolio metric** (code quality, test/coverage,
reliability & tooling, and RAG answer quality) so it can ship as a portfolio piece.

**Audience:** This document is handed to a coding agent for execution. It is self-contained.
The agent has the **full live stack** available (Ollama running with at least one model pulled,
the FastAPI app runnable end-to-end), so live-LLM-graded evaluation is in scope.

> **How to use this doc:** Execute sprints in order. Each sprint is independently shippable and
> ends with explicit, machine-checkable acceptance criteria. Do not start a later sprint's quality
> work before its measurement tooling exists — Sprint 0 makes everything measurable first.

---

## 1. What Tyrone 3.0 is (current architecture)

A **local-first** FastAPI + Ollama assistant. Single entry point `main.py` exposes a web UI
(`templates/index.html` + `static/app.js`) and a JSON API. Three operating modes:

| Mode | What it does | Key code |
|---|---|---|
| **Chat** | Plain LLM chat; optionally grounded on one full document | `main.py` chat branch, `prompt_builder.build_chat_with_document_prompt` |
| **Document** | Hybrid vector (0.7) + lexical (0.3) RAG over a DuckDB corpus, with coverage stabilization, chunk verification, evidence chunks, and a confidence score | `app/services/rag_service.py`, `rag/search.py`, `app/services/confidence.py` |
| **Personal** | A personal memory store (entity/fact retrieval) **plus** tool execution: GoBook squash-court RPA (Playwright), Google Workspace (Gmail/Calendar/Sheets), WhatsApp Web | `app/services/personal_service.py`, `tools/gobook_tools.py`, `tools/workspace_tools.py` |

**Supporting subsystems:**
- **Ingestion pipeline** — PDF/DOCX/PPTX/XLSX/XLS/CSV/TXT/MD, OCR (pytesseract), markitdown,
  layout normalizer, spreadsheet extractor (`rag/ingest.py` + extractors).
- **Watcher** — a deterministic rule engine that inspects each request (`app/services/watcher.py`).
  Currently **pass-through only** (always `allowed=True, modified=False`).
- **Token / session accounting** — `app/utils/token_utils.py`, `app/services/session_grounding.py`.
- **Config** — all RAG/retrieval/confidence constants in `app/config.py`.

---

## 2. Baseline scorecard (measured 2026-05-31)

| Metric | Current | Target | Gap |
|---|---|---|---|
| Test suite green | **97 %** (99/102 pass) | 100 % (gate) | 3 async tests cannot run — missing `pytest-asyncio` |
| Line coverage (`app/`, `rag/`) | **Unknown** (never measured) | ≥ 90 % | No coverage tooling |
| Lint clean (ruff) | **Unknown** | 0 errors | No linter configured |
| Type clean (mypy, core modules) | **Unknown** | 0 errors on `app/`, `rag/` | No type checker configured |
| Dead/broken code | **Present** | 0 | Orphaned `_rpa_*_impl` in `main.py:772-938` ref unimported symbols |
| Deprecation warnings | **Present** | 0 | `@app.on_event` deprecated (FastAPI lifespan) |
| RAG retrieval recall@k | **Unknown** | ≥ 90 % | No eval harness, no golden dataset |
| RAG answer faithfulness (grounded, no hallucination) | **Unknown** | ≥ 90 % | No eval harness |
| "Insufficient info" refusal accuracy | **Unknown** | ≥ 90 % | No eval harness |
| Confidence calibration | **Unknown** | ≥ 90 % agreement | Heuristic only, never validated |
| Tool intent-detection accuracy | **Unknown** | ≥ 90 % | No labelled fixtures |
| Graceful-failure rate (no unhandled 500s) | **Unknown** | 100 % | Untested |
| Retrieval latency (p95, warm) | **Unknown** | Documented budget met | Never measured |
| Docs / portfolio polish | **Minimal** | Complete | README is setup-only; no architecture/demo docs |

**Headline finding:** *the metrics don't exist yet.* The single most valuable early work is building
the measurement harness (Sprint 0–2) so "90 %" becomes a number the agent can read, not a guess.

---

## 3. The portfolio metric rubric (definition of "90 %")

Each metric below has an exact definition and a single source of truth: a script under
`eval/` that prints a number. A top-level `eval/scorecard.py` aggregates them and **fails CI if
any gated metric is below target**.

1. **Tests green** — `pytest` exit 0, 0 skips for environmental reasons. *Gate: 100 %.*
2. **Coverage** — `coverage` line % over `app/` and `rag/` (tools/ excluded — external I/O). *Gate: ≥ 90 %.*
3. **Lint** — `ruff check` reports 0 errors. *Gate: 0.*
4. **Types** — `mypy app rag` reports 0 errors. *Gate: 0 on core; tools/ may use `# type: ignore` islands.*
5. **Dead code** — `vulture` (or equivalent) reports 0 high-confidence unused symbols. *Gate: 0.*
6. **Retrieval recall@k** — fraction of golden questions whose gold chunk(s) appear in retrieved set. *Gate: ≥ 90 %.*
7. **Answer faithfulness** — LLM-graded: answer is fully supported by retrieved evidence, no invented facts. *Gate: ≥ 90 %.*
8. **Refusal accuracy** — for out-of-corpus questions, system returns the "insufficient information" path. *Gate: ≥ 90 %.*
9. **Confidence calibration** — `high` confidence ⇒ answer correct; `low` ⇒ wrong/refused. Agreement ≥ 90 %.
10. **Tool intent accuracy** — labelled-utterance set routed to the correct tool/intent. *Gate: ≥ 90 %.*
11. **Robustness** — fuzz/edge API matrix produces a structured response, never an unhandled 500. *Gate: 100 %.*
12. **Performance** — retrieval p95 within a stated budget on the eval corpus (documented, not gated hard).
13. **Docs** — README, ARCHITECTURE.md, a runnable demo script, and screenshots exist. *Gate: present.*

---

## 4. Sprints

### Sprint 0 — Measurement foundation (make everything a number)
**Why first:** You cannot hit 90 % on metrics you can't read. This sprint turns every rubric item
into a script and wires a gate.

**Tasks**
- Add dev tooling. Create `pyproject.toml` with `[project.optional-dependencies] dev = [...]`:
  `pytest`, `pytest-asyncio`, `pytest-cov`, `coverage`, `ruff`, `mypy`, `vulture`, `httpx`.
  Pin `requirements.txt` versions for reproducibility.
- Fix the 3 failing async tests: add `pytest-asyncio` and configure `asyncio_mode = "auto"`
  in `pyproject.toml`. Affected: `tests/test_spec_012_v2.py::test_api_chat_routing`,
  `tests/test_spec_017_api.py::test_personal_mode_api`, `tests/test_spec_017_modes.py::test_modes_api`.
- Add `conftest.py` with a shared temp-DB fixture so tests never touch the committed `rag_v2.db`.
- Create `eval/scorecard.py` — runs each metric script, prints a table, exits non-zero if any gate fails.
  Stub the not-yet-built metrics (Sprints 2+) as `SKIPPED (not implemented)` so the runner works today.
- Add GitHub Actions CI (`.github/workflows/ci.yml`): install deps, run `ruff`, `mypy`, `pytest --cov`,
  `eval/scorecard.py`. Cache pip. (Mark LLM-dependent eval jobs as a separate, non-blocking workflow
  since CI has no Ollama — see Sprint 5 for the mock-LLM path.)
- Add `ruff.toml`/`[tool.ruff]` and `[tool.mypy]` config. Start `mypy` in non-strict mode scoped to
  `app/` and `rag/`; record the baseline error count.

**Acceptance criteria**
- `pytest` → **102/102 pass, 0 skips**.
- `coverage` produces an HTML + terminal report; baseline % recorded in the sprint notes.
- `python eval/scorecard.py` runs and prints the full rubric table (gated rows real, others SKIPPED).
- CI is green on a no-op PR.

---

### Sprint 1 — Code-quality cleanup (lint, types, dead code, refactor)
**Targets rubric:** Lint, Types, Dead code, Deprecations.

**Tasks**
- **Remove dead/broken code:** delete the orphaned `_rpa_book_impl`, `_rpa_cancel_impl`,
  `_rpa_list_impl`, `_rpa_open_courts_impl`, `_detect_rpa_intent`, `_extract_rpa_details`,
  `_extract_date_and_times`, `_time_to_minutes`, `_slot_within_range` in `main.py:691-938`.
  They reference unimported symbols (`async_playwright`, `login`, `tempfile`, `load_credentials`,
  `validate_booking_date`) and would `NameError` if ever called — the live routes use
  `tools.gobook_tools` instead. Confirm with `vulture` and a grep that nothing imports them.
- **Fix deprecation:** replace `@app.on_event("startup")` with FastAPI `lifespan` handler.
- **Refactor the mega-handler:** `main.py:api_chat` is ~515 lines mixing routing, RAG, personal
  tools, workspace tools, watcher, and debug assembly. Extract per-mode handlers
  (`handle_document_mode`, `handle_personal_mode`, `handle_chat_mode`) into
  `app/services/chat_orchestrator.py`. The workspace-intent dispatch (`main.py:300-457`) should move
  into `tools/workspace_tools.py` as a single `dispatch_workspace_intent(...)`. Keep behavior identical;
  rely on the now-passing API tests as the guardrail.
- Make `ruff check` and `mypy app rag` clean. Resolve real issues; use targeted ignores only with a reason.
- Run `vulture` and remove or justify every finding.

**Acceptance criteria**
- `ruff check` → 0 errors. `mypy app rag` → 0 errors. `vulture` → 0 high-confidence findings.
- 0 deprecation warnings from `pytest`.
- `main.py` `api_chat` body ≤ ~80 lines; all existing tests still pass unchanged.

---

### Sprint 2 — RAG evaluation harness + golden dataset
**Targets rubric:** Retrieval recall@k, Faithfulness, Refusal accuracy (builds the measurement; quality fixes come in Sprint 3).

**Tasks**
- Create `eval/corpus/` with 5–10 small, license-safe documents spanning the supported types
  (a PDF, a DOCX, an XLSX, a CSV, a TXT). Include at least one scanned/image PDF to exercise OCR.
- Create `eval/golden.jsonl` — 40–60 labelled cases, each: `{question, mode, expected_doc_ids,
  expected_chunk_substrings, answer_must_contain, answer_must_not_contain, should_refuse}`.
  Cover: narrow lookups, enumeration/list questions, table/spreadsheet lookups, multi-doc questions,
  and **out-of-corpus** questions (for refusal).
- `eval/build_index.py` — ingests `eval/corpus/` into a dedicated `eval/eval.db` (never the prod db).
- `eval/retrieval_eval.py` — runs `get_rag_context` per case, computes **recall@k** and
  **MRR**; prints per-case and aggregate.
- `eval/faithfulness_eval.py` — runs the full `/api/chat` document path against the **live Ollama model**,
  then uses an LLM grader prompt (`eval/grader_prompt.txt`) to score each answer 0/1 on
  *grounded-in-evidence* and *answers-the-question*. Cache model outputs to `eval/.cache/` keyed by
  prompt hash so reruns are cheap and reproducible.
- `eval/refusal_eval.py` — verifies out-of-corpus questions hit the "Insufficient information" path.
- Wire all three into `eval/scorecard.py` (replace the SKIPPED stubs).

**Acceptance criteria**
- `python eval/build_index.py && python eval/retrieval_eval.py` prints recall@k and MRR numbers.
- `python eval/faithfulness_eval.py` runs end-to-end against live Ollama and prints a faithfulness %.
- Scorecard now shows **real numbers** for metrics 6–8 (pass or fail — fixing is Sprint 3).
- Eval is hermetic: uses `eval/eval.db`, leaves `rag_v2.db` untouched.

---

### Sprint 3 — RAG quality to ≥ 90 %
**Targets rubric:** Retrieval recall@k ≥ 90 %, Faithfulness ≥ 90 %, Refusal ≥ 90 %.

**Tasks** (drive each by the Sprint 2 harness; tune, re-measure, repeat)
- Triage retrieval misses from `retrieval_eval.py`. Likely levers in `app/config.py`:
  `VECTOR_WEIGHT`/`LEXICAL_WEIGHT`, `PER_DOC_CAP`, `DOCUMENT_MIN_USEFUL_SCORE`,
  the coverage drop thresholds, and enumeration caps. Adjust based on evidence, not guesswork —
  every change must move the recall number and not regress faithfulness.
- Triage faithfulness failures. Strengthen grounding prompts in `app/services/prompt_builder.py`
  (`build_grounded_prompt`) to forbid using outside knowledge and to cite evidence; verify the
  "insufficient information" instruction is unambiguous.
- Tighten refusal: confirm the empty-retrieval path (`main.py` document branch, `skip_llm=True`)
  and `DOCUMENT_MIN_USEFUL_SCORE` produce refusals for out-of-corpus questions without suppressing
  valid low-but-correct answers.
- Add regression tests in `tests/` that pin the won behaviors (e.g., a previously-missed golden case).

**Acceptance criteria**
- `retrieval_eval.py` recall@k ≥ 90 %; `faithfulness_eval.py` ≥ 90 %; `refusal_eval.py` ≥ 90 %.
- No regression in the existing `tests/` suite or in already-passing golden cases.
- Config changes documented in `ARCHITECTURE.md` (Sprint 8) with the before/after numbers.

---

### Sprint 4 — Confidence calibration
**Targets rubric:** Confidence calibration ≥ 90 % agreement.

**Tasks**
- `eval/confidence_eval.py` — for each golden case, compare the emitted confidence `label`
  (`compute_document_confidence`) against actual correctness from the faithfulness grader.
  Report agreement, plus a simple reliability table (high/medium/low × correct/incorrect).
- Tune the weights and thresholds in `app/services/confidence.py` / `app/config.py`
  (`CONFIDENCE_HIGH_THRESHOLD`, `CONFIDENCE_MEDIUM_THRESHOLD`, the score formula) so that
  `high` strongly predicts correct and `low` predicts refuse/incorrect.
- Add unit tests pinning the calibrated thresholds and the reason-code logic.

**Acceptance criteria**
- `confidence_eval.py` agreement ≥ 90 %; no `high` confidence on a hallucinated/refused answer.
- Calibration table included in the eval output and in `ARCHITECTURE.md`.

---

### Sprint 5 — Reliability, tooling & robustness
**Targets rubric:** Tool intent accuracy ≥ 90 %, Graceful-failure 100 %, plus a CI-safe mock-LLM path.

**Tasks**
- **Intent fixtures:** `eval/intents.jsonl` — labelled utterances for every RPA, Workspace, and
  WhatsApp intent (`detect_rpa_intent`, `detect_workspace_intent`) including near-miss negatives.
  `eval/intent_eval.py` computes routing accuracy and a confusion matrix.
- Fix misroutes surfaced by the eval (regex/keyword tuning in `tools/gobook_tools.py` /
  `tools/workspace_tools.py`). Add unit tests for fixed cases.
- **Graceful failure matrix:** `tests/test_api_robustness.py` — hit `/api/chat`, `/api/ingest`,
  `/api/rpa/*` with empty messages, oversized input, bad modes, missing fields, unsupported file types,
  no model selected. Assert structured responses and **no unhandled 500s**. Audit broad `except`
  blocks for ones that swallow errors silently.
- **Mock-LLM for CI:** add an `OLLAMA_FAKE`/injectable client so `eval/` and robustness tests can run
  deterministically without Ollama. Live runs stay the default locally; CI uses recorded/mock responses
  (reuse the Sprint 2 cache). This unblocks gating faithfulness-adjacent checks in CI.
- **Secrets handling:** `secrets.json` (username/password) is gitignored — good. Add `secrets.example.json`,
  document the schema, and ensure no credential ever lands in logs or the debug payload. Add a test that
  the debug trace contains no secret values.

**Acceptance criteria**
- `intent_eval.py` ≥ 90 % routing accuracy.
- Robustness suite passes; fuzz matrix yields 0 unhandled 500s.
- `eval/` and robustness tests runnable with mock LLM (no Ollama) and pass in CI.

---

### Sprint 6 — Coverage to ≥ 90 %
**Targets rubric:** Line coverage ≥ 90 % on `app/` and `rag/`.

**Tasks**
- Read the Sprint 0 coverage report; rank modules by uncovered lines. Likely thin spots:
  `rag/search.py` (511 lines), `rag/ingest.py` (573), `rag/spreadsheet_extractor.py`,
  `app/services/session_grounding.py`, the new `chat_orchestrator.py`.
- Add focused unit tests for branch-heavy logic (hybrid ranking, enumeration mode, coverage
  stabilization in `rag_service._apply_coverage_stabilization`, layout normalizer).
- Exclude unreachable/`__main__`/external-I/O lines explicitly via `[tool.coverage.run] omit` and
  `# pragma: no cover` with justification (Playwright launches, network calls) — do not pad.

**Acceptance criteria**
- `coverage report` for `app/` + `rag/` ≥ 90 % line coverage; CI enforces `--cov-fail-under=90`.

---

### Sprint 7 — Performance & final hardening
**Targets rubric:** Performance budget documented & met; final gate sweep.

**Tasks**
- `eval/perf_eval.py` — measure retrieval latency (cold/warm) and end-to-end `/api/chat` latency
  over the golden set; report p50/p95. Set a documented budget (e.g., retrieval p95 < 500 ms warm
  on the eval corpus — adjust to observed hardware) and flag regressions.
- Address any obvious hotspots only if measured (e.g., per-request DuckDB connection open/close in
  `rag_service.py` — consider a pooled/cached connection if it dominates).
- Run the **full scorecard** and close any metric still under target.

**Acceptance criteria**
- `perf_eval.py` reports p50/p95 and meets the documented budget (or the budget is revised with rationale).
- `python eval/scorecard.py` → **every gated metric ≥ target; exit 0.**

---

### Sprint 8 — Portfolio polish
**Targets rubric:** Docs present; demo-ready.

**Tasks**
- Rewrite `README.md`: what it is, the 3 modes, the architecture diagram, the metric scorecard
  (with the achieved numbers as a badge/table), setup, and how to run the eval.
- Add `ARCHITECTURE.md`: request lifecycle, RAG pipeline, confidence model, watcher, the eval
  methodology, and the config-tuning decisions from Sprints 3–4.
- Add a one-command demo: `demo/seed.py` ingests `eval/corpus/` and `demo/walkthrough.md` scripts a
  scripted chat/document/personal showcase. Capture 3–5 screenshots into `docs/img/`.
- Final repo hygiene: remove stray artifacts (`demo5.out.log`, `demo5.err.log`, `consolidated.txt`,
  duplicate `rag.db`/`test_ingest.db`/`test.pdf` if unused), confirm `.gitignore` covers
  `eval/.cache/`, `eval/eval.db`, `temp_uploads/`, `rag_uploads/`.

**Acceptance criteria**
- README shows the final scorecard with all metrics ≥ 90 %.
- `ARCHITECTURE.md` + demo script + screenshots present; a fresh clone can run setup → demo → eval
  by following the README only.

---

## 5. Dependency order & suggested sequencing

```
Sprint 0 (measurement) ─┬─> Sprint 1 (code quality)
                        ├─> Sprint 2 (eval harness) ──> Sprint 3 (RAG quality) ──> Sprint 4 (confidence)
                        └─> Sprint 5 (reliability/tooling) ─┐
Sprint 3/4/5 ──> Sprint 6 (coverage) ──> Sprint 7 (perf + final gate) ──> Sprint 8 (polish)
```

- **Sprint 0 is a hard prerequisite** for all others.
- Sprints 1 and 2 can run in parallel (different files).
- Do not declare done until `python eval/scorecard.py` exits 0 with every gated metric ≥ target.

## 6. Definition of done (the release gate)

A single command tells the whole story:

```bash
ruff check . && mypy app rag && pytest --cov=app --cov=rag --cov-fail-under=90 && python eval/scorecard.py
```

Ship when that command exits 0 and the scorecard prints **≥ 90 % on every gated metric**.
