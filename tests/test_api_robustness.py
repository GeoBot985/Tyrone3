from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = ROOT / "secrets.json"


@pytest.fixture(autouse=True)
def _fake_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_FAKE", "1")


@pytest.fixture(autouse=True)
def _reset_session():
    client.post("/api/session/reset")


def _json(response):
    assert response.headers["content-type"].startswith("application/json")
    return response.json()


def test_empty_message_is_rejected():
    response = client.post("/api/chat", json={"model": "fake-model", "message": "", "mode": "chat"})
    assert response.status_code == 422


def test_oversized_message_is_rejected():
    response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "x" * 20001, "mode": "chat"},
    )
    assert response.status_code == 422


def test_bad_mode_is_rejected():
    response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "hello", "mode": "wrong"},
    )
    assert response.status_code == 422


def test_missing_model_is_rejected():
    response = client.post("/api/chat", json={"message": "hello", "mode": "chat"})
    assert response.status_code == 422


def test_empty_model_is_rejected():
    response = client.post(
        "/api/chat",
        json={"model": "", "message": "hello", "mode": "chat"},
    )
    assert response.status_code == 422


def test_api_models_works_without_real_ollama():
    response = client.get("/api/models")
    data = _json(response)
    assert response.status_code == 200
    assert "models" in data
    assert "granite4:1b" in data["models"]


def test_unsupported_upload_type_is_structured():
    response = client.post(
        "/api/ingest",
        files={"file": ("malware.exe", b"not a document", "application/octet-stream")},
    )
    data = _json(response)
    assert response.status_code == 200
    assert data["ok"] is False
    assert data["status"] == "failed"
    assert "Unsupported file type" in data["error"]


def test_missing_upload_field_is_422():
    response = client.post("/api/ingest", files={})
    assert response.status_code == 422


def test_rpa_endpoints_return_structured_errors_for_missing_fields():
    book = _json(client.post("/api/rpa/book", json={"mode": "personal"}))
    cancel = _json(client.post("/api/rpa/cancel", json={"mode": "personal"}))
    open_courts = _json(client.post("/api/rpa/open-courts", json={"mode": "personal"}))
    list_response = _json(client.post("/api/rpa/list", json={"mode": "personal"}))

    assert book["ok"] is False
    assert "date and time" in book["error"]
    assert cancel["ok"] is False
    assert "date and time" in cancel["error"]
    assert open_courts["ok"] is False
    assert "date, start, and end" in open_courts["error"]
    assert list_response["ok"] is True


def test_rpa_endpoints_reject_bad_mode():
    response = client.post(
        "/api/rpa/book",
        json={"mode": "chat", "date": "2026-06-05", "time": "18:00"},
    )
    assert response.status_code == 403


def test_chat_debug_does_not_expose_secret_values():
    secrets = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "hello there", "mode": "personal"},
    )
    data = _json(response)
    body = json.dumps(data)
    assert response.status_code == 200
    assert secrets["username"] not in body
    assert secrets["password"] not in body


def test_document_mode_ollama_error_falls_back_to_refusal(monkeypatch):
    monkeypatch.setattr(
        "main.get_rag_context",
        lambda *args, **kwargs: {
            "error": None,
            "chunks": [
                {
                    "document_id": "doc1",
                    "document_name": "claims.xlsx",
                    "chunk_index": 1,
                    "text": "row 1",
                    "score": 0.2,
                    "lexical_score": 0.0,
                }
            ],
            "chunks_for_prompt": [
                {
                    "document_id": "doc1",
                    "document_name": "claims.xlsx",
                    "chunk_index": 1,
                    "text": "row 1",
                    "score": 0.2,
                    "lexical_score": 0.0,
                }
            ],
            "metrics": {"coverage_mode": "narrow_lookup", "retrieval_mode": "default"},
        },
    )

    async def _fake_chat(*_args, **_kwargs):
        return {}, {"endpoint": "/api/chat"}, "Server error '500 Internal Server Error'"

    monkeypatch.setattr("main.ollama_chat", _fake_chat)

    response = client.post(
        "/api/chat",
        json={
            "model": "fake-model",
            "message": "What is the warranty period for the lunar orchid harvester?",
            "mode": "document",
        },
    )
    data = _json(response)
    assert response.status_code == 200
    assert data["reply"] == "Insufficient information"
    assert data["confidence"]["label"] == "low"
