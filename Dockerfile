# Tyrone 3.0 — app image. Talks to an Ollama instance running on the host
# (or elsewhere) via the OLLAMA_BASE_URL env var; this image does not bundle Ollama.
FROM python:3.11-slim

# Tesseract is a system dependency for OCR (pytesseract is only the Python binding).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code.
COPY . .

# Persistent data (corpus DB, uploaded originals) lives here; mount a volume.
ENV TYRONE_DATA_DIR=/app/data \
    OLLAMA_BASE_URL=http://host.docker.internal:11434
RUN mkdir -p /app/data

EXPOSE 8000

# Bind to 0.0.0.0 so the port is reachable from the host's mapped port.
# Access stays local: only the host's published port exposes it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
