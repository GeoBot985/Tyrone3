from fastapi.testclient import TestClient

from main import app


client = TestClient(app)

SESSION_GROUNDING = {
    "current_datetime": "2026-04-12T00:00:00+00:00",
    "timezone": "Africa/Johannesburg",
    "location": "Johannesburg, South Africa",
    "agent_purpose": "General assistant with chat, document, and personal modes",
    "default_mode": "chat",
    "selected_model": "fake-model",
    "model_available": True,
    "session_turn_count": 1,
    "session_prompt_tokens_est": 10,
    "session_response_tokens_est": 5,
    "session_total_tokens_est": 15,
}


async def _fake_ollama_chat(_model, prompt, temperature=0.1):
    return (
        {
            "model": "fake-model",
            "created_at": "2026-04-12T00:00:00Z",
            "done": True,
            "total_duration": 1,
            "message": {"content": "- Date: 2026-01-01; Amount: 120.00 [Doc: claims.xlsx | Chunk 1]"},
        },
        {"prompt_preview": prompt[:120], "temperature": temperature},
        None,
    )


def _patch_session_grounding(monkeypatch):
    monkeypatch.setattr("main.increment_session_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr("main.get_session_grounding", lambda: dict(SESSION_GROUNDING))


def test_document_mode_returns_confidence_and_coverage_debug(monkeypatch):
    _patch_session_grounding(monkeypatch)
    monkeypatch.setattr(
        "main.get_rag_context",
        lambda *args, **kwargs: {
            "error": None,
            "chunks": [
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": 1, "text": "row 1", "score": 0.82, "lexical_score": 0.75},
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": 2, "text": "row 2", "score": 0.78, "lexical_score": 0.7},
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": 3, "text": "row 3", "score": 0.74, "lexical_score": 0.66},
            ],
            "chunks_for_prompt": [
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": 1, "text": "row 1", "score": 0.82, "lexical_score": 0.75},
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": 2, "text": "row 2", "score": 0.78, "lexical_score": 0.7},
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": 3, "text": "row 3", "score": 0.74, "lexical_score": 0.66},
            ],
            "metrics": {
                "retrieval_mode": "enumeration",
                "coverage_mode": "coverage_required",
                "coverage_required": True,
                "coverage_truncated": True,
                "coverage_reason": "max_coverage_chunks_reached",
                "retrieval_top_k_requested": 12,
                "retrieval_verified_chunks_count": 9,
                "retrieval_chunks_used_for_prompt": 3,
                "eligible_docs": 1,
                "candidate_count": 12,
                "pool_size": 12,
                "verification_status": "passed",
                "bounded_negative_mode": False,
            },
        },
    )
    monkeypatch.setattr("main.ollama_chat", _fake_ollama_chat)

    response = client.post(
        "/api/chat",
        json={
            "model": "fake-model",
            "message": "summarize the medical deductions please",
            "mode": "document",
            "document_ids": ["doc1"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["debug"]["coverage_mode"] == "coverage_required"
    assert data["debug"]["coverage_truncated"] is True
    assert data["confidence"] is not None
    assert "score" in data["confidence"]
    assert "label" in data["confidence"]


def test_chat_and_personal_modes_leave_confidence_empty(monkeypatch):
    _patch_session_grounding(monkeypatch)
    monkeypatch.setattr("main.ollama_chat", _fake_ollama_chat)

    chat_response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "hello", "mode": "chat"},
    )
    personal_response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "my wife's birthday", "mode": "personal"},
    )

    assert chat_response.status_code == 200
    assert personal_response.status_code == 200
    assert chat_response.json()["confidence"] is None
    assert personal_response.json()["confidence"] is None
