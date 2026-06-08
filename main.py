from __future__ import annotations

import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from app.config import (
    STATIC_DIR,
    SUPPORTED_UPLOAD_TYPES_DISPLAY,
    TEMP_UPLOADS_DIR,
    TEMPLATES_DIR,
    personal_mode_enabled,
)
from app.services.chat_orchestrator import prepare_mode_state
from app.services.ingest_service import ingest_file
from app.services.personal_service import initialize_personal_service
from app.services.rag_service import (
    clear_corpus_service,
    delete_document_service,
    get_corpus_stats_service,
    get_rag_context,
    list_indexed_documents,
)
from app.services.session_grounding import (
    build_session_grounding,
    get_session_grounding,
    increment_session_usage,
)
from app.services.watcher import ChatRequestPayload, inspect_chat_request
from app.utils.token_utils import estimate_tokens
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from models import ChatRequest, ChatResponse, RPARequest, RPAResponse, TokenUsage, TurnContext
from ollama_client import chat as ollama_chat
from ollama_client import get_models
from rag.ingest import is_supported_upload_extension
from tools.gobook_tools import rpa_book, rpa_cancel, rpa_list, rpa_open_courts
from watcher import PassiveWatcher

RAG_ENABLED = True
WATCHER_ENABLED = True
BASE_CHAT_MODES = {"chat", "document"}


def valid_chat_modes() -> set[str]:
    """Modes accepted by /api/chat; personal is opt-in via TYRONE_ENABLE_PERSONAL."""
    modes = set(BASE_CHAT_MODES)
    if personal_mode_enabled():
        modes.add("personal")
    return modes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await build_session_grounding()
    yield


app = FastAPI(title="Tyrone 3.0", lifespan=lifespan)

initialize_personal_service()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
watcher = PassiveWatcher()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"personal_enabled": personal_mode_enabled()},
    )


@app.get("/api/grounding")
async def api_grounding():
    return get_session_grounding()


@app.post("/api/ingest")
async def api_ingest(file: UploadFile = File(...)):
    temp_dir = TEMP_UPLOADS_DIR
    os.makedirs(temp_dir, exist_ok=True)

    filename = file.filename or "upload.pdf"
    safe_name = os.path.basename(filename)
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")

    ext = os.path.splitext(safe_name)[1].lower()
    if not is_supported_upload_extension(ext):
        return JSONResponse(
            content={
                "ok": False,
                "status": "failed",
                "error": f"Unsupported file type. Supported types: {SUPPORTED_UPLOAD_TYPES_DISPLAY}",
            }
        )

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ingest_file(temp_path, document_name=safe_name)
    finally:
        await file.close()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return JSONResponse(content=result)


@app.get("/api/docs")
async def api_docs():
    return list_indexed_documents()


@app.delete("/api/docs/{document_id}")
async def api_delete_doc(document_id: str):
    return delete_document_service(document_id)


@app.post("/api/docs/clear")
async def api_clear_corpus():
    return clear_corpus_service()


@app.post("/api/session/reset")
async def api_reset_session():
    await build_session_grounding()
    return {"ok": True}


@app.get("/api/stats")
async def api_stats():
    return get_corpus_stats_service()


@app.get("/api/models")
async def api_models():
    models, error = await get_models()
    if error:
        return JSONResponse(content={"models": [], "error": error}, status_code=200)
    return {"models": models}


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: ChatRequest):
    start_time = time.time()
    if request.mode == "personal" and not personal_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Personal mode is not enabled. Set TYRONE_ENABLE_PERSONAL=1 to use it.",
        )
    if request.mode not in valid_chat_modes():
        raise HTTPException(status_code=422, detail="Invalid mode. Use chat or document.")
    context = TurnContext(
        model=request.model,
        user_message=request.message,
        request_started_at=datetime.now(UTC).isoformat(),
    )
    user_input_tokens = estimate_tokens(request.message)
    context_tokens = 0
    watcher.pre_check(context)

    mode_state = await prepare_mode_state(
        request,
        session_id=context.session_id,
        rag_enabled=RAG_ENABLED,
        get_rag_context_fn=get_rag_context,
    )
    effective_mode = request.mode
    retrieval_query = mode_state["retrieval_query"]
    retrieval_chunks = mode_state["retrieval_chunks"]
    retrieval_metrics = mode_state["retrieval_metrics"]
    retrieval_error = mode_state["retrieval_error"]
    response_format_detected = mode_state["response_format_detected"]
    response_format_reason = mode_state["response_format_reason"]
    coverage_mode = mode_state["coverage_mode"]
    coverage_reason = mode_state["coverage_reason"]
    coverage_truncated = mode_state["coverage_truncated"]
    final_prompt = mode_state["final_prompt"] or request.message
    skip_llm = mode_state["skip_llm"]
    reply_text = mode_state["reply_text"]
    confidence_payload = mode_state["confidence_payload"]
    personal_context = mode_state["personal_context"]
    personal_input_persisted = mode_state["personal_input_persisted"]
    personal_status = mode_state["personal_status"]
    personal_retrieval_metrics = mode_state["personal_retrieval_metrics"]
    doc_data = mode_state["doc_data"]

    if mode_state.get("context_tokens") is not None:
        context_tokens = mode_state["context_tokens"]

    watcher_allowed = None
    watcher_modified = None
    watcher_notes: list[str] = []
    watcher_error = None
    watcher_rule_results: list[dict] = []

    if WATCHER_ENABLED:
        payload: ChatRequestPayload = {
            "user_message": request.message,
            "selected_model": request.model,
            "rag_enabled": RAG_ENABLED,
            "retrieval_query": retrieval_query,
            "retrieval_chunks": retrieval_chunks,
            "retrieval_error": retrieval_error,
            "final_prompt": final_prompt,
        }
        watcher_result = inspect_chat_request(payload)
        watcher_allowed = watcher_result.get("allowed")
        watcher_modified = watcher_result.get("modified")
        watcher_notes = watcher_result.get("watcher_notes", [])
        watcher_error = watcher_result.get("watcher_error")
        watcher_rule_results = watcher_result.get("rule_results", [])
        final_prompt = watcher_result.get("payload", payload).get("final_prompt", final_prompt)

    prompt_tokens = estimate_tokens(final_prompt)
    response_tokens = 0

    if not skip_llm:
        ollama_response, request_summary, error = await ollama_chat(
            request.model, final_prompt, temperature=0.1
        )
        context.ollama_request_summary = request_summary
        if error:
            context.error = error
            if effective_mode == "document" and (
                not confidence_payload or confidence_payload.get("label") in {"low", "medium"}
            ):
                from app.services.confidence import build_refusal_confidence

                reply_text = "Insufficient information"
                confidence_payload = build_refusal_confidence(
                    coverage_mode=coverage_mode or "narrow_lookup",
                    coverage_truncated=coverage_truncated,
                    reason="ollama_error_refusal_fallback",
                )
            else:
                reply_text = f"Error: {error}"
        else:
            context.ollama_response_summary = {
                "model": ollama_response.get("model"),
                "created_at": ollama_response.get("created_at"),
                "done": ollama_response.get("done"),
                "total_duration": ollama_response.get("total_duration"),
            }
            reply_text = ollama_response.get("message", {}).get("content", "")
            response_tokens = estimate_tokens(reply_text)
    else:
        response_tokens = estimate_tokens(reply_text)

    if effective_mode == "document" and reply_text.strip().lower().startswith(
        "insufficient information"
    ):
        from app.services.confidence import build_refusal_confidence

        confidence_payload = build_refusal_confidence(
            coverage_mode=coverage_mode or "narrow_lookup",
            coverage_truncated=coverage_truncated,
        )

    increment_session_usage(prompt_tokens, response_tokens)
    session_grounding = get_session_grounding() or {
        "session_turn_count": 1,
        "session_prompt_tokens_est": prompt_tokens,
        "session_response_tokens_est": response_tokens,
        "session_total_tokens_est": prompt_tokens + response_tokens,
    }

    watcher.post_check(context)
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    response_preview = (
        reply_text[:100] + ("..." if len(reply_text) > 100 else "") if reply_text else None
    )

    retrieval_scope = "full_corpus"
    selected_documents_count = 0
    selected_documents_names: list[str] = []
    if effective_mode == "chat" and request.chat_document_id:
        retrieval_scope = "single_document_grounding"
        selected_documents_count = 1
        selected_documents_names = (
            [doc_data.get("document_name", request.chat_document_id)]
            if doc_data
            else [request.chat_document_id]
        )
    elif request.document_ids:
        retrieval_scope = "working_set"
        selected_documents_count = len(request.document_ids)
        id_to_name = {
            chunk["document_id"]: chunk["document_name"]
            for chunk in retrieval_chunks
            if chunk.get("document_id") and chunk.get("document_name")
        }
        selected_documents_names = [
            id_to_name.get(doc_id, doc_id) for doc_id in request.document_ids
        ]

    debug_payload = {
        "grounding": get_session_grounding(),
        "user_message": request.message,
        "selected_model": request.model,
        "mode": effective_mode,
        "rag_enabled": RAG_ENABLED,
        "retrieval_scope": retrieval_scope,
        "selected_documents_count": selected_documents_count,
        "selected_documents_names": selected_documents_names,
        "retrieval_query": retrieval_query,
        "retrieval_chunks": retrieval_chunks,
        "retrieval_metrics": retrieval_metrics,
        "retrieval_error": retrieval_error,
        "response_format_detected": response_format_detected
        if effective_mode == "document"
        else None,
        "response_format_rules_applied": effective_mode == "document",
        "response_format_reason": response_format_reason if effective_mode == "document" else None,
        "coverage_mode": coverage_mode if effective_mode == "document" else None,
        "coverage_required": coverage_mode == "coverage_required"
        if effective_mode == "document"
        else False,
        "retrieval_top_k_requested": (retrieval_metrics or {}).get("retrieval_top_k_requested")
        if effective_mode == "document"
        else None,
        "retrieval_verified_chunks_count": (retrieval_metrics or {}).get(
            "retrieval_verified_chunks_count"
        )
        if effective_mode == "document"
        else None,
        "retrieval_chunks_used_for_prompt": (retrieval_metrics or {}).get(
            "retrieval_chunks_used_for_prompt"
        )
        if effective_mode == "document"
        else None,
        "coverage_truncated": coverage_truncated if effective_mode == "document" else False,
        "coverage_reason": coverage_reason if effective_mode == "document" else None,
        "personal_input_persisted": personal_input_persisted,
        "personal_status": personal_status,
        "personal_context": personal_context,
        "personal_records_retrieved_count": len(personal_context["memories"])
        if personal_context
        else 0,
        "personal_retrieval_metrics": personal_retrieval_metrics,
        "personal_general_knowledge_fallback": "disabled"
        if effective_mode == "personal"
        else "n/a",
        "watcher_enabled": WATCHER_ENABLED,
        "watcher_allowed": watcher_allowed,
        "watcher_modified": watcher_modified,
        "watcher_notes": watcher_notes,
        "watcher_error": watcher_error,
        "watcher_rule_results": watcher_rule_results,
        "final_prompt": final_prompt,
        "ollama_error": context.error,
        "response_preview": response_preview,
        "elapsed_ms": elapsed_ms,
    }

    if effective_mode == "document":
        if confidence_payload is None:
            from app.services.confidence import compute_document_confidence

            confidence_payload = compute_document_confidence(
                chunks_used_for_prompt=retrieval_chunks,
                retrieval_metrics=retrieval_metrics,
                retrieval_error=retrieval_error,
                coverage_mode=coverage_mode or "narrow_lookup",
                coverage_truncated=coverage_truncated,
                skip_llm=skip_llm,
            )
        if confidence_payload:
            debug_payload["confidence_reason_codes"] = confidence_payload.get("reason_codes", [])

    token_usage = TokenUsage(
        mode=effective_mode,
        user_input_tokens_est=user_input_tokens,
        context_tokens_est=context_tokens,
        prompt_tokens_est=prompt_tokens,
        response_tokens_est=response_tokens,
        turn_total_tokens_est=prompt_tokens + response_tokens,
        session_turn_count=session_grounding.get("session_turn_count", 1),
        session_prompt_tokens_est=session_grounding.get("session_prompt_tokens_est", prompt_tokens),
        session_response_tokens_est=session_grounding.get(
            "session_response_tokens_est", response_tokens
        ),
        session_total_tokens_est=session_grounding.get(
            "session_total_tokens_est", prompt_tokens + response_tokens
        ),
    )

    return ChatResponse(
        reply=reply_text,
        evidence=retrieval_chunks if effective_mode == "document" else None,
        confidence=confidence_payload if effective_mode == "document" else None,
        debug=debug_payload,
        token_usage=token_usage,
    )


def _ensure_personal_mode(mode: str):
    if not personal_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Personal mode is not enabled. Set TYRONE_ENABLE_PERSONAL=1 to use it.",
        )
    if mode != "personal":
        raise HTTPException(
            status_code=403, detail="These tools are only available in Personal Mode."
        )


@app.post("/api/rpa/book", response_model=RPAResponse)
async def api_rpa_book(request: RPARequest):
    _ensure_personal_mode(request.mode)
    if not request.date or not request.time:
        return RPAResponse(ok=False, action="book", error="date and time are required.")
    try:
        result = await rpa_book(
            request.date, request.time, request.court or "Court 1", request.confirm, request.slowmo
        )
        return RPAResponse(ok=True, action="book", result=result)
    except Exception as exc:
        return RPAResponse(ok=False, action="book", error=str(exc))


@app.post("/api/rpa/cancel", response_model=RPAResponse)
async def api_rpa_cancel(request: RPARequest):
    _ensure_personal_mode(request.mode)
    if not request.date or not request.time:
        return RPAResponse(ok=False, action="cancel", error="date and time are required.")
    try:
        result = await rpa_cancel(
            request.date, request.time, request.court or "Court 1", request.confirm, request.slowmo
        )
        return RPAResponse(ok=True, action="cancel", result=result)
    except Exception as exc:
        return RPAResponse(ok=False, action="cancel", error=str(exc))


@app.post("/api/rpa/list", response_model=RPAResponse)
async def api_rpa_list(request: RPARequest):
    _ensure_personal_mode(request.mode)
    try:
        bookings = await rpa_list(request.slowmo)
        return RPAResponse(ok=True, action="list", result={"bookings": bookings})
    except Exception as exc:
        return RPAResponse(ok=False, action="list", error=str(exc))


@app.post("/api/rpa/open-courts", response_model=RPAResponse)
async def api_rpa_open_courts(request: RPARequest):
    _ensure_personal_mode(request.mode)
    if not request.date or not request.start or not request.end:
        return RPAResponse(
            ok=False, action="open_courts", error="date, start, and end are required."
        )
    try:
        results = await rpa_open_courts(request.date, request.start, request.end, request.slowmo)
        return RPAResponse(ok=True, action="open_courts", result={"courts": results})
    except Exception as exc:
        return RPAResponse(ok=False, action="open_courts", error=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
