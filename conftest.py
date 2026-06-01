from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import uvicorn


@pytest.fixture
def temp_rag_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_rag.db"
    monkeypatch.setenv("TYRONE_RAG_DB_PATH", str(db_path))

    import app.config as app_config
    import app.services.ingest_service as ingest_service
    import app.services.personal_service as personal_service
    import app.services.rag_service as rag_service
    import rag.db as rag_db
    import rag.personal_db as rag_personal_db

    for module in (
        app_config,
        rag_service,
        rag_db,
        rag_personal_db,
        ingest_service,
        personal_service,
    ):
        if hasattr(module, "DB_PATH"):
            monkeypatch.setattr(module, "DB_PATH", str(db_path), raising=False)
        if hasattr(module, "RAG_DB_PATH"):
            monkeypatch.setattr(module, "RAG_DB_PATH", str(db_path), raising=False)

    conn = rag_personal_db.get_connection(str(db_path))
    try:
        rag_personal_db.init_personal_db(conn)
        rag_personal_db.bootstrap_personal_data(conn)
    finally:
        conn.close()

    return Path(db_path)


@pytest.fixture(autouse=True)
def isolate_rag_db(temp_rag_db):
    yield temp_rag_db


@pytest.fixture(scope="session", autouse=True)
def api_server():
    config = uvicorn.Config("main:app", host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield
    server.should_exit = True
    thread.join(timeout=5)
