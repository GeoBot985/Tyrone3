from __future__ import annotations

import json

from eval.build_corpus import build_corpus, build_golden
from eval.common import DB_PATH, CORPUS_DIR, ensure_eval_dirs
from rag.db import clear_corpus, get_connection, init_db, insert_document, get_document_by_id
from rag.ingest import ingest_document


def _rekey_document(conn, old_id: str, new_id: str) -> None:
    doc = get_document_by_id(conn, old_id)
    if not doc:
        return
    doc["document_id"] = new_id
    insert_document(conn, doc)
    conn.execute("UPDATE chunks SET document_id = ? WHERE document_id = ?", [new_id, old_id])
    conn.execute("DELETE FROM documents WHERE document_id = ?", [old_id])
    # Repair the foreign key reference by inserting the stable-ID row before repointing chunks.


def build_index() -> dict[str, object]:
    ensure_eval_dirs()
    doc_index = build_corpus(overwrite=True)
    build_golden(doc_index)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = get_connection(str(DB_PATH))
    try:
        init_db(conn)
        clear_corpus(conn)

        ingested_docs: list[dict[str, object]] = []
        for entry in doc_index:
            corpus_path = CORPUS_DIR / entry["file_name"]
            expected_id = entry["doc_id"]
            result = ingest_document(str(corpus_path), conn, document_name=entry["file_name"])
            old_id = result["document_id"]
            if old_id != expected_id:
                _rekey_document(conn, old_id, expected_id)
                result["document_id"] = expected_id
            ingested_docs.append(result)

        stats = conn.execute(
            "SELECT COUNT(*) AS doc_count, COALESCE(SUM(chunk_count), 0) AS chunk_total FROM documents"
        ).fetchone()
        return {
            "db_path": str(DB_PATH),
            "documents": ingested_docs,
            "doc_count": int(stats[0]),
            "chunk_count": int(stats[1]),
        }
    finally:
        conn.close()


def main() -> int:
    result = build_index()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
