from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=20000)
    mode: Literal["chat", "document", "personal"] = "chat"
    document_ids: list[str] | None = None
    chat_document_id: str | None = None


class TokenUsage(BaseModel):
    mode: str
    user_input_tokens_est: int
    context_tokens_est: int
    prompt_tokens_est: int
    response_tokens_est: int
    turn_total_tokens_est: int
    session_turn_count: int
    session_prompt_tokens_est: int
    session_response_tokens_est: int
    session_total_tokens_est: int


class ChatResponse(BaseModel):
    reply: str
    evidence: list[dict[str, Any]] | None = None
    confidence: dict[str, Any] | None = None
    debug: dict[str, Any]
    token_usage: TokenUsage | None = None


class RPARequest(BaseModel):
    mode: str = "personal"
    date: str | None = None
    time: str | None = None
    start: str | None = None
    end: str | None = None
    court: str | None = None
    confirm: bool = False
    slowmo: int = 100


class RPAResponse(BaseModel):
    ok: bool
    action: str
    result: Any | None = None
    error: str | None = None


class WatcherEvent(BaseModel):
    stage: str
    timestamp: str
    decision: str
    notes: str
    selected_model: str
    user_message_preview: str


class TurnContext(BaseModel):
    model: str
    user_message: str
    session_id: str = "default_session"
    request_started_at: str
    watcher_events: list[WatcherEvent] = Field(default_factory=list)
    ollama_request_summary: dict[str, Any] | None = None
    ollama_response_summary: dict[str, Any] | None = None
    error: str | None = None
