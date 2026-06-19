"""HTTP-level coverage for the DELETE /api/docs/{document_id} endpoint.

Covers the 204-on-success and 404-on-missing semantics added in main.py; the
underlying rag.db.delete_document cascade is covered by the unit tests.
"""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def _ingest_txt(name: str = "delete_me.txt", body: str = "Alpha Beta Gamma\nDelta Epsilon\n") -> str:
    resp = client.post(
        "/api/ingest",
        files={"file": (name, BytesIO(body.encode()), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    doc_id = resp.json()["document_id"]
    assert doc_id, resp.text
    return doc_id


def test_delete_document_returns_204_and_removes_it():
    doc_id = _ingest_txt()

    listed = client.get("/api/docs").json()
    assert any(d["document_id"] == doc_id for d in listed["documents"])

    delete = client.delete(f"/api/docs/{doc_id}")
    assert delete.status_code == 204
    assert delete.content == b""

    listed = client.get("/api/docs").json()
    assert not any(d["document_id"] == doc_id for d in listed["documents"])


def test_delete_missing_document_returns_404():
    delete = client.delete("/api/docs/does-not-exist")
    assert delete.status_code == 404
    body = delete.json()
    assert body["ok"] is False
    assert body["deleted"] is False
    assert "not found" in body["error"].lower()
