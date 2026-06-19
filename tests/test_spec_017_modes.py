"""Spec 017 - chat/document mode API integration (in-process, deterministic fake model).

Previously live-port smoke scripts depending on a session-scoped uvicorn server
(removed from conftest). Now driven through FastAPI's TestClient with OLLAMA_FAKE=1.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fake_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_FAKE", "1")


@pytest.fixture(autouse=True)
def _reset_session():
    client.post("/api/session/reset")


def test_chat_mode_api():
    response = client.post(
        "/api/chat",
        json={"model": "fake", "message": "When is Cornelia's birthday?", "mode": "chat"},
    )
    assert response.status_code == 200
    debug = response.json().get("debug", {})
    assert debug.get("mode") == "chat"
    # Chat mode must not populate personal context.
    assert debug.get("personal_context") is None
    assert isinstance(debug.get("final_prompt"), str) and debug["final_prompt"]


def test_document_mode_api():
    response = client.post(
        "/api/chat",
        json={"model": "fake", "message": "What does the policy say?", "mode": "document"},
    )
    assert response.status_code == 200
    debug = response.json().get("debug", {})
    assert debug.get("mode") == "document"
    assert debug.get("retrieval_query") == "What does the policy say?"
    # No corpus is indexed in the isolated test DB, so no chunks return; the
    # important contract is that document mode runs retrieval without crashing.
    assert debug.get("retrieval_chunks") == []
