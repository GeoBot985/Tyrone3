"""Spec 017 - personal mode API integration (in-process, deterministic fake model).

These were previously live-port smoke scripts that depended on a session-scoped
uvicorn server (removed from conftest). They now exercise the ASGI app directly via
FastAPI's TestClient with OLLAMA_FAKE=1 so they run hermetically in CI.
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


def test_personal_mode_api():
    payload = {
        "model": "fake",
        "message": "When is Cornelia's birthday?",
        "mode": "personal",
    }

    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    debug = data.get("debug", {})

    # Personal mode resolves the bootstrapped entity and retrieves a stored fact.
    assert debug.get("mode") == "personal"
    assert debug.get("personal_input_persisted") is True
    pc = debug.get("personal_context", {})
    assert [e["canonical_name"] for e in pc.get("resolved_entities", [])] == ["Cornelia"]
    assert len(pc.get("memories", [])) >= 1
    final_prompt = debug.get("final_prompt")
    assert isinstance(final_prompt, str) and final_prompt

    # The input was persisted; a repeat request still resolves Cornelia and returns
    # the same stored fact.
    response2 = client.post("/api/chat", json=payload)
    assert response2.status_code == 200
    pc2 = response2.json().get("debug", {}).get("personal_context", {})
    assert [e["canonical_name"] for e in pc2.get("resolved_entities", [])] == ["Cornelia"]
    assert len(pc2.get("memories", [])) >= 1
