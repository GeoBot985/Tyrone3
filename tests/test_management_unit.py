import os
import sys
import duckdb

# Add Demo5 to path
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, init_db, delete_document, clear_corpus, get_corpus_stats, insert_document, insert_chunk

def test_management():
    db_path = "test_rag.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = get_connection(db_path)
    init_db(conn)

    # Insert a dummy document
    doc = {
        "document_id": "doc1",
        "document_name": "test.pdf",
        "source_path": "/path/to/test.pdf",
        "file_hash": "hash1",
        "file_size_bytes": 1024,
        "ingested_at": "2023-10-27T10:00:00Z",
        "chunk_count": 2
    }
    insert_document(conn, doc)

    # Insert dummy chunks
    chunk1 = {
        "chunk_id": "c1",
        "document_id": "doc1",
        "chunk_index": 0,
        "text": "Hello world",
        "embedding": [0.1] * 384
    }
    chunk2 = {
        "chunk_id": "c2",
        "document_id": "doc1",
        "chunk_index": 1,
        "text": "Goodbye world",
        "embedding": [0.2] * 384
    }
    insert_chunk(conn, chunk1)
    insert_chunk(conn, chunk2)

    # Check stats
    stats = get_corpus_stats(conn)
    assert stats["total_documents"] == 1
    assert stats["total_chunks"] == 2
    assert stats["last_ingestion_at"] == "2023-10-27T10:00:00Z"
    print("Stats check passed")

    # Delete document
    success = delete_document(conn, "doc1")
    assert success is True
    stats = get_corpus_stats(conn)
    assert stats["total_documents"] == 0
    assert stats["total_chunks"] == 0
    print("Delete document passed")

    # Re-insert and test clear
    insert_document(conn, doc)
    insert_chunk(conn, chunk1)
    clear_corpus(conn)
    stats = get_corpus_stats(conn)
    assert stats["total_documents"] == 0
    assert stats["total_chunks"] == 0
    print("Clear corpus passed")

    conn.close()
    os.remove(db_path)

if __name__ == "__main__":
    test_management()
