from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class ChatRequest(BaseModel):
    model: str
    message: str
    mode: str = "chat" # chat, document, personal
    document_ids: Optional[List[str]] = None
    chat_document_id: Optional[str] = None

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
    evidence: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[Dict[str, Any]] = None
    debug: Dict[str, Any]
    token_usage: Optional[TokenUsage] = None


class RPARequest(BaseModel):
    mode: str = "personal"
    date: Optional[str] = None
    time: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    court: Optional[str] = None
    confirm: bool = False
    slowmo: int = 100


class RPAResponse(BaseModel):
    ok: bool
    action: str
    result: Optional[Any] = None
    error: Optional[str] = None

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
    watcher_events: List[WatcherEvent] = Field(default_factory=list)
    ollama_request_summary: Optional[Dict[str, Any]] = None
    ollama_response_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
