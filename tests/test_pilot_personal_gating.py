"""Pilot release gate: personal mode is opt-in and hidden by default.

Personal mode wires to the operator's own GoBook/Google/WhatsApp accounts, so the
pilot ships chat + document only. It is enabled via TYRONE_ENABLE_PERSONAL=1.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fake_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_FAKE", "1")


def test_personal_chat_rejected_when_disabled(monkeypatch):
    monkeypatch.setenv("TYRONE_ENABLE_PERSONAL", "0")
    response = client.post(
        "/api/chat",
        json={"model": "fake-model", "message": "hello", "mode": "personal"},
    )
    assert response.status_code == 403


def test_rpa_rejected_when_disabled(monkeypatch):
    monkeypatch.setenv("TYRONE_ENABLE_PERSONAL", "0")
    response = client.post("/api/rpa/list", json={"mode": "personal"})
    assert response.status_code == 403


def test_personal_option_hidden_in_ui_when_disabled(monkeypatch):
    monkeypatch.setenv("TYRONE_ENABLE_PERSONAL", "0")
    html = client.get("/").text
    assert 'value="personal"' not in html
    assert 'value="document"' in html


def test_personal_option_shown_when_enabled(monkeypatch):
    monkeypatch.setenv("TYRONE_ENABLE_PERSONAL", "1")
    html = client.get("/").text
    assert 'value="personal"' in html


def test_chat_and_document_always_available(monkeypatch):
    monkeypatch.setenv("TYRONE_ENABLE_PERSONAL", "0")
    for mode in ("chat", "document"):
        response = client.post(
            "/api/chat",
            json={"model": "fake-model", "message": "hello", "mode": mode},
        )
        assert response.status_code == 200, mode
