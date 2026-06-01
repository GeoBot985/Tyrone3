# Architecture

Tyrone 3.0 is a local-first assistant with a FastAPI backend, a browser UI, a DuckDB-backed RAG
store, and a lightweight watcher that inspects every chat request before the model runs.

## Request Lifecycle

1. The browser posts a `ChatRequest` to `POST /api/chat`.
2. `main.py` builds a `TurnContext`, estimates user input tokens, and runs the watcher pre-check.
3. `app/services/chat_orchestrator.py` prepares mode-specific state.
4. The selected mode routes into one of three paths:
   - `chat`: direct prompt, or document-grounded chat when `chat_document_id` is set
   - `document`: hybrid RAG retrieval, evidence compaction, confidence scoring, and Ollama answer generation
   - `personal`: memory retrieval, RPA intent routing, workspace intent routing, or a general personal prompt
5. The watcher inspects the assembled payload and can annotate or modify the final prompt.
6. If LLM generation is required, `ollama_client.chat()` executes the request.
7. `main.py` assembles reply text, evidence, confidence, token accounting, and debug output.

The important design choice is that the mode logic is split out of `main.py` so the route stays
thin and the behavior is testable in isolation.

## RAG Pipeline

### Ingestion

`rag/ingest.py` and the service layer accept PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, and MD files.
The ingestion path:

- extracts text with format-specific extractors
- applies OCR when the PDF text threshold indicates the page is image-heavy
- normalizes layout and spreadsheet content
- chunks the resulting text
- stores documents and embeddings in DuckDB

### Retrieval

`app/services/rag_service.py` uses `rag/search.py` for hybrid retrieval:

- vector score weight: `0.7`
- lexical score weight: `0.3`
- per-document caps and candidate pool limits are tuned separately for narrow lookup, single-doc,
  and enumeration-style queries
- document coverage mode applies stabilization so a high-score tail does not bloat the prompt

After retrieval, the service:

- verifies chunks against the database
- compacts duplicate lines and table-like content
- truncates or refuses if the evidence is too weak

### Refusal Behavior

If document-mode retrieval returns no verified chunks, the orchestrator returns
`Insufficient information` without calling the model. That keeps out-of-corpus behavior
deterministic and makes the refusal metric measurable.

## Confidence Model

`app/services/confidence.py` converts retrieval quality into a user-visible label:

- `high` if score >= `0.45`
- `medium` if score >= `0.25`
- `low` otherwise

The score uses:

- average retrieval score
- evidence count
- lexical strength
- penalties for single-chunk evidence, weak tails, truncated coverage, and retrieval failures

The refusal path uses a dedicated low-confidence payload so it does not masquerade as a strong
answer.

## Watcher

The watcher is currently a pass-through rule engine. It exists to make request inspection explicit
and to leave a clean hook for future policy enforcement. The payload it sees includes:

- user message
- selected model
- RAG enabled state
- retrieval query
- retrieval chunks
- final prompt

Even though it is pass-through today, the code path is useful because it keeps prompt assembly and
policy inspection separate.

## Eval Methodology

The evaluation stack lives under `eval/` and is deliberately isolated from the production database.

### Corpus and goldens

- `eval/build_corpus.py` generates a small synthetic corpus across TXT, DOCX, CSV, XLSX, and PDF.
- `eval/golden.jsonl` contains labeled retrieval, faithfulness, refusal, confidence, and intent
  cases.
- `eval/build_index.py` populates `eval/eval.db` only.

### Metrics

- `eval/retrieval_eval.py` measures recall@k and MRR from the golden set.
- `eval/faithfulness_eval.py` runs document-mode chat and uses a grader prompt to score grounded
  answers.
- `eval/refusal_eval.py` checks that out-of-corpus questions hit the refusal path.
- `eval/confidence_eval.py` compares confidence labels against correctness.
- `eval/intent_eval.py` checks tool and intent routing.
- `eval/perf_eval.py` measures cold/warm retrieval and chat latency.
- `eval/scorecard.py` runs the full gate table.

The eval cache is keyed by prompt hash so repeat runs are cheap and reproducible.

## Config Tuning Decisions

The key tuning choices made during Sprints 3-4 were:

- `VECTOR_WEIGHT = 0.7`, `LEXICAL_WEIGHT = 0.3`
- `DOCUMENT_MIN_USEFUL_SCORE = 0.18`
- `CONFIDENCE_HIGH_THRESHOLD = 0.45`
- `CONFIDENCE_MEDIUM_THRESHOLD = 0.25`

Why those values:

- retrieval was already strong on the synthetic corpus, so the main goal was preserving recall
  while preventing weak or truncated evidence from being treated as confident
- document-mode refusals should be deterministic when retrieval finds nothing useful
- confidence labels should map cleanly onto actual correctness, especially for refusal cases

The latest measured confidence table was:

- `high`: 14 correct, 0 incorrect
- `low`: 0 correct, 8 incorrect

The latest measured retrieval and chat warm p95 values were:

- retrieval: 44.7 ms
- chat: 31.3 ms

## Operational Notes

- `OLLAMA_FAKE=1` enables deterministic demo and CI mode.
- `secrets.json` is gitignored and should only hold the GoBook username/password schema.
- Generated eval/runtime artifacts stay out of version control via `.gitignore`.
