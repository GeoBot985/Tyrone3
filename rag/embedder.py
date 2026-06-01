from __future__ import annotations

import hashlib
import os

import requests


def embed_text(text: str) -> list[float]:
    if os.environ.get("OLLAMA_FAKE"):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < 384:
            for byte in digest:
                values.append(byte / 255.0)
                if len(values) >= 384:
                    break
        return values

    url = "http://localhost:11434/api/embeddings"
    payload = {"model": "nomic-embed-text", "prompt": text}

    response = requests.post(url, json=payload)
    response.raise_for_status()

    data = response.json()
    return data.get("embedding", [])
