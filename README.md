# Tyrone 3.0

## Prerequisites

- Python 3.10+
- Ollama running locally on `http://localhost:11434`
- At least one model pulled in Ollama, for example `ollama run qwen2.5-coder:7b`

## Setup

1. Create and activate a virtual environment.

```bash
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Start the app from this folder.

```bash
python main.py
```

4. Open `http://127.0.0.1:8000`.

## Notes

- The app now resolves `templates`, `static`, uploads, and DuckDB files from the project root, so it runs correctly after being moved into its own folder.
- Runtime data is stored under this folder in `temp_uploads/`, `rag_uploads/`, and `rag_v2.db`.
