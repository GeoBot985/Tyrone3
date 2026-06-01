import os
import shutil
import sys
import uuid

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.db import get_connection, get_document_by_hash, init_db, list_documents
from rag.ingest import IngestionFailure, get_file_hash, get_file_type, ingest_document

from app.config import RAG_DB_PATH, RAG_UPLOADS_DIR, SUPPORTED_UPLOAD_TYPES_DISPLAY

PERSISTENT_UPLOAD_DIR = RAG_UPLOADS_DIR


def _build_persistent_copy_path(source_path: str) -> str:
    os.makedirs(PERSISTENT_UPLOAD_DIR, exist_ok=True)
    filename = os.path.basename(source_path)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    return os.path.join(PERSISTENT_UPLOAD_DIR, unique_name)


def ingest_file(path: str, document_name: str | None = None) -> dict:
    """
    Returns:
    {
        "ok": bool,
        "path": str,
        "document_name": str,
        "status": "success" | "failed" | "skipped",
        "document_id": str | None,
        "chunks_indexed": int,
        "error": str | None,
        "reason": str | None
    }
    """
    display_name = document_name or os.path.basename(path)
    result = {
        "ok": False,
        "path": path,
        "document_name": display_name,
        "status": "failed",
        "document_id": None,
        "chunks_indexed": 0,
        "error": None,
        "reason": None,
    }

    if not os.path.exists(path):
        result["error"] = "Selected file does not exist."
        return result

    db_path = RAG_DB_PATH

    try:
        conn = get_connection(db_path)
        init_db(conn)

        # Optional Duplicate Detection
        file_hash = get_file_hash(path)
        existing_doc = get_document_by_hash(conn, file_hash)
        if existing_doc:
            result["ok"] = True
            result["status"] = "skipped"
            result["reason"] = "duplicate"
            result["document_id"] = existing_doc["document_id"]
            result["chunks_indexed"] = existing_doc["chunk_count"]
            result["provenance"] = {
                "status": "duplicate_skipped",
                "document_id": existing_doc["document_id"],
                "existing_chunk_count": existing_doc["chunk_count"],
                "file_type": existing_doc.get("file_type"),
                "ingestion_method": existing_doc.get("ingestion_method"),
                "primary_extractor": existing_doc.get("primary_extractor"),
                "ocr_used": existing_doc.get("ocr_used", False),
            }
            return result

        persistent_path = _build_persistent_copy_path(path)
        shutil.copy2(path, persistent_path)

        try:
            ingest_result = ingest_document(
                persistent_path,
                conn,
                document_name=display_name,
            )
        except Exception:
            if os.path.exists(persistent_path):
                os.remove(persistent_path)
            raise

        result["ok"] = True
        result["status"] = "success"
        result["document_name"] = ingest_result.get("document_name", display_name)
        result["document_id"] = ingest_result.get("document_id")
        result["chunks_indexed"] = ingest_result.get("chunk_count", 0)
        result["path"] = ingest_result.get("source_path", persistent_path)
        result["ocr_used"] = ingest_result.get("ocr_used", False)
        result["ocr_char_count"] = ingest_result.get("ocr_char_count", 0)
        result["ocr_page_count"] = ingest_result.get("ocr_page_count", 0)
        result["ingestion_method"] = ingest_result.get("ingestion_method", "markitdown")
        result["file_type"] = ingest_result.get("file_type", "unknown")
        result["timings"] = ingest_result.get("timings", {})
        result["failed_pages"] = ingest_result.get("failed_pages", [])
        result["max_workers"] = ingest_result.get("max_workers")
        result["provenance"] = ingest_result.get("provenance", {})

    except Exception as e:
        provenance = e.provenance if isinstance(e, IngestionFailure) else {}
        error_str = str(e)
        ext = os.path.splitext(path)[1].lower()
        file_type_label = get_file_type(path).upper()
        if "no extractable text" in error_str.lower() or "no non-empty chunks" in error_str.lower():
            if ext in {".docx", ".pptx", ".xlsx", ".xls", ".csv", ".txt", ".md"}:
                result["error"] = f"No extractable text was found in this {file_type_label} file."
            else:
                result["error"] = "No extractable text was found in this PDF."
        elif "legacy .xls spreadsheets are not yet supported" in error_str.lower():
            result["error"] = (
                "Legacy .xls spreadsheets are not yet supported. Please save as .xlsx and retry."
            )
        elif "failed to read xlsx workbook" in error_str.lower():
            result["error"] = "Failed to read XLSX workbook."
        elif "xlsx workbook contained no extractable rows" in error_str.lower():
            result["error"] = "XLSX workbook contained no extractable rows."
        elif "xlsx workbook could not identify any usable sheets" in error_str.lower():
            result["error"] = "XLSX workbook could not identify any usable sheets."
        elif (
            "fitz" in error_str.lower()
            or "pdf" in error_str.lower()
            and "read" in error_str.lower()
        ):
            result["error"] = "Failed to read PDF."
        elif "unsupported file type" in error_str.lower():
            result["error"] = (
                f"Unsupported file type. Supported types: {SUPPORTED_UPLOAD_TYPES_DISPLAY}"
            )
        elif "extraction failed with markitdown" in error_str.lower():
            result["error"] = "Failed to read document."
        elif "docx" in error_str.lower() and "read" in error_str.lower():
            result["error"] = "Failed to read document."
        elif "embed" in error_str.lower() or "ollama" in error_str.lower():
            result["error"] = "Failed to generate embeddings."
        elif (
            "sql" in error_str.lower()
            or "database" in error_str.lower()
            or "duckdb" in error_str.lower()
        ):
            result["error"] = "Failed to store document in knowledge base."
        else:
            result["error"] = f"Ingestion failed: {error_str}"

        if provenance:
            provenance["status"] = "failed"
            result["provenance"] = provenance
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return result


def ingest_pdf_file(path: str, document_name: str | None = None) -> dict:
    return ingest_file(path, document_name)


def get_indexed_docs() -> list[str]:
    """Returns a list of unique document IDs currently in the database."""
    db_path = RAG_DB_PATH
    if not os.path.exists(db_path):
        return []

    docs = []
    try:
        conn = get_connection(db_path)
        # Check if table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        if any(t[0] == "documents" for t in tables):
            doc_records = list_documents(conn)
            docs = [d["document_id"] for d in doc_records]
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return docs
