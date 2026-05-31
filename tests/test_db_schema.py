import sys
import os
import duckdb

# Add Demo5 root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, init_db, insert_document, list_documents

def test_db_schema():
    db_path = "test_rag_v2.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = get_connection(db_path)
    init_db(conn)

    doc = {
        "document_id": "test-id",
        "document_name": "test-doc",
        "source_path": "/path/to/test.pdf",
        "file_hash": "hash",
        "file_size_bytes": 1000,
        "ingested_at": "2023-01-01T00:00:00",
        "chunk_count": 5,
        "ingestion_method": "ocr",
        "file_type": "pdf",
        "primary_extractor": "markitdown",
        "fallback_extractor": "ocr",
        "failure_stage": None,
        "failure_reason": None,
        "raw_text_char_count": 5100,
        "normalized_text_char_count": 5000,
        "extraction_details_json": "{\"layout_mode\":\"plain\"}",
        "ocr_used": True,
        "ocr_char_count": 5000
    }

    insert_document(conn, doc)

    docs = list_documents(conn)
    assert len(docs) == 1
    assert docs[0]["ingestion_method"] == "ocr"
    assert docs[0]["primary_extractor"] == "markitdown"
    assert docs[0]["fallback_extractor"] == "ocr"
    assert docs[0]["raw_text_char_count"] == 5100
    assert docs[0]["normalized_text_char_count"] == 5000
    assert docs[0]["extraction_details_json"] == "{\"layout_mode\":\"plain\"}"
    assert docs[0]["ocr_used"] == True
    assert docs[0]["ocr_char_count"] == 5000

    print("test_db_schema passed")
    conn.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_db_schema()
