from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import chat_orchestrator as co
from app.services import ingest_service
from models import ChatRequest
from rag import ingest as rag_ingest
from rag import db as rag_db


class _FakeConn:
    def close(self) -> None:
        return None


def test_ingest_service_success_duplicate_and_indexed_docs(tmp_path, monkeypatch):
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(ingest_service, "get_connection", lambda *_: _FakeConn())
    monkeypatch.setattr(ingest_service, "init_db", lambda *_: None)
    monkeypatch.setattr(ingest_service, "get_file_hash", lambda *_: "hash-1")
    monkeypatch.setattr(ingest_service.shutil, "copy2", lambda *_args, **_kwargs: None)

    duplicate_doc = {
        "document_id": "doc-dup",
        "chunk_count": 7,
        "file_type": "txt",
        "ingestion_method": "markitdown",
        "primary_extractor": "markitdown",
        "ocr_used": False,
    }
    monkeypatch.setattr(ingest_service, "get_document_by_hash", lambda *_: duplicate_doc)
    duplicate = ingest_service.ingest_file(str(sample))
    assert duplicate["status"] == "skipped"
    assert duplicate["reason"] == "duplicate"
    assert duplicate["document_id"] == "doc-dup"

    monkeypatch.setattr(ingest_service, "get_document_by_hash", lambda *_: None)
    monkeypatch.setattr(
        ingest_service,
        "ingest_document",
        lambda *_args, **_kwargs: {
            "document_name": "sample.txt",
            "document_id": "doc-new",
            "chunk_count": 3,
            "source_path": str(sample),
            "ocr_used": True,
            "ocr_char_count": 11,
            "ocr_page_count": 1,
            "ingestion_method": "markitdown+ocr_fallback",
            "file_type": "txt",
            "timings": {"total": 1.0},
            "failed_pages": [],
            "max_workers": 2,
            "provenance": {"status": "success"},
        },
    )
    success = ingest_service.ingest_file(str(sample), document_name="sample.txt")
    assert success["ok"] is True
    assert success["status"] == "success"
    assert success["document_id"] == "doc-new"
    assert success["chunks_indexed"] == 3

    monkeypatch.setattr(ingest_service, "RAG_DB_PATH", str(tmp_path / "indexed.db"))
    db_path = Path(ingest_service.RAG_DB_PATH)
    conn = rag_db.get_connection(str(db_path))
    rag_db.init_db(conn)
    rag_db.insert_document(
        conn,
        {
            "document_id": "doc-a",
            "document_name": "Doc A",
            "source_path": "x",
            "file_hash": "hash-a",
            "file_size_bytes": 1,
            "ingested_at": "2026-01-01T00:00:00",
            "chunk_count": 1,
        },
    )
    conn.close()
    monkeypatch.setattr(ingest_service, "get_connection", rag_db.get_connection)
    indexed = ingest_service.get_indexed_docs()
    assert indexed == ["doc-a"]


@pytest.mark.parametrize(
    ("filename", "message", "expected_error"),
    [
        ("missing.docx", "no extractable text was found", "No extractable text was found in this DOCX file."),
        ("missing.pdf", "no extractable text was found", "No extractable text was found in this PDF."),
        (
            "legacy.xls",
            "Legacy .xls spreadsheets are not yet supported. Please save as .xlsx and retry.",
            "Legacy .xls spreadsheets are not yet supported. Please save as .xlsx and retry.",
        ),
        ("bad.xlsx", "Failed to read XLSX workbook: boom", "Failed to read XLSX workbook."),
        ("empty.xlsx", "XLSX workbook contained no extractable rows.", "XLSX workbook contained no extractable rows."),
        (
            "nosheets.xlsx",
            "XLSX workbook could not identify any usable sheets.",
            "XLSX workbook could not identify any usable sheets.",
        ),
        ("bad.pdf", "fitz error", "Failed to read PDF."),
        (
            "file.bin",
            "Unsupported file type: .bin",
            "Unsupported file type. Supported types: PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, MD.",
        ),
        ("doc.txt", "extraction failed with markitdown", "Failed to read document."),
        ("doc.docx", "DOCX read failed", "Failed to read document."),
        ("doc.txt", "embed layer failed", "Failed to generate embeddings."),
        ("doc.txt", "duckdb database error", "Failed to store document in knowledge base."),
        ("doc.txt", "some odd failure", "Ingestion failed: some odd failure"),
    ],
)
def test_ingest_service_error_mapping(tmp_path, monkeypatch, filename, message, expected_error):
    path = tmp_path / filename
    path.write_text("content", encoding="utf-8")

    monkeypatch.setattr(ingest_service, "get_connection", lambda *_: _FakeConn())
    monkeypatch.setattr(ingest_service, "init_db", lambda *_: None)
    monkeypatch.setattr(ingest_service, "get_file_hash", lambda *_: "hash-1")
    monkeypatch.setattr(ingest_service, "get_document_by_hash", lambda *_: None)
    monkeypatch.setattr(ingest_service.shutil, "copy2", lambda *_args, **_kwargs: None)

    def boom(*_args, **_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(ingest_service, "ingest_document", boom)
    result = ingest_service.ingest_file(str(path))
    assert result["ok"] is False
    assert result["error"] == expected_error


def test_ingest_service_inception_failure_provenance(tmp_path, monkeypatch):
    path = tmp_path / "source.txt"
    path.write_text("content", encoding="utf-8")
    provenance = {"status": "in_progress", "document_id": "doc-1"}

    monkeypatch.setattr(ingest_service, "get_connection", lambda *_: _FakeConn())
    monkeypatch.setattr(ingest_service, "init_db", lambda *_: None)
    monkeypatch.setattr(ingest_service, "get_file_hash", lambda *_: "hash-1")
    monkeypatch.setattr(ingest_service, "get_document_by_hash", lambda *_: None)
    monkeypatch.setattr(ingest_service.shutil, "copy2", lambda *_args, **_kwargs: None)

    def boom(*_args, **_kwargs):
        raise rag_ingest.IngestionFailure("embed pipeline failed", provenance)

    monkeypatch.setattr(ingest_service, "ingest_document", boom)
    result = ingest_service.ingest_file(str(path))
    assert result["error"] == "Failed to generate embeddings."
    assert result["provenance"]["status"] == "failed"


def test_rag_ingest_helpers_and_extract_branches(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("abcdef", encoding="utf-8")
    assert rag_ingest.get_file_extension(str(source)) == ".txt"
    assert rag_ingest.get_file_type(str(source)) == "txt"
    assert rag_ingest.is_supported_upload_extension(".txt") is True
    assert rag_ingest.is_supported_upload_extension(".zzz") is False
    assert rag_ingest.chunk_text("abcdefghij", chunk_size=4, overlap=1) == ["abcd", "defg", "ghij"]
    assert rag_ingest._normalize_extracted_text("  a \n\n b ") == "a\nb"
    assert rag_ingest.get_file_hash(str(source))
    assert rag_ingest._embed_chunk((0, "", "doc", {})) is None

    monkeypatch.setattr(rag_ingest, "embed_text", lambda text: [1.0, 0.0, 0.0])
    embedded = rag_ingest._embed_chunk((1, "chunk text", "doc", {"region_type": "table_row"}))
    assert embedded["document_id"] == "doc"
    assert embedded["region_type"] == "table_row"

    monkeypatch.setattr(
        rag_ingest,
        "extract_xlsx_structured",
        lambda *_: {
            "success": True,
            "text": "Header: Value",
            "sheet_count": 1,
            "sheet_names": ["Sheet1"],
            "row_count": 1,
            "header_detection_used": True,
            "header_detection_warnings": [],
            "skipped_objects": [],
            "column_count_by_sheet": {"Sheet1": 2},
            "sheets": [],
            "warnings": [],
            "region_counts": {"table_row": 1},
            "row_records": [{"text": "Header: Value", "region_type": "table_row"}],
        },
    )
    prov = rag_ingest._build_provenance("xlsx")
    xlsx = rag_ingest._extract_text_for_ingestion(str(source), ".xlsx", rag_ingest.IngestionTimings(), prov)
    assert xlsx["ingestion_method"] == "openpyxl_structured"

    monkeypatch.setattr(
        rag_ingest,
        "extract_xlsx_structured",
        lambda *_: {"success": False, "error": "workbook exploded"},
    )
    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest._extract_text_for_ingestion(str(source), ".xlsx", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("xlsx"))

    monkeypatch.setattr(
        rag_ingest,
        "extract_docx_structured",
        lambda *_: {
            "success": True,
            "text": "Doc body",
            "paragraph_count": 1,
            "table_count": 0,
            "table_row_count": 0,
            "blocks": [{"text": "Doc body"}],
            "warnings": [],
            "region_counts": {"table_row": 0},
        },
    )
    docx = rag_ingest._extract_text_for_ingestion(str(source), ".docx", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("docx"))
    assert docx["ingestion_method"] == "python_docx_structured"

    monkeypatch.setattr(
        rag_ingest,
        "extract_docx_structured",
        lambda *_: {"success": True, "text": "", "paragraph_count": 0, "table_count": 0, "table_row_count": 0, "blocks": [], "warnings": [], "region_counts": {}},
    )
    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest._extract_text_for_ingestion(str(source), ".docx", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("docx"))

    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest._extract_text_for_ingestion(str(source), ".xls", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("xls"))


def test_rag_ingest_pdf_and_markitdown_branches(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_text("pdf", encoding="utf-8")

    monkeypatch.setattr(rag_ingest, "ENABLE_MARKITDOWN", False)
    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest._extract_text_for_ingestion(str(source), ".txt", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("txt"))

    monkeypatch.setattr(rag_ingest, "ENABLE_MARKITDOWN", True)
    monkeypatch.setattr(rag_ingest, "is_scanned_pdf", lambda _length: False)
    monkeypatch.setattr(
        rag_ingest,
        "extract_with_markitdown",
        lambda *_: {"success": True, "text": "Paragraph one"},
    )
    normal = rag_ingest._extract_text_for_ingestion(str(source), ".pdf", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("pdf"))
    assert normal["ingestion_method"] == "markitdown"

    monkeypatch.setattr(rag_ingest, "is_scanned_pdf", lambda _length: True)
    monkeypatch.setattr(
        rag_ingest,
        "extract_with_markitdown",
        lambda *_: {"success": True, "text": "scan"},
    )
    monkeypatch.setattr(
        rag_ingest,
        "extract_text_with_ocr",
        lambda *_args, **_kwargs: {
            "error": None,
            "text": "OCR text",
            "ocr_char_count": 8,
            "ocr_page_count": 1,
            "failed_pages": [],
            "granular_timings": {"ocr": 1.0},
        },
    )
    fallback = rag_ingest._extract_text_for_ingestion(str(source), ".pdf", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("pdf"))
    assert fallback["ingestion_method"] == "markitdown+ocr_fallback"
    assert fallback["ocr_used"] is True

    monkeypatch.setattr(
        rag_ingest,
        "extract_text_with_ocr",
        lambda *_args, **_kwargs: {
            "error": "OCR failed",
            "text": "",
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "failed_pages": [],
        },
    )
    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest._extract_text_for_ingestion(str(source), ".pdf", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("pdf"))

    monkeypatch.setattr(
        rag_ingest,
        "extract_with_markitdown",
        lambda *_: {"success": True, "text": "This is plain text"},
    )
    txt = rag_ingest._extract_text_for_ingestion(str(source), ".txt", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("txt"))
    assert txt["ingestion_method"] == "markitdown"

    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest._extract_text_for_ingestion(str(source), ".zzz", rag_ingest.IngestionTimings(), rag_ingest._build_provenance("zzz"))


def test_rag_ingest_document_success_and_failures(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_text("hello world", encoding="utf-8")

    class _PdfDoc:
        def __len__(self):
            return 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(rag_ingest.fitz, "open", lambda *_: _PdfDoc())
    monkeypatch.setattr(
        rag_ingest,
        "_extract_text_for_ingestion",
        lambda *_args, **_kwargs: {
            "text": "Alpha Beta",
            "structured_chunks": [
                {"text": "Alpha Beta", "region_type": "table_row", "sheet_name": None, "row_index": None, "cell_range": None}
            ],
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "ingestion_method": "markitdown",
            "file_type": "pdf",
            "failed_pages": [],
            "raw_text_char_count": 10,
            "normalized_text_char_count": 10,
        },
    )
    monkeypatch.setattr(
        rag_ingest,
        "normalize_layout_aware_text",
        lambda text, _file_type: {"text": text, "applied": False, "layout_mode": "simple", "warnings": [], "heuristic": "none"},
    )
    monkeypatch.setattr(rag_ingest, "embed_text", lambda _text: [1.0, 0.0, 0.0])

    written = []

    def record_document(_conn, doc):
        written.append(("document", doc))

    def record_chunk(_conn, chunk):
        written.append(("chunk", chunk))

    monkeypatch.setattr(rag_ingest, "insert_document", record_document)
    monkeypatch.setattr(rag_ingest, "insert_chunk", record_chunk)

    doc = rag_ingest.ingest_document(str(source), _FakeConn(), document_name="Source PDF")
    assert doc["document_name"] == "Source PDF"
    assert doc["chunk_count"] == 1
    assert doc["provenance"]["status"] == "success"
    assert written[0][0] == "document"
    assert written[1][0] == "chunk"

    with pytest.raises(FileNotFoundError):
        rag_ingest.ingest_document(str(tmp_path / "missing.pdf"), _FakeConn())

    monkeypatch.setattr(
        rag_ingest.fitz,
        "open",
        lambda *_: (_ for _ in ()).throw(RuntimeError("failed to open pdf")),
    )
    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest.ingest_document(str(source), _FakeConn())

    monkeypatch.setattr(rag_ingest.fitz, "open", lambda *_: _PdfDoc())
    monkeypatch.setattr(
        rag_ingest,
        "_extract_text_for_ingestion",
        lambda *_args, **_kwargs: {
            "text": "",
            "structured_chunks": [],
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "ingestion_method": "markitdown",
            "file_type": "pdf",
            "failed_pages": [],
            "raw_text_char_count": 0,
            "normalized_text_char_count": 0,
        },
    )
    with pytest.raises(rag_ingest.IngestionFailure):
        rag_ingest.ingest_document(str(source), _FakeConn())


@pytest.mark.asyncio
async def test_prepare_mode_state_document_personal_workspace_and_chat(monkeypatch):
    monkeypatch.setattr(
        co,
        "rpa_list",
        lambda *_args, **_kwargs: ["2026-06-05 / 18:00-19:00 / Court 1"],
    )
    async def fake_rpa_open_courts(*_args, **_kwargs):
        return ["Court 2"]

    async def fake_rpa_list(*_args, **_kwargs):
        return ["2026-06-05 / 18:00-19:00 / Court 1"]

    async def fake_rpa_book(*_args, **_kwargs):
        return {"selection": "Court 1 / 18:00-19:00"}

    async def fake_rpa_cancel(*_args, **_kwargs):
        return {"ok": True}

    async def fake_dispatch_workspace_intent(*_args, **_kwargs):
        return "workspace reply"

    monkeypatch.setattr(co, "rpa_list", fake_rpa_list)
    monkeypatch.setattr(co, "rpa_open_courts", fake_rpa_open_courts)
    monkeypatch.setattr(
        co,
        "rpa_book",
        fake_rpa_book,
    )
    monkeypatch.setattr(co, "rpa_cancel", fake_rpa_cancel)
    monkeypatch.setattr(co, "dispatch_workspace_intent", fake_dispatch_workspace_intent)

    document_request = ChatRequest(model="fake-model", message="show me the report", mode="document")
    empty = await co.prepare_mode_state(
        document_request,
        session_id="s1",
        get_rag_context_fn=lambda *_args, **_kwargs: {
            "error": None,
            "chunks": [],
            "metrics": {"coverage_mode": "narrow_lookup", "coverage_truncated": False},
        },
    )
    assert empty["skip_llm"] is True
    assert empty["reply_text"] == "Insufficient information"
    assert empty["confidence_payload"]["label"] == "low"

    filled = await co.prepare_mode_state(
        document_request,
        session_id="s2",
        get_rag_context_fn=lambda *_args, **_kwargs: {
            "error": None,
            "chunks": [
                {"text": "Alpha", "score": 0.8, "lexical_score": 0.7},
                {"text": "Beta", "score": 0.7, "lexical_score": 0.6},
            ],
            "chunks_for_prompt": [
                {"text": "Alpha", "score": 0.8, "lexical_score": 0.7},
                {"text": "Beta", "score": 0.7, "lexical_score": 0.6},
            ],
            "metrics": {"coverage_mode": "narrow_lookup", "retrieval_mode": "default"},
        },
    )
    assert filled["skip_llm"] is False
    assert filled["confidence_payload"]["label"] in {"medium", "high"}

    personal_rpa_list = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="Show my upcoming bookings", mode="personal"),
        session_id="s3",
    )
    assert personal_rpa_list["skip_llm"] is True
    assert personal_rpa_list["reply_text"] == "2026-06-05 / 18:00-19:00 / Court 1"

    personal_rpa_open = await co.prepare_mode_state(
        ChatRequest(
            model="fake-model",
            message="What courts are open on 2026-06-05 between 17:00 and 18:00?",
            mode="personal",
        ),
        session_id="s4",
    )
    assert personal_rpa_open["reply_text"] == "Court 2"

    personal_rpa_error = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="What courts are open?", mode="personal"),
        session_id="s5",
    )
    assert personal_rpa_error["reply_text"].startswith("RPA request failed:")

    personal_workspace = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="Check Gmail for unread mail", mode="personal"),
        session_id="s6",
    )
    assert personal_workspace["personal_status"] == "workspace_gmail_check"
    assert personal_workspace["reply_text"] == "workspace reply"

    monkeypatch.setattr(co, "persist_user_input", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        co,
        "retrieve_personal_store_records",
        lambda *_args, **_kwargs: {
            "status": "records_found",
            "resolved_entities": [{"canonical_name": "Cornelia"}],
            "memories": [{"raw_user_input": "Cornelia birthday"}],
            "metrics": {"retrieved": 1},
        },
    )
    monkeypatch.setattr(
        co,
        "build_personal_grounded_prompt",
        lambda *_args, **_kwargs: "PERSONAL_PROMPT",
    )
    personal_general = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="When is Cornelia's birthday?", mode="personal"),
        session_id="s7",
    )
    assert personal_general["personal_input_persisted"] is True
    assert personal_general["final_prompt"] == "PERSONAL_PROMPT"
    assert personal_general["context_tokens"] > 0

    monkeypatch.setattr(
        co,
        "retrieve_personal_store_records",
        lambda *_args, **_kwargs: {
            "status": "ambiguous",
            "resolved_entities": [],
            "memories": [],
            "metrics": {},
        },
    )
    ambiguous = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="unclear", mode="personal"),
        session_id="s8",
    )
    assert ambiguous["reply_text"] == co.AMBIGUITY_RESPONSE
    assert ambiguous["skip_llm"] is True

    monkeypatch.setattr(
        co,
        "retrieve_personal_store_records",
        lambda *_args, **_kwargs: {
            "status": "no_fact",
            "resolved_entities": [{"canonical_name": "Cornelia"}],
            "memories": [],
            "metrics": {},
        },
    )
    no_fact = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="Cornelia", mode="personal"),
        session_id="s9",
    )
    assert no_fact["reply_text"] == co.NO_FACT_RESPONSE

    monkeypatch.setattr(
        co,
        "retrieve_personal_store_records",
        lambda *_args, **_kwargs: {
            "status": "no_entity",
            "resolved_entities": [],
            "memories": [],
            "metrics": {},
        },
    )
    no_entity = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="unknown", mode="personal"),
        session_id="s10",
    )
    assert no_entity["reply_text"] == co.NO_ENTITY_RESPONSE

    monkeypatch.setattr(
        co,
        "get_full_document_content",
        lambda *_args, **_kwargs: {"error": "missing", "document_name": None, "full_text": "", "chunk_count": 0},
    )
    doc_error = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="summarize", mode="chat", chat_document_id="doc-x"),
        session_id="s11",
    )
    assert doc_error["skip_llm"] is True
    assert doc_error["reply_text"] == "Error: missing"

    monkeypatch.setattr(
        co,
        "get_full_document_content",
        lambda *_args, **_kwargs: {"error": None, "document_name": "Doc X", "full_text": "Alpha Beta", "chunk_count": 1},
    )
    monkeypatch.setattr(
        co,
        "build_chat_with_document_prompt",
        lambda *_args, **_kwargs: "CHAT_DOC_PROMPT",
    )
    doc_ok = await co.prepare_mode_state(
        ChatRequest(model="fake-model", message="summarize", mode="chat", chat_document_id="doc-x"),
        session_id="s12",
    )
    assert doc_ok["final_prompt"] == "CHAT_DOC_PROMPT"
