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
            "message": {"content": "| Date | Amount |\n| --- | --- |\n| 2026-01-01 | 120.00 |"},
        },
        {"prompt_preview": prompt[:120], "temperature": temperature},
        None,
    )


def _patch_session_grounding(monkeypatch):
    monkeypatch.setattr("main.increment_session_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr("main.get_session_grounding", lambda: dict(SESSION_GROUNDING))


def test_document_mode_debug_payload_contains_response_format_detected(monkeypatch):
    _patch_session_grounding(monkeypatch)
    monkeypatch.setattr(
        "main.get_rag_context",
        lambda *args, **kwargs: {
            "error": None,
            "chunks": [
                {
                    "document_id": "doc1",
                    "document_name": "claims.xlsx",
                    "chunk_index": 1,
                    "text": "2026-01-01 | 120.00 | GP Consultation",
                    "score": 0.9,
                    "vector_score": 0.8,
                    "lexical_score": 1.0,
                }
            ],
            "metrics": {"retrieval_mode": "enumeration", "eligible_docs": 1, "candidate_count": 1, "pool_size": 1},
        },
    )
    monkeypatch.setattr("main.ollama_chat", _fake_ollama_chat)

    response = client.post(
        "/api/chat",
        json={
            "model": "fake-model",
            "message": "show all GP consultations with date and amount",
            "mode": "document",
            "document_ids": ["doc1"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["debug"]["response_format_detected"] == "table"
    assert data["debug"]["response_format_rules_applied"] is True
    assert data["debug"]["response_format_reason"] in {"matched_table_keyword", "matched_list_plus_field_pair"}


def test_chat_mode_unaffected_by_response_format_debug(monkeypatch):
    _patch_session_grounding(monkeypatch)
    monkeypatch.setattr("main.ollama_chat", _fake_ollama_chat)

    response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "hello", "mode": "chat"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["debug"]["mode"] == "chat"
    assert data["debug"]["response_format_detected"] is None
    assert data["debug"]["response_format_rules_applied"] is False


def test_personal_mode_unaffected_by_response_format_debug(monkeypatch):
    _patch_session_grounding(monkeypatch)
    response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "my wife's birthday", "mode": "personal"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["debug"]["mode"] == "personal"
    assert data["debug"]["response_format_detected"] is None
    assert data["debug"]["response_format_rules_applied"] is False
