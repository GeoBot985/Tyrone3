import pytest
from app.services.session_grounding import build_session_grounding, get_session_grounding, format_grounding_for_debug
from app.config import DEFAULT_MODEL, DEFAULT_MODE, AGENT_PURPOSE

@pytest.mark.asyncio
async def test_build_session_grounding():
    # Mocking get_models is tricky without a real Ollama,
    # but build_session_grounding should still return a valid dict.
    context = await build_session_grounding()
    assert context["selected_model"] == DEFAULT_MODEL
    assert context["default_mode"] == DEFAULT_MODE
    assert context["agent_purpose"] == AGENT_PURPOSE
    assert "current_datetime" in context
    assert "timezone" in context
    assert "session_id" in context

def test_get_session_grounding():
    # After build, it should be available
    context = get_session_grounding()
    assert context is not None
    assert context["selected_model"] == DEFAULT_MODEL

def test_format_grounding_for_debug():
    context = {
        "current_datetime": "2026-04-04T14:30:00",
        "timezone": "UTC",
        "location": "unknown",
        "agent_purpose": "Test Purpose",
        "default_mode": "chat",
        "selected_model": "granite4:3b",
        "model_available": True
    }
    formatted = format_grounding_for_debug(context)
    assert "2026-04-04T14:30:00" in formatted
    assert "UTC" in formatted
    assert "Test Purpose" in formatted
    assert "granite4:3b" in formatted
    assert "Not available" not in formatted

    context["model_available"] = False
    formatted = format_grounding_for_debug(context)
    assert "WARNING: Not available" in formatted
