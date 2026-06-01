# Why I Built Tyrone 3.0 Local-First

## The thesis

Most "AI assistant" projects are thin wrappers over a hosted API. The moment a user pastes a
contract, a medical record, or an internal policy into that box, the data leaves the building —
it transits a third party, may be retained, logged, or used for training, and crosses a
jurisdictional boundary. For a large and growing set of organisations, **that single fact
disqualifies cloud LLMs outright.**

Tyrone 3.0 is built for those environments. The design constraint came first: *the document and the
reasoning over it must never leave the machine.* Everything else followed from that.

## What "local-first" actually means here

- **Inference runs on-device.** The LLM is served by [Ollama](https://ollama.com/) on
  `localhost:11434`. Prompts, retrieved context, and generated answers never touch a remote model
  provider. No API key, no egress, no per-token metering.
- **The knowledge base is a local file.** Ingested documents are chunked, embedded, and stored in a
  local DuckDB database (`rag_v2.db`). Retrieval (`search.py`) runs in-process against that file.
  There is no vector-database SaaS in the loop.
- **It runs fully air-gapped.** Pull a model once, and the Chat and Document modes operate with the
  network cable unplugged. That is the litmus test for a true compliance-grade engine.

## Why this matters for high-compliance environments

| Risk with cloud LLMs | How local-first removes it |
|---|---|
| Sensitive data leaves your jurisdiction | Documents and prompts stay on the host — nothing is transmitted |
| Provider retention / training on your data | There is no provider; nothing is retained off-box |
| Vendor outage takes your assistant down | No external dependency for the core loop — it runs offline |
| Per-token cost scales with usage | Inference is a fixed local resource, not a metered API |
| "Trust us" data handling | **Auditable by construction** — every answer ships provenance metadata |

Legal, healthcare, finance, defence, and public-sector teams routinely operate under rules
(POPIA, GDPR, HIPAA, attorney–client privilege, data-residency mandates) where "the data was sent to
a US cloud LLM" is not a footnote — it is a breach. Local-first is not a performance optimisation
here. It is the entire point.

## Auditability is a feature, not an afterthought

Privacy alone isn't enough for regulated work — you also have to *show your work*. Every Tyrone
response carries deterministic metadata layers (see `docs/architecture_diagram.md`):

- **Evidence** — the exact retrieved chunks, with document IDs and scores, behind every grounded answer.
- **Confidence** — a calibrated score with reason codes, so a low-confidence answer is flagged, not hidden.
- **Refusal by default** — when retrieval finds nothing relevant, the engine returns
  *"Insufficient information"* instead of hallucinating. This is measured (`refusal_accuracy`) and gated.
- **Watcher guardrails** — a deterministic rule engine inspects every request and attaches pass/fail
  results, independent of the probabilistic model.
- **Full debug trace** — the complete request lineage, suitable for replay and audit.

A reviewer can answer "*where did this answer come from, and how sure was the system?*" from the
response itself — no vendor cooperation required.

## The honest boundary

I scoped the privacy claim precisely, because over-claiming is its own red flag:

- **Chat and Document modes are fully local.** This is the compliance-grade core.
- **Personal mode includes opt-in external integrations** (Google Workspace, WhatsApp Web, the GoBook
  court-booking RPA). These *intentionally* talk to third-party services — that is their job. They are
  explicit, user-invoked actions, isolated from the document-reasoning core, and never required for
  the local RAG pipeline to function.

The promise is therefore exact: **your documents and the reasoning over them stay on your machine.**
The integrations that reach outside do so only when you explicitly ask them to, and only for the
external service they name.

## Why this is the portfolio story

This project demonstrates a judgement that matters more than wiring up an API: **I started from a
real-world constraint (data must not leave the premises) and engineered a complete, measured system
around it** — local inference, local retrieval, deterministic guardrails, calibrated confidence, and
a quality scorecard that proves the claims rather than asserting them.
