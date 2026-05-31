from fastapi.testclient import TestClient
import pytest
from main import app
from models import ChatRequest, ChatResponse
import asyncio

client = TestClient(app)

def test_api_session_reset():
    # Call reset session
    response = client.post("/api/session/reset")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_token_usage_chat_mode():
    # Reset session first
    client.post("/api/session/reset")

    payload = {
        "model": "granite4:3b",
        "message": "Hello, how are you?",
        "mode": "chat"
    }
    # Note: This will attempt to call Ollama. Since Ollama might not be running in the test environment,
    # we expect it to fail gracefully or we might need to mock it.
    # However, for checking token_usage structure, we just need the API to return.

    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "token_usage" in data
    usage = data["token_usage"]
    assert usage["mode"] == "chat"
    assert usage["user_input_tokens_est"] > 0
    assert usage["prompt_tokens_est"] > 0
    # response_tokens might be 0 if Ollama fails, but turn_total_tokens_est should be prompt + response
    assert usage["turn_total_tokens_est"] == usage["prompt_tokens_est"] + usage["response_tokens_est"]
    assert usage["session_turn_count"] == 1
    assert usage["session_total_tokens_est"] == usage["turn_total_tokens_est"]

def test_token_usage_accumulation():
    # Reset session first
    client.post("/api/session/reset")

    payload = {
        "model": "granite4:3b",
        "message": "First message",
        "mode": "chat"
    }

    # First turn
    resp1 = client.post("/api/chat", json=payload)
    data1 = resp1.json()
    usage1 = data1["token_usage"]

    # Second turn
    payload["message"] = "Second message"
    resp2 = client.post("/api/chat", json=payload)
    data2 = resp2.json()
    usage2 = data2["token_usage"]

    assert usage2["session_turn_count"] == 2
    assert usage2["session_prompt_tokens_est"] == usage1["prompt_tokens_est"] + usage2["prompt_tokens_est"]
    assert usage2["session_response_tokens_est"] == usage1["response_tokens_est"] + usage2["response_tokens_est"]
    assert usage2["session_total_tokens_est"] == usage1["turn_total_tokens_est"] + usage2["turn_total_tokens_est"]

def test_token_usage_reset():
    # First turn
    client.post("/api/chat", json={"model": "m", "message": "msg", "mode": "chat"})

    # Reset
    client.post("/api/session/reset")

    # Check next turn starts from 1
    resp = client.post("/api/chat", json={"model": "m", "message": "msg", "mode": "chat"})
    data = resp.json()
    usage = data["token_usage"]
    assert usage["session_turn_count"] == 1
    assert usage["session_total_tokens_est"] == usage["turn_total_tokens_est"]
