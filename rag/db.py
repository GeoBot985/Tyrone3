import struct

import duckdb
from app.config import RAG_DB_PATH


def _rows_to_dicts(cursor) -> list[dict]:
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def _row_to_dict(cursor) -> dict | None:
    row = cursor.fetchone()
    if not row:
        return None
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


def get_connection(db_path=RAG_DB_PATH):
    return duckdb.connect(db_path)


def init_db(conn):
    # New normalized schema
    conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        document_name TEXT NOT NULL,
        source_path TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        file_size_bytes BIGINT NOT NULL,
        ingested_at TEXT NOT NULL,
        chunk_count INTEGER NOT NULL,
        ingestion_method TEXT DEFAULT 'text',
        file_type TEXT DEFAULT 'pdf',
        primary_extractor TEXT,
        fallback_extractor TEXT,
        failure_stage TEXT,
        failure_reason TEXT,
        raw_text_char_count INTEGER DEFAULT 0,
        normalized_text_char_count INTEGER DEFAULT 0,
        extraction_details_json TEXT,
        ocr_used BOOLEAN DEFAULT FALSE,
        ocr_char_count INTEGER DEFAULT 0,
        ocr_page_count INTEGER DEFAULT 0
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        region_type TEXT,
        sheet_name TEXT,
        row_index INTEGER,
        cell_range TEXT,
        embedding BLOB NOT NULL,
        FOREIGN KEY(document_id) REFERENCES documents(document_id)
    );
    """)

    # Migration for existing databases
    existing_cols_info = conn.execute("PRAGMA table_info('documents')").fetchall()
    col_names = [c[1] for c in existing_cols_info]
    if "ingestion_method" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ingestion_method TEXT DEFAULT 'text'")
    if "file_type" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN file_type TEXT DEFAULT 'pdf'")
    if "primary_extractor" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN primary_extractor TEXT")
    if "fallback_extractor" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN fallback_extractor TEXT")
    if "failure_stage" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN failure_stage TEXT")
    if "failure_reason" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN failure_reason TEXT")
    if "raw_text_char_count" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN raw_text_char_count INTEGER DEFAULT 0")
    if "normalized_text_char_count" not in col_names:
        conn.execute(
            "ALTER TABLE documents ADD COLUMN normalized_text_char_count INTEGER DEFAULT 0"
        )
    if "extraction_details_json" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN extraction_details_json TEXT")
    if "ocr_used" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_used BOOLEAN DEFAULT FALSE")
    if "ocr_char_count" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_char_count INTEGER DEFAULT 0")
    if "ocr_page_count" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_page_count INTEGER DEFAULT 0")

    existing_chunk_cols_info = conn.execute("PRAGMA table_info('chunks')").fetchall()
    chunk_col_names = [c[1] for c in existing_chunk_cols_info]
    if "region_type" not in chunk_col_names:
        conn.execute("ALTER TABLE chunks ADD COLUMN region_type TEXT")
    if "sheet_name" not in chunk_col_names:
        conn.execute("ALTER TABLE chunks ADD COLUMN sheet_name TEXT")
    if "row_index" not in chunk_col_names:
        conn.execute("ALTER TABLE chunks ADD COLUMN row_index INTEGER")
    if "cell_range" not in chunk_col_names:
        conn.execute("ALTER TABLE chunks ADD COLUMN cell_range TEXT")


def insert_document(conn, doc: dict) -> None:
    conn.execute(
        """
        INSERT INTO documents (
            document_id, document_name, source_path, file_hash,
            file_size_bytes, ingested_at, chunk_count,
            ingestion_method, file_type, primary_extractor, fallback_extractor,
            failure_stage, failure_reason, raw_text_char_count, normalized_text_char_count,
            extraction_details_json, ocr_used, ocr_char_count, ocr_page_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            doc["document_id"],
            doc["document_name"],
            doc["source_path"],
            doc["file_hash"],
            doc["file_size_bytes"],
            doc["ingested_at"],
            doc["chunk_count"],
            doc.get("ingestion_method", "text"),
            doc.get("file_type", "pdf"),
            doc.get("primary_extractor"),
            doc.get("fallback_extractor"),
            doc.get("failure_stage"),
            doc.get("failure_reason"),
            doc.get("raw_text_char_count", 0),
            doc.get("normalized_text_char_count", 0),
            doc.get("extraction_details_json"),
            doc.get("ocr_used", False),
            doc.get("ocr_char_count", 0),
            doc.get("ocr_page_count", 0),
        ],
    )


def insert_chunk(conn, chunk: dict) -> None:
    # Convert list of floats to binary format for BLOB storage
    embedding = chunk["embedding"]
    blob_data = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        """
        INSERT INTO chunks (
            chunk_id, document_id, chunk_index, text, region_type, sheet_name, row_index, cell_range, embedding
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            chunk["chunk_id"],
            chunk["document_id"],
            chunk["chunk_index"],
            chunk["text"],
            chunk.get("region_type"),
            chunk.get("sheet_name"),
            chunk.get("row_index"),
            chunk.get("cell_range"),
            blob_data,
        ],
    )


def list_documents(conn) -> list[dict]:
    cursor = conn.execute("SELECT * FROM documents ORDER BY ingested_at DESC")
    return _rows_to_dicts(cursor)


def delete_document(conn, document_id: str) -> bool:
    # Manual cascade: DuckDB's ON DELETE CASCADE support varies across versions, so we
    # delete child rows explicitly. We deliberately do NOT wrap this in a single
    # transaction: DuckDB (1.4.x) validates the parent-side foreign key against the
    # pre-transaction snapshot, so deleting the documents row inside an explicit txn
    # still reports the just-deleted chunks as referencing it (ConstraintException).
    # Running the statements in autocommit avoids that. Order is chunks-then-documents:
    # the FK makes deleting documents-first impossible, and the only reachable
    # intermediate state on a mid-sequence failure is orphaned chunks (no parent),
    # which the FK prevents from being reintroduced. Returns True only when a documents
    # row was actually removed.
    existing = conn.execute(
        "SELECT 1 FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if existing is None:
        return False
    conn.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
    conn.execute("DELETE FROM documents WHERE document_id = ?", [document_id])
    return True


def clear_corpus(conn) -> None:
    # Delete child rows before parent rows. As with delete_document, this is not wrapped
    # in an explicit transaction because DuckDB's foreign-key validation does not see
    # in-transaction child deletes when checking the parent delete, which would raise a
    # spurious ConstraintException. Autocommit per statement is correct here.
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM documents")


def get_corpus_stats(conn) -> dict:
    doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    last_ingestion = conn.execute("SELECT MAX(ingested_at) FROM documents").fetchone()[0]

    return {
        "total_documents": doc_count,
        "total_chunks": chunk_count,
        "last_ingestion_at": last_ingestion,
    }


def get_document_by_id(conn, document_id: str) -> dict | None:
    cursor = conn.execute("SELECT * FROM documents WHERE document_id = ?", [document_id])
    return _row_to_dict(cursor)


def get_document_by_hash(conn, file_hash: str) -> dict | None:
    cursor = conn.execute("SELECT * FROM documents WHERE file_hash = ?", [file_hash])
    return _row_to_dict(cursor)


def get_all_embeddings(conn, document_ids: list[str] | None = None):
    query = """
        SELECT
            c.text, c.embedding, c.chunk_index, c.region_type, c.sheet_name, c.row_index, c.cell_range,
            d.document_id, d.document_name, d.ingested_at
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
    """
    params = []
    if document_ids:
        placeholders = ",".join(["?"] * len(document_ids))
        query += f" WHERE d.document_id IN ({placeholders})"
        params = document_ids

    results = conn.execute(query, params).fetchall()

    parsed_results = []
    for (
        text,
        blob,
        chunk_index,
        region_type,
        sheet_name,
        row_index,
        cell_range,
        doc_id,
        doc_name,
        ingested_at,
    ) in results:
        # Convert blob back to list of floats
        num_floats = len(blob) // 4  # 4 bytes per float32
        embedding = list(struct.unpack(f"{num_floats}f", blob))
        parsed_results.append(
            {
                "text": text,
                "embedding": embedding,
                "chunk_index": chunk_index,
                "region_type": region_type,
                "sheet_name": sheet_name,
                "row_index": row_index,
                "cell_range": cell_range,
                "document_id": doc_id,
                "document_name": doc_name,
                "ingested_at": ingested_at,
            }
        )

    return parsed_results


def find_exact_chunk(
    conn,
    document_id: str,
    chunk_index: int,
    text: str,
) -> dict | None:
    result = conn.execute(
        """
        SELECT
            c.chunk_id,
            c.document_id,
            c.chunk_index,
            c.text,
            c.region_type,
            c.sheet_name,
            c.row_index,
            c.cell_range,
            d.document_name,
            d.ingested_at
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.document_id = ?
          AND c.chunk_index = ?
          AND c.text = ?
        LIMIT 1
        """,
        [document_id, chunk_index, text],
    ).fetchone()

    if not result:
        return None

    cols = [
        "chunk_id",
        "document_id",
        "chunk_index",
        "text",
        "region_type",
        "sheet_name",
        "row_index",
        "cell_range",
        "document_name",
        "ingested_at",
    ]
    return dict(zip(cols, result))


def get_all_chunks_for_document(conn, document_id: str) -> list[dict]:
    results = conn.execute(
        """
        SELECT chunk_id, document_id, chunk_index, text, region_type, sheet_name, row_index, cell_range
        FROM chunks
        WHERE document_id = ?
        ORDER BY chunk_index ASC
    """,
        [document_id],
    ).fetchall()

    cols = [
        "chunk_id",
        "document_id",
        "chunk_index",
        "text",
        "region_type",
        "sheet_name",
        "row_index",
        "cell_range",
    ]
    return [dict(zip(cols, r)) for r in results]
