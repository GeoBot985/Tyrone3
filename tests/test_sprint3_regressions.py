from __future__ import annotations

import asyncio

from models import ChatRequest
from app.services.chat_orchestrator import prepare_mode_state


def test_document_mode_refuses_with_exact_canonical_phrase():
    request = ChatRequest(
        model="fake-model",
        message="What is the hidden clause?",
        mode="document",
        document_ids=["doc-1"],
    )

    def fake_get_rag_context(*args, **kwargs):
        return {
            "error": None,
            "chunks": [],
            "chunks_for_prompt": [],
            "metrics": {},
        }

    state = asyncio.run(
        prepare_mode_state(
            request,
            session_id="test-session",
            rag_enabled=True,
            get_rag_context_fn=fake_get_rag_context,
        )
    )

    assert state["skip_llm"] is True
    assert state["reply_text"] == "Insufficient information"
    assert state["final_prompt"] == "No context provided."
