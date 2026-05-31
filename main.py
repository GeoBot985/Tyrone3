from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta
import re
import time
import os
import shutil
import uuid
import re
from zoneinfo import ZoneInfo

from models import ChatRequest, ChatResponse, RPARequest, RPAResponse, TurnContext, TokenUsage
from ollama_client import get_models, chat as ollama_chat
from watcher import PassiveWatcher
from app.utils.token_utils import estimate_tokens
from app.services.rag_service import (
    get_rag_context, list_indexed_documents, delete_document_service,
    clear_corpus_service, get_corpus_stats_service, get_full_document_content
)
from app.services.ingest_service import ingest_file
from app.services.watcher import inspect_chat_request, ChatRequestPayload
from app.services.prompt_builder import build_grounded_prompt, build_chat_with_document_prompt
from app.services.confidence import compute_document_confidence
from app.services.document_coverage import detect_document_coverage_mode, explain_document_coverage_reason
from app.services.response_format import detect_document_response_format, explain_document_response_format_rule
from app.services.session_grounding import build_session_grounding, get_session_grounding, increment_session_usage
from app.services.personal_service import (
    AMBIGUITY_RESPONSE,
    initialize_personal_service,
    NO_ENTITY_RESPONSE,
    NO_FACT_RESPONSE,
    persist_user_input,
    retrieve_personal_store_records,
)
from app.services.personal_prompt_builder import build_personal_grounded_prompt
from app.config import (
    SUPPORTED_UPLOAD_TYPES_DISPLAY,
    STATIC_DIR,
    TEMPLATES_DIR,
    TEMP_UPLOADS_DIR,
)
from rag.ingest import is_supported_upload_extension
from tools.gobook_tools import (
    detect_rpa_intent,
    extract_rpa_details,
    rpa_book,
    rpa_cancel,
    rpa_list,
    rpa_open_courts,
)
from tools.workspace_tools import (
    calendar_create,
    calendar_next,
    calendar_remove,
    calendar_search,
    detect_workspace_intent,
    extract_workspace_details,
    gmail_check,
    gmail_send,
    normalize_date,
    sheet_create,
    sheet_read,
    sheet_write,
    summarize_calendar_output,
    summarize_whatsapp_output,
    whatsapp_read,
    whatsapp_search,
    whatsapp_send,
)

RAG_ENABLED = True
WATCHER_ENABLED = True

app = FastAPI(title="Tyrone 3.0")

# Initialize DBs
initialize_personal_service()

# Setup templates and static files
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

watcher = PassiveWatcher()

@app.on_event("startup")
async def startup_event():
    await build_session_grounding()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/grounding")
async def api_grounding():
    grounding = get_session_grounding()
    return grounding

@app.post("/api/ingest")
async def api_ingest(file: UploadFile = File(...)):
    # Save the uploaded file temporarily
    temp_dir = TEMP_UPLOADS_DIR
    os.makedirs(temp_dir, exist_ok=True)

    filename = file.filename or "upload.pdf"
    safe_name = os.path.basename(filename)
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")

    # Extension validation
    ext = os.path.splitext(safe_name)[1].lower()
    if not is_supported_upload_extension(ext):
        return JSONResponse(content={
            "ok": False,
            "status": "failed",
            "error": f"Unsupported file type. Supported types: {SUPPORTED_UPLOAD_TYPES_DISPLAY}"
        })

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
    result = list_indexed_documents()
    return result

@app.delete("/api/docs/{document_id}")
async def api_delete_doc(document_id: str):
    result = delete_document_service(document_id)
    return result

@app.post("/api/docs/clear")
async def api_clear_corpus():
    result = clear_corpus_service()
    return result

@app.post("/api/session/reset")
async def api_reset_session():
    # We rebuild grounding to get a new session ID and reset counters
    await build_session_grounding()
    return {"ok": True}

@app.get("/api/stats")
async def api_stats():
    result = get_corpus_stats_service()
    return result

@app.get("/api/models")
async def api_models():
    models, error = await get_models()
    if error:
        # We don't crash, we just return the error gracefully.
        return JSONResponse(content={"models": [], "error": error}, status_code=200)
    return {"models": models}

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: ChatRequest):
    start_time = time.time()

    # Determine effective mode
    effective_mode = request.mode

    # 1. Create TurnContext
    context = TurnContext(
        model=request.model,
        user_message=request.message,
        request_started_at=datetime.now(timezone.utc).isoformat()
    )

    # Token counting - User input
    user_input_tokens = estimate_tokens(request.message)
    context_tokens = 0

    # 2. Watcher Pre-check
    watcher.pre_check(context)

    # Tri-Mode Execution Shell
    retrieval_query = None
    retrieval_chunks = []
    retrieval_metrics = None
    retrieval_error = None
    response_format_detected = None
    response_format_reason = None
    coverage_mode = None
    coverage_reason = None
    coverage_truncated = False
    final_prompt = request.message
    skip_llm = False
    reply_text = ""
    confidence_payload = None

    # Personal mode data
    personal_context = None
    personal_input_persisted = False
    personal_status = None
    personal_general_fallback_disabled = False
    personal_retrieval_metrics = None

    if effective_mode == "document":
        response_format_detected = detect_document_response_format(request.message)
        response_format_reason = explain_document_response_format_rule(request.message)
        coverage_mode = detect_document_coverage_mode(request.message, response_format_detected)
        coverage_reason = explain_document_coverage_reason(request.message, response_format_detected)
        if RAG_ENABLED:
            rag_result = get_rag_context(
                request.message,
                top_k=3,
                document_ids=request.document_ids,
                response_format=response_format_detected,
            )
            retrieval_query = request.message
            retrieval_error = rag_result.get("error")
            retrieval_chunks = rag_result.get("chunks", [])
            retrieval_metrics = rag_result.get("metrics")
            prompt_chunks = rag_result.get("chunks_for_prompt", retrieval_chunks)
            coverage_mode = (retrieval_metrics or {}).get("coverage_mode", coverage_mode)
            coverage_truncated = bool((retrieval_metrics or {}).get("coverage_truncated", False))
            coverage_reason = (retrieval_metrics or {}).get("coverage_reason", coverage_reason)

            if not retrieval_chunks and not retrieval_error:
                # Fallback if corpus is empty or nothing retrieved
                skip_llm = True
                reply_text = "Insufficient information. No relevant information found in the selected documents."
                final_prompt = "No context provided."
            elif retrieval_chunks:
                # Calculate context tokens from chunks
                context_text = "\n".join([c.get("text", "") for c in prompt_chunks])
                context_tokens = estimate_tokens(context_text)
                final_prompt = build_grounded_prompt(
                    request.message,
                    prompt_chunks,
                    response_format=response_format_detected,
                    retrieval_mode=(retrieval_metrics or {}).get("retrieval_mode", "default"),
                    coverage_mode=coverage_mode or "narrow_lookup",
                    coverage_truncated=coverage_truncated,
                )
    elif effective_mode == "personal":
        rpa_intent = detect_rpa_intent(request.message)
        if rpa_intent:
            try:
                skip_llm = True
                personal_general_fallback_disabled = True
                personal_status = f"rpa_{rpa_intent}"

                rpa_details = extract_rpa_details(request.message)
                request_date = rpa_details["date"]
                times = rpa_details["times"]
                court_value = rpa_details["court"]

                if rpa_intent == "list":
                    result = await rpa_list(100)
                    reply_text = "\n".join(result) if result else "No active upcoming bookings."
                elif rpa_intent == "open_courts":
                    open_start_time = rpa_details["start"]
                    open_end_time = rpa_details["end"]
                    if not request_date or not open_start_time or not open_end_time:
                        raise RuntimeError(
                            "Open courts needs a date and a time range, for example 16:30-18:00 or between 16:30 and 18:00."
                        )
                    if not open_end_time:
                        reply_text = "Open courts needs a time range, for example 16:30-18:00."
                    else:
                        courts = await rpa_open_courts(request_date, open_start_time, open_end_time, 100)
                        reply_text = "\n".join(courts) if courts else "No open courts found."
                elif rpa_intent == "book":
                    if not request_date or len(times) < 1:
                        raise RuntimeError("Booking requests need a date and time.")
                    if rpa_details["start"] and rpa_details["end"]:
                        time_value = f"{rpa_details['start']}-{rpa_details['end']}"
                    else:
                        time_value = times[0]
                    result = await rpa_book(request_date, time_value, court_value, True, 100)
                    reply_text = f"Booking submitted: {result.get('selection', 'unknown')}"
                else:
                    if not request_date or len(times) < 1:
                        raise RuntimeError("Cancel requests need a date and time.")
                    time_value = times[0]
                    result = await rpa_cancel(request_date, time_value, court_value, True, 100)
                    if not result.get("ok", True):
                        raise RuntimeError(result.get("error") or "Cancel request failed.")
                    reply_text = "Cancellation submitted."

                personal_context = {"resolved_entities": [], "memories": []}
            except Exception as exc:
                reply_text = f"RPA request failed: {exc}"
                skip_llm = True
                personal_context = {"resolved_entities": [], "memories": []}
        elif detect_workspace_intent(request.message):
            workspace_intent = detect_workspace_intent(request.message)
            try:
                skip_llm = True
                personal_general_fallback_disabled = True
                personal_status = f"workspace_{workspace_intent}"
                details = extract_workspace_details(request.message)

                if workspace_intent == "gmail_send":
                    to_value = details.get("email")
                    subject = details.get("subject") or "Tyrone message"
                    body = details.get("body") or request.message
                    if not to_value:
                        raise RuntimeError("Gmail send requests need a recipient email address.")
                    result = await gmail_send(to_value, subject, body)
                    reply_text = result.output.strip() or "Gmail send completed."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Gmail send failed.")
                elif workspace_intent == "gmail_check":
                    result = await gmail_check(5)
                    reply_text = result.output.strip() or "No unread inbox mail."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Gmail check failed.")
                elif workspace_intent == "calendar_create":
                    title = details.get("calendar_title") or details.get("title") or "Tyrone calendar event"
                    date = details.get("date")
                    start = details.get("start")
                    end = details.get("end")
                    if not date or not start or not end:
                        raise RuntimeError("Calendar create requests need a date and start/end times.")
                    norm_date = normalize_date(date)
                    start_dt = f"{norm_date}T{start}:00+02:00"
                    end_dt = f"{norm_date}T{end}:00+02:00"
                    result = await calendar_create(title, start_dt, end_dt)
                    reply_text = result.output.strip() or "Calendar entry created."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Calendar create failed.")
                elif workspace_intent == "calendar_search":
                    query = details.get("title") or details.get("message") or request.message
                    result = await calendar_search(query, days=7)
                    reply_text = summarize_calendar_output(result.output, request.message)
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Calendar search failed.")
                elif workspace_intent == "calendar_remove":
                    event_id = details.get("event_id") or details.get("id")
                    if not event_id:
                        raise RuntimeError("Calendar remove requests need an event ID.")
                    result = await calendar_remove(event_id)
                    reply_text = result.output.strip() or "Calendar entry removed."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Calendar remove failed.")
                elif workspace_intent == "calendar_next":
                    request_l = request.message.lower()
                    if "tomorrow" in request_l or "today" in request_l:
                        tz = ZoneInfo("Africa/Johannesburg")
                        now = datetime.now(tz)
                        day_offset = 1 if "tomorrow" in request_l else 0
                        target_day = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
                        day_start = target_day.isoformat()
                        day_end = (target_day + timedelta(days=1)).isoformat()
                        result = await calendar_search("", time_min=day_start, time_max=day_end, max_results=20)
                        if not result.ok:
                            raise RuntimeError(result.error.strip() or "Calendar search failed.")
                        reply_text = summarize_calendar_output(result.output, request.message)
                        if not reply_text:
                            reply_text = "No calendar entries found for that day."
                    else:
                        result = await calendar_next(5)
                        reply_text = summarize_calendar_output(result.output, request.message)
                        if not result.ok:
                            raise RuntimeError(result.error.strip() or "Calendar next failed.")
                elif workspace_intent == "sheet_create":
                    title = details.get("title") or "Tyrone Sheet"
                    result = await sheet_create(title)
                    reply_text = result.output.strip() or "Spreadsheet created."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Sheet create failed.")
                elif workspace_intent == "sheet_read":
                    spreadsheet_id = details.get("spreadsheet_id")
                    range_name = details.get("range")
                    if not spreadsheet_id or not range_name:
                        raise RuntimeError("Sheet read requests need a spreadsheet id and range.")
                    result = await sheet_read(spreadsheet_id, range_name)
                    reply_text = result.output.strip() or "No sheet values found."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Sheet read failed.")
                elif workspace_intent == "sheet_write":
                    spreadsheet_id = details.get("spreadsheet_id")
                    range_name = details.get("range")
                    values_json = details.get("values")
                    if not spreadsheet_id or not range_name or not values_json:
                        raise RuntimeError("Sheet write requests need a spreadsheet id, range, and values JSON.")
                    result = await sheet_write(spreadsheet_id, range_name, values_json)
                    reply_text = result.output.strip() or "Sheet write completed."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "Sheet write failed.")
                elif workspace_intent == "whatsapp_send":
                    chat = details.get("chat")
                    if not chat:
                        raise RuntimeError("WhatsApp send requests need a chat name.")
                    message_text = details.get("whatsapp_message") or details.get("body") or request.message
                    result = await whatsapp_send(chat, message=message_text)
                    reply_text = result.output.strip() or "WhatsApp message sent."
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "WhatsApp send failed.")
                elif workspace_intent == "whatsapp_read":
                    chat = details.get("chat")
                    if not chat:
                        raise RuntimeError("WhatsApp read requests need a chat name.")
                    result = await whatsapp_read(chat, limit=10)
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "WhatsApp read failed.")
                    user_text = request.message.lower()
                    if any(term in user_text for term in ("plumber", "plumbers", "recommended", "recommend", "meeting date", "decided", "decision", "summary", "summarize", "summarise")):
                        style_hint = (
                            "Return a compact answer with at most 5 bullets. "
                            "Only mention people, decisions, or facts that are explicitly supported by the messages. "
                            "If the chat does not clearly support an answer, say that you do not know. "
                            "For recommendation requests, list only the names that are directly mentioned as recommendations and a very short reason. "
                            "For decision requests, answer yes/no first, then one short sentence. "
                            "Avoid long prose, avoid repeating the whole transcript, and exclude timestamps and phone numbers unless they are directly relevant."
                        )
                    else:
                        style_hint = (
                            "Return a concise answer in at most 4 bullets. "
                            "Focus on the main point, any decision, and any action items. "
                            "Avoid timestamps, phone numbers, and repeated chatter."
                        )
                    answer_prompt = (
                        "Answer the user's WhatsApp question using only the retrieved chat messages below. "
                        f"{style_hint}\n\n"
                        f"User question: {request.message}\n\n"
                        f"Chat messages:\n{result.output}"
                    )
                    answer_response, _, answer_error = await ollama_chat(
                        request.model,
                        answer_prompt,
                        temperature=0.1,
                    )
                    if answer_error:
                        raise RuntimeError(answer_error)
                    reply_text = answer_response.get("message", {}).get("content", "").strip() or summarize_whatsapp_output(result.output)
                elif workspace_intent == "whatsapp_search":
                    chat = details.get("chat")
                    if not chat:
                        raise RuntimeError("WhatsApp search requests need a chat name.")
                    result = await whatsapp_search(chat)
                    reply_text = result.output.strip() or f"Chat opened: {chat}"
                    if not result.ok:
                        raise RuntimeError(result.error.strip() or "WhatsApp search failed.")
                else:
                    raise RuntimeError(f"Unsupported workspace intent: {workspace_intent}")

                personal_context = {"resolved_entities": [], "memories": []}
            except Exception as exc:
                reply_text = f"Workspace request failed: {exc}"
                skip_llm = True
                personal_context = {"resolved_entities": [], "memories": []}
        else:
            persist_user_input(request.message, session_id=context.session_id)
            personal_input_persisted = True
            personal_general_fallback_disabled = True

            personal_result = retrieve_personal_store_records(request.message)
            personal_status = personal_result["status"]
            personal_retrieval_metrics = personal_result.get("metrics")
            personal_context = {
                "resolved_entities": personal_result["resolved_entities"],
                "memories": personal_result["memories"],
            }

            if personal_status == "ambiguous":
                reply_text = AMBIGUITY_RESPONSE
                skip_llm = True
                final_prompt = "Personal mode store retrieval was ambiguous. No LLM prompt generated."
            elif personal_status == "no_fact":
                reply_text = NO_FACT_RESPONSE
                skip_llm = True
                final_prompt = "Personal mode store retrieval found an entity but no supporting records. No LLM prompt generated."
            elif personal_status == "no_entity":
                reply_text = NO_ENTITY_RESPONSE
                skip_llm = True
                final_prompt = "Personal mode store retrieval found no matching records. No LLM prompt generated."
            else:
                # Calculate context tokens from personal memories
                context_text = "\n".join([m.get("raw_user_input", "") for m in personal_context["memories"]])
                context_tokens = estimate_tokens(context_text)
                final_prompt = build_personal_grounded_prompt(
                    request.message,
                    personal_context["resolved_entities"],
                    personal_context["memories"],
                )
    else: # chat mode
        if request.chat_document_id:
            doc_data = get_full_document_content(request.chat_document_id)
            if doc_data.get("error"):
                skip_llm = True
                reply_text = f"Error: {doc_data['error']}"
                final_prompt = f"Failed to load document {request.chat_document_id}"
            else:
                # Full document context
                context_tokens = estimate_tokens(doc_data.get("full_text", ""))
                final_prompt = build_chat_with_document_prompt(
                    request.message,
                    doc_data["document_name"],
                    doc_data["full_text"]
                )
        else:
            # normal chat
            final_prompt = request.message

    # 2.5 Watcher Module
    watcher_allowed = None
    watcher_modified = None
    watcher_notes = []
    watcher_error = None
    watcher_rule_results = []

    if WATCHER_ENABLED:
        payload: ChatRequestPayload = {
            "user_message": request.message,
            "selected_model": request.model,
            "rag_enabled": RAG_ENABLED,
            "retrieval_query": retrieval_query,
            "retrieval_chunks": retrieval_chunks,
            "retrieval_error": retrieval_error,
            "final_prompt": final_prompt
        }

        watcher_result = inspect_chat_request(payload)

        watcher_allowed = watcher_result.get("allowed")
        watcher_modified = watcher_result.get("modified")
        watcher_notes = watcher_result.get("watcher_notes", [])
        watcher_error = watcher_result.get("watcher_error")
        watcher_rule_results = watcher_result.get("rule_results", [])

        final_prompt = watcher_result.get("payload", payload).get("final_prompt", final_prompt)

    # 3. Call Ollama
    prompt_tokens = estimate_tokens(final_prompt)
    response_tokens = 0

    if not skip_llm:
        ollama_response, request_summary, error = await ollama_chat(request.model, final_prompt, temperature=0.1)
        context.ollama_request_summary = request_summary

        if error:
            context.error = error
            reply_text = f"Error: {error}"
        else:
            # Simplify response summary to keep it clean
            context.ollama_response_summary = {
                "model": ollama_response.get("model"),
                "created_at": ollama_response.get("created_at"),
                "done": ollama_response.get("done"),
                "total_duration": ollama_response.get("total_duration")
            }
            reply_text = ollama_response.get("message", {}).get("content", "")
            response_tokens = estimate_tokens(reply_text)
    else:
        # If skipped LLM, we might still have a reply_text
        response_tokens = estimate_tokens(reply_text)

    # Increment session usage
    increment_session_usage(prompt_tokens, response_tokens)
    session_grounding = get_session_grounding()
    if session_grounding is None:
        session_grounding = {
            "session_turn_count": 1,
            "session_prompt_tokens_est": prompt_tokens,
            "session_response_tokens_est": response_tokens,
            "session_total_tokens_est": prompt_tokens + response_tokens,
        }

    # 4. Watcher Post-check
    watcher.post_check(context)

    end_time = time.time()
    elapsed_ms = round((end_time - start_time) * 1000, 2)

    # 5. Build structured debug trace
    response_preview = reply_text[:100] + ("..." if len(reply_text) > 100 else "") if reply_text else None

    # Handle RAG scope for debug
    retrieval_scope = "full_corpus"
    selected_documents_count = 0
    selected_documents_names = []

    if effective_mode == "chat" and request.chat_document_id:
        retrieval_scope = "single_document_grounding"
        selected_documents_count = 1
        # Try to get the name if we loaded it successfully
        if not skip_llm:
            # We already have it from doc_data
            selected_documents_names = [doc_data.get("document_name", request.chat_document_id)]
        else:
            selected_documents_names = [request.chat_document_id]
    elif request.document_ids:
        retrieval_scope = "working_set"
        selected_documents_count = len(request.document_ids)

        # Try to resolve document names from chunks or recent docs
        # We can map ID -> Name from the retrieval_chunks if any matched
        # Or from a quick lookup if needed. For now, let's use the chunks metadata.
        id_to_name = {chunk['document_id']: chunk['document_name'] for chunk in retrieval_chunks}

        selected_documents_names = []
        for doc_id in request.document_ids:
            name = id_to_name.get(doc_id, doc_id) # Fallback to ID if not in retrieved chunks
            selected_documents_names.append(name)

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
        "response_format_detected": response_format_detected if effective_mode == "document" else None,
        "response_format_rules_applied": True if effective_mode == "document" else False,
        "response_format_reason": response_format_reason if effective_mode == "document" else None,
        "coverage_mode": coverage_mode if effective_mode == "document" else None,
        "coverage_required": coverage_mode == "coverage_required" if effective_mode == "document" else False,
        "retrieval_top_k_requested": (retrieval_metrics or {}).get("retrieval_top_k_requested") if effective_mode == "document" else None,
        "retrieval_verified_chunks_count": (retrieval_metrics or {}).get("retrieval_verified_chunks_count") if effective_mode == "document" else None,
        "retrieval_chunks_used_for_prompt": (retrieval_metrics or {}).get("retrieval_chunks_used_for_prompt") if effective_mode == "document" else None,
        "coverage_truncated": coverage_truncated if effective_mode == "document" else False,
        "coverage_reason": coverage_reason if effective_mode == "document" else None,
        "personal_input_persisted": personal_input_persisted,
        "personal_status": personal_status,
        "personal_context": personal_context,
        "personal_records_retrieved_count": len(personal_context["memories"]) if personal_context else 0,
        "personal_retrieval_metrics": personal_retrieval_metrics,
        "personal_general_knowledge_fallback": "disabled" if effective_mode == "personal" else "n/a",
        "watcher_enabled": WATCHER_ENABLED,
        "watcher_allowed": watcher_allowed,
        "watcher_modified": watcher_modified,
        "watcher_notes": watcher_notes,
        "watcher_error": watcher_error,
        "watcher_rule_results": watcher_rule_results,
        "final_prompt": final_prompt,
        "ollama_error": context.error,
        "response_preview": response_preview
    }

    if effective_mode == "document":
        confidence_payload = compute_document_confidence(
            chunks_used_for_prompt=rag_result.get("chunks_for_prompt", retrieval_chunks) if 'rag_result' in locals() else retrieval_chunks,
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
        session_turn_count=session_grounding["session_turn_count"],
        session_prompt_tokens_est=session_grounding["session_prompt_tokens_est"],
        session_response_tokens_est=session_grounding["session_response_tokens_est"],
        session_total_tokens_est=session_grounding["session_total_tokens_est"]
    )

    return ChatResponse(
        reply=reply_text,
        evidence=retrieval_chunks if effective_mode == "document" else None,
        confidence=confidence_payload if effective_mode == "document" else None,
        debug=debug_payload,
        token_usage=token_usage
    )


def _ensure_personal_mode(mode: str):
    if mode != "personal":
        raise HTTPException(status_code=403, detail="These tools are only available in Personal Mode.")


def _detect_rpa_intent(message: str) -> str | None:
    text = message.lower().strip()
    if not text:
        return None
    has_date = bool(re.search(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", text))
    has_time = bool(re.search(r"\b\d{1,2}:\d{2}\b", text))
    has_court = bool(re.search(r"\bcourt\s*#?\s*\d+\b", text, re.I))
    has_booking_shape = has_date or has_time or has_court

    if any(term in text for term in ("cancel booking", "delete booking", "cancel my booking", "remove booking")):
        return "cancel"
    if re.search(r"\bcancel\b", text) and has_booking_shape:
        return "cancel"
    if any(term in text for term in ("open courts", "check for open courts", "available courts", "courts open")):
        return "open_courts"
    if any(term in text for term in ("upcoming bookings", "my bookings", "list bookings", "show bookings")):
        return "list"
    has_book_word = bool(re.search(r"\bbook\b", text))
    if any(term in text for term in ("book court", "make booking", "new booking", "book squash", "book the court", "please book")):
        return "book"
    if has_book_word and (has_date or has_time or has_court):
        return "book"
    return None


def _extract_date_and_times(message: str) -> tuple[str | None, list[str]]:
    dates = re.findall(r"(\d{4}[-/]\d{2}[-/]\d{2})", message)
    times = re.findall(r"(\d{1,2}:\d{2})", message)
    return (dates[0] if dates else None), times


def _extract_rpa_details(message: str) -> dict:
    text = message.lower()
    request_date, times = _extract_date_and_times(message)

    court_match = re.search(r"\bcourt\s*#?\s*(\d+)\b", text, re.I)
    court_value = f"Court {court_match.group(1)}" if court_match else "Court 1"

    start_time = None
    end_time = None

    range_match = re.search(r"(\d{1,2}:\d{2})\s*(?:-|to|until|through)\s*(\d{1,2}:\d{2})", text, re.I)
    if range_match:
        start_time, end_time = range_match.group(1), range_match.group(2)
    else:
        between_match = re.search(r"(?:between|from)\s+(\d{1,2}:\d{2})\s+(?:and|to)\s+(\d{1,2}:\d{2})", text, re.I)
        if between_match:
            start_time, end_time = between_match.group(1), between_match.group(2)
        elif len(times) >= 2:
            start_time, end_time = times[0], times[1]
        elif len(times) == 1:
            start_time = times[0]

    return {
        "date": request_date,
        "times": times,
        "start": start_time,
        "end": end_time,
        "court": court_value,
    }


def _time_to_minutes(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def _slot_within_range(slot_start: str, slot_end: str, range_start: str, range_end: str) -> bool:
    start_minutes = _time_to_minutes(slot_start)
    end_minutes = _time_to_minutes(slot_end)
    request_start_minutes = _time_to_minutes(range_start)
    request_end_minutes = _time_to_minutes(range_end)

    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    if request_end_minutes <= request_start_minutes:
        request_end_minutes += 24 * 60

    return start_minutes >= request_start_minutes and end_minutes <= request_end_minutes


async def _rpa_book_impl(date: str, time_value: str, court: str, confirm: bool, slowmo: int):
    validate_booking_date(date)
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_book_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_new_booking_panel(page)
                date_str = normalize_date(date)
                await set_booking_date(page, date_str)
                selection = await select_slot(page, time_value, court or "Court 1")
                if confirm:
                    await page.locator("input[type='submit'][value='Book']").click()
                    await page.wait_for_timeout(2000)
                return {"selection": selection, "confirmed": confirm}
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


async def _rpa_cancel_impl(date: str, time_value: str, court: str, confirm: bool, slowmo: int):
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_cancel_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_upcoming_bookings(page)
                rows = page.locator("#upcomings tbody tr")
                target_date = normalize_date(date)
                target_court = normalize_court(court or "Court 1")
                start_target, end_target = time_value.replace(" ", ""), None
                if "-" in start_target:
                    start_target, end_target = start_target.split("-", 1)

                row = None
                for i in range(await rows.count()):
                    candidate = rows.nth(i)
                    cells = candidate.locator("td")
                    if await cells.count() < 8:
                        continue
                    facility = (await cells.nth(2).inner_text()).strip()
                    date_text = (await cells.nth(3).inner_text()).strip()
                    start_text = (await cells.nth(4).inner_text()).strip()
                    end_text = (await cells.nth(5).inner_text()).strip()
                    status_text = (await cells.nth(6).inner_text()).strip()
                    if facility != target_court or date_text != target_date or status_text.lower() == "cancelled":
                        continue
                    if end_target is None and start_text == start_target:
                        row = candidate
                        break
                    if end_target is not None and start_text == start_target and end_text == end_target:
                        row = candidate
                        break

                if row is None:
                    return {"ok": False, "error": "Matching booking not found."}
                await open_booking_modal(page, row)
                result = await cancel_booking(page, confirm)
                return result
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


async def _rpa_list_impl(slowmo: int):
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_list_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_upcoming_bookings(page)
                rows = page.locator("#upcomings tbody tr")
                results = []
                for i in range(await rows.count()):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    if await cells.count() < 8:
                        continue
                    court = (await cells.nth(2).inner_text()).strip()
                    date_text = (await cells.nth(3).inner_text()).strip()
                    start_text = (await cells.nth(4).inner_text()).strip()
                    end_text = (await cells.nth(5).inner_text()).strip()
                    status_text = (await cells.nth(6).inner_text()).strip()
                    if status_text.lower() == "cancelled":
                        continue
                    results.append(f"{date_text} / {start_text}-{end_text} / {court}")
                return results
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


async def _rpa_open_courts_impl(date: str, start: str, end: str, slowmo: int):
    validate_booking_date(date)
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_open_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_new_booking_panel(page)
                date_str = normalize_date(date)
                await set_booking_date(page, date_str)
                table = page.locator("table").first
                headers = [h.strip() for h in await table.locator("th").all_inner_texts()]
                court_columns = [h for h in headers if h.startswith("Court #")]
                results = []
                rows = table.locator("tr")
                for i in range(await rows.count()):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    if await cells.count() == 0:
                        continue
                    row_text = (await row.inner_text()).strip()
                    match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", row_text)
                    if not match:
                        continue
                    slot_start, slot_end = match.group(1), match.group(2)
                    if not _slot_within_range(slot_start, slot_end, start, end):
                        continue
                    for court_name in court_columns:
                        cell_index = headers.index(court_name)
                        checkbox = cells.nth(cell_index).locator("input[type='checkbox']").first
                        if await checkbox.count() == 0:
                            continue
                        if await checkbox.is_enabled() and not await checkbox.is_checked():
                            results.append(f"{date_str} / {slot_start}-{slot_end} / {court_name}")
                return results
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


@app.post("/api/rpa/book", response_model=RPAResponse)
async def api_rpa_book(request: RPARequest):
    _ensure_personal_mode(request.mode)
    if not request.date or not request.time:
        return RPAResponse(ok=False, action="book", error="date and time are required.")
    try:
        result = await rpa_book(request.date, request.time, request.court or "Court 1", request.confirm, request.slowmo)
        return RPAResponse(ok=True, action="book", result=result)
    except Exception as exc:
        return RPAResponse(ok=False, action="book", error=str(exc))


@app.post("/api/rpa/cancel", response_model=RPAResponse)
async def api_rpa_cancel(request: RPARequest):
    _ensure_personal_mode(request.mode)
    if not request.date or not request.time:
        return RPAResponse(ok=False, action="cancel", error="date and time are required.")
    try:
        result = await rpa_cancel(request.date, request.time, request.court or "Court 1", request.confirm, request.slowmo)
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
        return RPAResponse(ok=False, action="open_courts", error="date, start, and end are required.")
    try:
        results = await rpa_open_courts(request.date, request.start, request.end, request.slowmo)
        return RPAResponse(ok=True, action="open_courts", result={"courts": results})
    except Exception as exc:
        return RPAResponse(ok=False, action="open_courts", error=str(exc))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
