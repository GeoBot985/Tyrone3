# Tyrone 3.0 — Request Lifecycle (Architecture Block Diagram)

This is the end-to-end lifecycle of a single chat request as it enters `main.py`, is routed
through `chat_orchestrator.py`, queries `search.py`, passes the deterministic `watcher.py`
guardrails, and returns a payload with **attached deterministic metadata layers** (retrieval
metrics, confidence, watcher rule results, token usage).

> The diagrams below are [Mermaid](https://mermaid.js.org/). They render natively on GitHub,
> in VS Code (Markdown Preview Mermaid Support), and in most portfolio site generators.

---

## 1. Sequence diagram — the full request lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Web UI<br/>(static/app.js)
    participant API as FastAPI<br/>(main.py /api/chat)
    participant Orch as Orchestrator<br/>(chat_orchestrator.py)
    participant RAG as RAG Service<br/>(rag_service.py)
    participant Search as Hybrid Search<br/>(search.py)
    participant DB as DuckDB Corpus<br/>(rag_v2.db)
    participant Watch as Watcher<br/>(watcher.py)
    participant LLM as Ollama<br/>(local LLM)

    User->>UI: Type message, pick mode + model
    UI->>API: POST /api/chat {message, mode, model, document_ids}
    API->>API: Build TurnContext + estimate input tokens
    API->>Orch: route by mode (chat / document / personal)

    rect rgb(235, 245, 255)
    note over Orch,DB: DOCUMENT MODE — grounded retrieval
    Orch->>RAG: get_rag_context(query, top_k, document_ids)
    RAG->>Search: hybrid search (vector 0.7 + lexical 0.3)
    Search->>DB: candidate pool + per-doc caps
    DB-->>Search: candidate chunks
    Search-->>RAG: ranked chunks + retrieval metrics
    RAG->>RAG: verify chunks, coverage stabilization, compaction
    RAG-->>Orch: chunks_for_prompt + metrics (metadata layer 1)
    Orch->>Orch: build_grounded_prompt(...) OR refuse if empty
    end

    Orch-->>API: final_prompt + retrieval state

    rect rgb(245, 240, 255)
    note over API,Watch: DETERMINISTIC GUARDRAILS (fail-open)
    API->>Watch: inspect_chat_request(payload)
    Watch->>Watch: run rule engine (empty prompt, length,<br/>RAG-empty, model missing, retrieval error)
    Watch-->>API: rule_results + notes (metadata layer 2)
    end

    alt skip_llm (refusal / tool short-circuit)
        API->>API: use deterministic reply_text
    else call model
        API->>LLM: chat(model, final_prompt, temperature=0.1)
        LLM-->>API: generated answer
    end

    rect rgb(240, 255, 240)
    note over API: ASSEMBLE METADATA LAYERS
    API->>API: compute_document_confidence(...)  (layer 3)
    API->>API: token usage + session grounding   (layer 4)
    API->>API: build structured debug trace       (layer 5)
    end

    API-->>UI: ChatResponse {reply, evidence, confidence,<br/>debug, token_usage}
    UI-->>User: Render answer + evidence + confidence + debug panel
```

---

## 2. Mode routing (what the orchestrator decides)

```mermaid
flowchart TD
    A[POST /api/chat] --> B{mode?}

    B -->|document| C[RAG retrieval<br/>rag_service → search.py]
    C --> C1{chunks found?}
    C1 -->|no| C2[Refuse:<br/>'Insufficient information']
    C1 -->|yes| C3[build_grounded_prompt]

    B -->|personal| D{intent?}
    D -->|RPA| D1[GoBook court automation<br/>tools/gobook_tools.py]
    D -->|workspace| D2[Gmail / Calendar / Sheets / WhatsApp<br/>tools/workspace_tools.py]
    D -->|memory| D3[Personal store retrieval<br/>personal_service.py]

    B -->|chat| E{chat_document_id?}
    E -->|yes| E1[Ground on one full document]
    E -->|no| E2[Plain LLM chat]

    C2 --> W[Watcher rule engine<br/>watcher.py]
    C3 --> W
    D1 --> W
    D2 --> W
    D3 --> W
    E1 --> W
    E2 --> W

    W --> F{skip_llm?}
    F -->|yes| G[Deterministic reply]
    F -->|no| H[Ollama generation]
    G --> P[Assemble payload +<br/>metadata layers]
    H --> P
    P --> R[ChatResponse]
```

---

## 3. The deterministic metadata layers (the portfolio differentiator)

Every response carries machine-readable provenance, not just prose. This is what makes the engine
auditable — a key selling point for high-compliance use.

| Layer | Produced by | What it proves |
|---|---|---|
| **1. Retrieval metrics** | `rag_service.get_rag_context` | which chunks, scores, coverage mode, verification status |
| **2. Watcher rule results** | `watcher.inspect_chat_request` | deterministic guardrail checks (pass/fail, severity) |
| **3. Confidence** | `confidence.compute_document_confidence` | calibrated score + reason codes for the answer |
| **4. Token / session usage** | `token_utils` + `session_grounding` | per-turn and per-session cost accounting |
| **5. Debug trace** | `main.py` assembly | full request lineage for audit / replay |
