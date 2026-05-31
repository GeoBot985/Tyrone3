import requests

def embed_text(text: str) -> list[float]:
    url = "http://localhost:11434/api/embeddings"
    payload = {
        "model": "nomic-embed-text",
        "prompt": text
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    data = response.json()
    return data.get("embedding", [])
