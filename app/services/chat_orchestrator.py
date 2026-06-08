from __future__ import annotations

from typing import Any

from models import ChatRequest

# Personal-mode tools pull heavy optional deps (playwright, Google APIs). Personal
# mode is opt-in, so tolerate them being absent: chat/document deployments boot
# without these installed, and the personal branch guards before using them.
try:
    from tools.gobook_tools import (
        detect_rpa_intent,
        extract_rpa_details,
        rpa_book,
        rpa_cancel,
        rpa_list,
        rpa_open_courts,
    )
    from tools.workspace_tools import (
        detect_workspace_intent,
        dispatch_workspace_intent,
        extract_workspace_details,
    )

    PERSONAL_TOOLS_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised only without personal deps
    PERSONAL_TOOLS_AVAILABLE = False

from app.services.confidence import compute_document_confidence
from app.services.document_coverage import (
    detect_document_coverage_mode,
    explain_document_coverage_reason,
)
from app.services.personal_prompt_builder import build_personal_grounded_prompt
from app.services.personal_service import (
    AMBIGUITY_RESPONSE,
    NO_ENTITY_RESPONSE,
    NO_FACT_RESPONSE,
    persist_user_input,
    retrieve_personal_store_records,
)
from app.services.prompt_builder import (
    build_chat_with_document_prompt,
    build_grounded_prompt,
)
from app.services.rag_service import get_full_document_content, get_rag_context
from app.services.response_format import (
    detect_document_response_format,
    explain_document_response_format_rule,
)
from app.utils.token_utils import estimate_tokens


def _base_state() -> dict[str, Any]:
    return {
        "retrieval_query": None,
        "retrieval_chunks": [],
        "retrieval_metrics": None,
        "retrieval_error": None,
        "response_format_detected": None,
        "response_format_reason": None,
        "coverage_mode": None,
        "coverage_reason": None,
        "coverage_truncated": False,
        "final_prompt": "",
        "skip_llm": False,
        "reply_text": "",
        "confidence_payload": None,
        "personal_context": None,
        "personal_input_persisted": False,
        "personal_status": None,
        "personal_general_fallback_disabled": False,
        "personal_retrieval_metrics": None,
        "doc_data": None,
    }


async def prepare_mode_state(
    request: ChatRequest,
    session_id: str,
    rag_enabled: bool = True,
    get_rag_context_fn=get_rag_context,
) -> dict[str, Any]:
    state = _base_state()
    effective_mode = request.mode

    if effective_mode == "document":
        state["response_format_detected"] = detect_document_response_format(request.message)
        state["response_format_reason"] = explain_document_response_format_rule(request.message)
        state["coverage_mode"] = detect_document_coverage_mode(
            request.message,
            state["response_format_detected"],
        )
        state["coverage_reason"] = explain_document_coverage_reason(
            request.message,
            state["response_format_detected"],
        )
        if rag_enabled:
            rag_result = get_rag_context_fn(
                request.message,
                top_k=3,
                document_ids=request.document_ids,
                response_format=state["response_format_detected"],
            )
            state["retrieval_query"] = request.message
            state["retrieval_error"] = rag_result.get("error")
            state["retrieval_chunks"] = rag_result.get("chunks", [])
            state["retrieval_metrics"] = rag_result.get("metrics")
            prompt_chunks = rag_result.get("chunks_for_prompt", state["retrieval_chunks"])
            state["coverage_mode"] = (state["retrieval_metrics"] or {}).get(
                "coverage_mode",
                state["coverage_mode"],
            )
            state["coverage_truncated"] = bool(
                (state["retrieval_metrics"] or {}).get("coverage_truncated", False)
            )
            state["coverage_reason"] = (state["retrieval_metrics"] or {}).get(
                "coverage_reason",
                state["coverage_reason"],
            )

            if not state["retrieval_chunks"] and not state["retrieval_error"]:
                state["skip_llm"] = True
                state["reply_text"] = "Insufficient information"
                state["final_prompt"] = "No context provided."
                state["confidence_payload"] = compute_document_confidence(
                    chunks_used_for_prompt=[],
                    retrieval_metrics=state["retrieval_metrics"],
                    retrieval_error=state["retrieval_error"],
                    coverage_mode=state["coverage_mode"] or "narrow_lookup",
                    coverage_truncated=state["coverage_truncated"],
                    skip_llm=True,
                )
            elif state["retrieval_chunks"]:
                context_text = "\n".join([c.get("text", "") for c in prompt_chunks])
                state["context_tokens"] = estimate_tokens(context_text)
                state["final_prompt"] = build_grounded_prompt(
                    request.message,
                    prompt_chunks,
                    response_format=state["response_format_detected"],
                    retrieval_mode=(state["retrieval_metrics"] or {}).get(
                        "retrieval_mode", "default"
                    ),
                    coverage_mode=state["coverage_mode"] or "narrow_lookup",
                    coverage_truncated=state["coverage_truncated"],
                )
                state["confidence_payload"] = compute_document_confidence(
                    chunks_used_for_prompt=prompt_chunks,
                    retrieval_metrics=state["retrieval_metrics"],
                    retrieval_error=state["retrieval_error"],
                    coverage_mode=state["coverage_mode"] or "narrow_lookup",
                    coverage_truncated=state["coverage_truncated"],
                    skip_llm=False,
                )

    elif effective_mode == "personal":
        if not PERSONAL_TOOLS_AVAILABLE:
            raise RuntimeError(
                "Personal mode is enabled but its dependencies (playwright, Google APIs) "
                "are not installed."
            )
        rpa_intent = detect_rpa_intent(request.message)
        if rpa_intent:
            try:
                state["skip_llm"] = True
                state["personal_general_fallback_disabled"] = True
                state["personal_status"] = f"rpa_{rpa_intent}"
                rpa_details = extract_rpa_details(request.message)
                request_date = rpa_details["date"]
                times = rpa_details["times"]
                court_value = rpa_details["court"]

                if rpa_intent == "list":
                    result = await rpa_list(100)
                    state["reply_text"] = (
                        "\n".join(result) if result else "No active upcoming bookings."
                    )
                elif rpa_intent == "open_courts":
                    open_start_time = rpa_details["start"]
                    open_end_time = rpa_details["end"]
                    if not request_date or not open_start_time or not open_end_time:
                        raise RuntimeError(
                            "Open courts needs a date and a time range, for example 16:30-18:00 or between 16:30 and 18:00."
                        )
                    courts = await rpa_open_courts(
                        request_date, open_start_time, open_end_time, 100
                    )
                    state["reply_text"] = "\n".join(courts) if courts else "No open courts found."
                elif rpa_intent == "book":
                    if not request_date or len(times) < 1:
                        raise RuntimeError("Booking requests need a date and time.")
                    time_value = (
                        f"{rpa_details['start']}-{rpa_details['end']}"
                        if rpa_details["start"] and rpa_details["end"]
                        else times[0]
                    )
                    result = await rpa_book(request_date, time_value, court_value, True, 100)
                    state["reply_text"] = f"Booking submitted: {result.get('selection', 'unknown')}"
                else:
                    if not request_date or len(times) < 1:
                        raise RuntimeError("Cancel requests need a date and time.")
                    result = await rpa_cancel(request_date, times[0], court_value, True, 100)
                    if not result.get("ok", True):
                        raise RuntimeError(result.get("error") or "Cancel request failed.")
                    state["reply_text"] = "Cancellation submitted."
                state["personal_context"] = {"resolved_entities": [], "memories": []}
            except Exception as exc:
                state["reply_text"] = f"RPA request failed: {exc}"
                state["skip_llm"] = True
                state["personal_context"] = {"resolved_entities": [], "memories": []}
        else:
            workspace_intent = detect_workspace_intent(request.message)
            if workspace_intent:
                try:
                    state["skip_llm"] = True
                    state["personal_general_fallback_disabled"] = True
                    state["personal_status"] = f"workspace_{workspace_intent}"
                    details = extract_workspace_details(request.message)
                    state["reply_text"] = await dispatch_workspace_intent(
                        workspace_intent,
                        request.message,
                        details,
                        request.model,
                    )
                    state["personal_context"] = {"resolved_entities": [], "memories": []}
                except Exception as exc:
                    state["reply_text"] = f"Workspace request failed: {exc}"
                    state["skip_llm"] = True
                    state["personal_context"] = {"resolved_entities": [], "memories": []}
            else:
                persist_user_input(request.message, session_id=session_id)
                state["personal_input_persisted"] = True
                state["personal_general_fallback_disabled"] = True
                personal_result = retrieve_personal_store_records(request.message)
                state["personal_status"] = personal_result["status"]
                state["personal_retrieval_metrics"] = personal_result.get("metrics")
                state["personal_context"] = {
                    "resolved_entities": personal_result["resolved_entities"],
                    "memories": personal_result["memories"],
                }

                if state["personal_status"] == "ambiguous":
                    state["reply_text"] = AMBIGUITY_RESPONSE
                    state["skip_llm"] = True
                    state["final_prompt"] = (
                        "Personal mode store retrieval was ambiguous. No LLM prompt generated."
                    )
                elif state["personal_status"] == "no_fact":
                    state["reply_text"] = NO_FACT_RESPONSE
                    state["skip_llm"] = True
                    state["final_prompt"] = (
                        "Personal mode store retrieval found an entity but no supporting records. No LLM prompt generated."
                    )
                elif state["personal_status"] == "no_entity":
                    state["reply_text"] = NO_ENTITY_RESPONSE
                    state["skip_llm"] = True
                    state["final_prompt"] = (
                        "Personal mode store retrieval found no matching records. No LLM prompt generated."
                    )
                else:
                    context_text = "\n".join(
                        [m.get("raw_user_input", "") for m in state["personal_context"]["memories"]]
                    )
                    state["context_tokens"] = estimate_tokens(context_text)
                    state["final_prompt"] = build_personal_grounded_prompt(
                        request.message,
                        state["personal_context"]["resolved_entities"],
                        state["personal_context"]["memories"],
                    )

    else:
        if request.chat_document_id:
            doc_data = get_full_document_content(request.chat_document_id)
            state["doc_data"] = doc_data
            if doc_data.get("error"):
                state["skip_llm"] = True
                state["reply_text"] = f"Error: {doc_data['error']}"
                state["final_prompt"] = f"Failed to load document {request.chat_document_id}"
            else:
                state["context_tokens"] = estimate_tokens(doc_data.get("full_text", ""))
                state["final_prompt"] = build_chat_with_document_prompt(
                    request.message,
                    doc_data["document_name"],
                    doc_data["full_text"],
                )
        else:
            state["final_prompt"] = request.message

    return state
