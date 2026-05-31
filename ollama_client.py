import httpx
from typing import List, Dict, Any, Tuple
import json

OLLAMA_BASE_URL = "http://localhost:11434"
CHAT_TIMEOUT_SECONDS = 300.0

async def get_models() -> Tuple[List[str], str]:
    """Fetches available local models from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            return models, ""
    except httpx.ConnectError:
        return [], "Ollama is not running or unreachable at localhost:11434."
    except Exception as e:
        return [], f"Error fetching models: {str(e)}"

async def chat(model: str, message: str, temperature: float = 0.1) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Sends a chat request to Ollama.
    Returns (response_data, request_summary, error_message).
    """
    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    request_summary = {
        "endpoint": "/api/chat",
        "payload": request_payload
    }

    try:
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=request_payload)
            response.raise_for_status()
            data = response.json()
            return data, request_summary, ""
    except httpx.ConnectError:
        return {}, request_summary, "Ollama is not running or unreachable at localhost:11434."
    except httpx.TimeoutException:
        return {}, request_summary, "Ollama request timed out after 5 minutes."
    except Exception as e:
        return {}, request_summary, f"Ollama request failed: {str(e)}"
