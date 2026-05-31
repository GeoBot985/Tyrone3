from typing import TypedDict, Optional, List, Literal

class ChatRequestPayload(TypedDict):
    user_message: str
    selected_model: str
    rag_enabled: bool
    retrieval_query: Optional[str]
    retrieval_chunks: List[dict]
    retrieval_error: Optional[str]
    final_prompt: str

class RuleResult(TypedDict):
    rule_id: str
    description: str
    severity: Literal["info", "warning", "error"]
    passed: bool
    details: str

class WatcherResult(TypedDict):
    allowed: bool
    modified: bool
    payload: ChatRequestPayload
    watcher_notes: List[str]
    watcher_error: Optional[str]
    rule_results: List[RuleResult]

def evaluate_rules(payload: ChatRequestPayload) -> List[RuleResult]:
    """
    Runs deterministic rules on the request payload.
    May raise exceptions if logic fails.
    """
    results: List[RuleResult] = []

    # Rule 1: Empty Prompt Check
    final_prompt = payload.get("final_prompt", "")
    results.append({
        "rule_id": "PROMPT_EMPTY",
        "description": "Final prompt must not be empty",
        "severity": "error",
        "passed": bool(final_prompt.strip()),
        "details": "Prompt is empty" if not final_prompt.strip() else ""
    })

    # Rule 2: Prompt Length Warning
    threshold = 8000
    prompt_len = len(final_prompt)
    results.append({
        "rule_id": "PROMPT_TOO_LONG",
        "description": f"Prompt length should not exceed {threshold} characters",
        "severity": "warning",
        "passed": prompt_len <= threshold,
        "details": f"length={prompt_len} exceeds threshold={threshold}" if prompt_len > threshold else ""
    })

    # Rule 3: RAG Enabled but No Context
    rag_enabled = payload.get("rag_enabled", False)
    chunks = payload.get("retrieval_chunks", [])
    results.append({
        "rule_id": "RAG_EMPTY",
        "description": "RAG enabled but no context retrieved",
        "severity": "warning",
        "passed": not (rag_enabled and not chunks),
        "details": "RAG enabled but no chunks retrieved" if (rag_enabled and not chunks) else ""
    })

    # Rule 4: No Model Selected
    model = payload.get("selected_model")
    results.append({
        "rule_id": "MODEL_MISSING",
        "description": "A model must be selected",
        "severity": "error",
        "passed": bool(model),
        "details": "No model selected" if not model else ""
    })

    # Rule 5: Retrieval Error Present
    retrieval_error = payload.get("retrieval_error")
    results.append({
        "rule_id": "RETRIEVAL_ERROR",
        "description": "Retrieval process encountered an error",
        "severity": "warning",
        "passed": retrieval_error is None,
        "details": f"Error: {retrieval_error}" if retrieval_error else ""
    })

    # Rule 6: Suspiciously Short User Input
    user_input = payload.get("user_message", "")
    results.append({
        "rule_id": "USER_INPUT_TOO_SHORT",
        "description": "User input is very short",
        "severity": "info",
        "passed": len(user_input) >= 3,
        "details": f"length={len(user_input)} is less than 3" if len(user_input) < 3 else ""
    })

    return results

def inspect_chat_request(payload: ChatRequestPayload) -> WatcherResult:
    """
    Accepts a structured chat request payload and returns a pass-through WatcherResult
    with attached rule evaluation results.
    If it fails internally, it fails open.
    """
    watcher_notes = ["pass_through"]
    rule_results = []
    watcher_error = None

    try:
        rule_results = evaluate_rules(payload)
    except Exception as e:
        watcher_notes.append("rule_engine_failed")
        watcher_error = str(e)

    return {
        "allowed": True,
        "modified": False,
        "payload": payload,
        "watcher_notes": watcher_notes,
        "watcher_error": watcher_error,
        "rule_results": rule_results
    }
