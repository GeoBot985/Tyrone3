import fitz
import hashlib
import json
import os
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .db import insert_chunk, insert_document
from .docx_extractor import extract_docx_structured
from .embedder import embed_text
from .ocr_service import extract_text_with_ocr, is_scanned_pdf
from .markitdown_extractor import extract_with_markitdown
from .layout_normalizer import normalize_layout_aware_text
from .spreadsheet_extractor import extract_xlsx_structured
from .timing import IngestionTimings, StageTimer
from app.config import (
    ENABLE_MARKITDOWN,
    INGESTION_MAX_WORKERS,
    INGESTION_EMBED_MAX_WORKERS,
    SUPPORTED_UPLOAD_EXTENSIONS,
)


def get_file_hash(path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for byte_block in iter(lambda: file_handle.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def _embed_chunk(task: tuple[int, str, str, dict]) -> dict | None:
    index, text_chunk, doc_id, metadata = task
    if not text_chunk.strip():
        return None

    embedding = embed_text(text_chunk)
    return {
        "chunk_id": str(uuid.uuid4()),
        "document_id": doc_id,
        "chunk_index": index,
        "text": text_chunk,
        "region_type": metadata.get("region_type"),
        "sheet_name": metadata.get("sheet_name"),
        "row_index": metadata.get("row_index"),
        "cell_range": metadata.get("cell_range"),
        "embedding": embedding,
    }


def _normalize_extracted_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines).strip()


class IngestionFailure(Exception):
    def __init__(self, message: str, provenance: dict):
        super().__init__(message)
        self.provenance = provenance


def _build_provenance(file_type: str) -> dict:
    return {
        "status": "in_progress",
        "file_type": file_type,
        "ingestion_method": None,
        "primary_extractor": "markitdown",
        "fallback_extractor": "ocr" if file_type == "pdf" else None,
        "primary_extractor_attempted": False,
        "primary_extractor_succeeded": False,
        "fallback_attempted": False,
        "fallback_succeeded": False,
        "failure_stage": None,
        "failure_reason": None,
        "raw_text_char_count": 0,
        "normalized_text_char_count": 0,
        "non_empty_chunk_count": 0,
        "chunk_count": 0,
        "ocr_used": False,
        "ocr_char_count": 0,
        "ocr_page_count": 0,
        "failed_pages": [],
        "timings": {},
        "stage_reached": "file_validation",
        "layout_normalization_applied": False,
        "layout_mode": None,
        "layout_warnings": [],
        "sheet_count": 0,
        "sheet_names": [],
        "row_count": 0,
        "header_detection_used": False,
        "header_detection_warnings": [],
        "skipped_object_types": [],
        "extraction_details": {},
        "has_table_rows": False,
        "has_summary_blocks": False,
        "region_counts": {},
    }


def _raise_ingestion_failure(provenance: dict, stage: str, reason: str, user_message: str | None = None):
    provenance["failure_stage"] = stage
    provenance["failure_reason"] = reason
    provenance["stage_reached"] = stage
    provenance["status"] = "failed"
    raise IngestionFailure(user_message or reason, provenance.copy())


def get_file_extension(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def get_file_type(path: str) -> str:
    return get_file_extension(path).lstrip(".") or "unknown"


def is_supported_upload_extension(ext: str) -> bool:
    return ext in SUPPORTED_UPLOAD_EXTENSIONS


def _extract_text_for_ingestion(path: str, ext: str, timings: IngestionTimings, provenance: dict) -> dict:
    if ext == ".xlsx":
        provenance["primary_extractor"] = "openpyxl_structured"
        provenance["fallback_extractor"] = None
        provenance["primary_extractor_attempted"] = True
        provenance["stage_reached"] = "extract_xlsx"
        with StageTimer(timings, "extract_xlsx"):
            xlsx_result = extract_xlsx_structured(path)

        provenance["sheet_count"] = xlsx_result.get("sheet_count", 0)
        provenance["sheet_names"] = xlsx_result.get("sheet_names", [])
        provenance["row_count"] = xlsx_result.get("row_count", 0)
        provenance["header_detection_used"] = xlsx_result.get("header_detection_used", False)
        provenance["header_detection_warnings"] = xlsx_result.get("header_detection_warnings", [])
        provenance["skipped_object_types"] = xlsx_result.get("skipped_objects", [])
        provenance["extraction_details"] = {
            "column_count_by_sheet": xlsx_result.get("column_count_by_sheet", {}),
            "sheets": xlsx_result.get("sheets", []),
            "warnings": xlsx_result.get("warnings", []),
            "sheet_count": xlsx_result.get("sheet_count", 0),
            "row_count": xlsx_result.get("row_count", 0),
        }
        provenance["region_counts"] = xlsx_result.get("region_counts", {})
        provenance["has_table_rows"] = provenance["region_counts"].get("table_row", 0) > 0
        provenance["has_summary_blocks"] = (
            provenance["region_counts"].get("summary_block", 0) > 0
            or provenance["region_counts"].get("pivot_like", 0) > 0
        )

        if not xlsx_result.get("success", False):
            _raise_ingestion_failure(
                provenance,
                "extract_xlsx",
                xlsx_result.get("error") or "unknown XLSX extraction error",
                xlsx_result.get("error") or "Failed to read XLSX workbook.",
            )

        raw_text = xlsx_result.get("text", "") or ""
        normalized_text = _normalize_extracted_text(raw_text)
        provenance["primary_extractor_succeeded"] = True
        provenance["raw_text_char_count"] = len(raw_text)
        provenance["normalized_text_char_count"] = len(normalized_text)
        if not normalized_text:
            _raise_ingestion_failure(
                provenance,
                "extract_xlsx",
                "XLSX workbook contained no extractable rows.",
                "XLSX workbook contained no extractable rows.",
            )

        return {
            "raw_text_char_count": len(raw_text),
            "normalized_text_char_count": len(normalized_text),
            "text": normalized_text,
            "structured_chunks": xlsx_result.get("row_records", []),
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "ingestion_method": "openpyxl_structured",
            "file_type": "xlsx",
            "failed_pages": [],
        }

    if ext == ".docx":
        provenance["primary_extractor"] = "python_docx_structured"
        provenance["fallback_extractor"] = None
        provenance["primary_extractor_attempted"] = True
        provenance["stage_reached"] = "extract_docx"
        with StageTimer(timings, "extract_docx"):
            docx_result = extract_docx_structured(path)

        provenance["extraction_details"] = {
            "paragraph_count": docx_result.get("paragraph_count", 0),
            "table_count": docx_result.get("table_count", 0),
            "table_row_count": docx_result.get("table_row_count", 0),
            "warnings": docx_result.get("warnings", []),
        }
        provenance["region_counts"] = docx_result.get("region_counts", {})
        provenance["has_table_rows"] = provenance["region_counts"].get("table_row", 0) > 0
        provenance["has_summary_blocks"] = False

        if not docx_result.get("success", False):
            _raise_ingestion_failure(
                provenance,
                "extract_docx",
                docx_result.get("error") or "unknown DOCX extraction error",
                docx_result.get("error") or "Failed to read DOCX file.",
            )

        raw_text = docx_result.get("text", "") or ""
        normalized_text = _normalize_extracted_text(raw_text)
        provenance["primary_extractor_succeeded"] = True
        provenance["raw_text_char_count"] = len(raw_text)
        provenance["normalized_text_char_count"] = len(normalized_text)
        if not normalized_text:
            _raise_ingestion_failure(
                provenance,
                "extract_docx",
                "DOCX file contained no extractable text.",
                "No extractable text was found in this DOCX file.",
            )

        return {
            "raw_text_char_count": len(raw_text),
            "normalized_text_char_count": len(normalized_text),
            "text": normalized_text,
            "structured_chunks": docx_result.get("blocks", []),
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "ingestion_method": "python_docx_structured",
            "file_type": "docx",
            "failed_pages": [],
        }

    if ext == ".xls":
        provenance["primary_extractor"] = "legacy_xls_unsupported"
        _raise_ingestion_failure(
            provenance,
            "file_validation",
            "Legacy .xls spreadsheets are not yet supported. Please save as .xlsx and retry.",
            "Legacy .xls spreadsheets are not yet supported. Please save as .xlsx and retry.",
        )

    if not ENABLE_MARKITDOWN:
        _raise_ingestion_failure(
            provenance,
            "extract_markitdown",
            "MarkItDown extraction is disabled by configuration.",
        )

    if ext == ".pdf":
        markitdown_result = {}
        provenance["primary_extractor_attempted"] = True
        provenance["stage_reached"] = "extract_markitdown"
        with StageTimer(timings, "extract_markitdown"):
            markitdown_result = extract_with_markitdown(path)

        raw_text = markitdown_result.get("text", "") or ""
        normalized_text = _normalize_extracted_text(raw_text)
        provenance["raw_text_char_count"] = len(raw_text)
        provenance["normalized_text_char_count"] = len(normalized_text)
        markitdown_failed = not markitdown_result.get("success", False)
        insufficient_text = is_scanned_pdf(len(normalized_text))
        provenance["primary_extractor_succeeded"] = not markitdown_failed and not insufficient_text

        if not markitdown_failed and not insufficient_text:
            return {
                "raw_text_char_count": len(raw_text),
                "normalized_text_char_count": len(normalized_text),
                "text": normalized_text,
                "ocr_used": False,
                "ocr_char_count": 0,
                "ocr_page_count": 0,
                "ingestion_method": "markitdown",
                "file_type": "pdf",
                "failed_pages": [],
            }

        provenance["fallback_attempted"] = True
        provenance["stage_reached"] = "extract_ocr_fallback"
        with StageTimer(timings, "extract_ocr_fallback"):
            ocr_result = extract_text_with_ocr(path, max_workers=INGESTION_MAX_WORKERS)

        if "granular_timings" in ocr_result:
            for stage_name, duration in ocr_result["granular_timings"].items():
                timings.record_stage(stage_name, duration)

        if ocr_result["error"]:
            reason = (
                f"markitdown_failed={markitdown_failed}; "
                f"markitdown_reason={markitdown_result.get('error') or 'insufficient_text' if insufficient_text else 'unknown'}; "
                f"ocr_reason={ocr_result['error']}"
            )
            _raise_ingestion_failure(
                provenance,
                "extract_ocr_fallback",
                reason,
                (
                    "PDF extraction failed in MarkItDown and OCR fallback: "
                    f"{markitdown_result.get('error') or 'insufficient text extracted'}; {ocr_result['error']}"
                ) if markitdown_failed or insufficient_text else ocr_result["error"],
            )

        normalized_ocr_text = _normalize_extracted_text(ocr_result["text"])
        if not normalized_ocr_text:
            _raise_ingestion_failure(
                provenance,
                "extract_ocr_fallback",
                "OCR fallback produced no usable normalized text.",
                "No extractable text found in PDF.",
            )

        provenance["fallback_succeeded"] = True

        return {
            "raw_text_char_count": len(ocr_result["text"]),
            "normalized_text_char_count": len(normalized_ocr_text),
            "text": normalized_ocr_text,
            "ocr_used": True,
            "ocr_char_count": ocr_result["ocr_char_count"],
            "ocr_page_count": ocr_result["ocr_page_count"],
            "ingestion_method": "markitdown+ocr_fallback",
            "file_type": "pdf",
            "failed_pages": ocr_result.get("failed_pages", []),
        }

    if ext in SUPPORTED_UPLOAD_EXTENSIONS:
        provenance["primary_extractor_attempted"] = True
        provenance["stage_reached"] = "extract_markitdown"
        with StageTimer(timings, "extract_markitdown"):
            markitdown_result = extract_with_markitdown(path)

        if not markitdown_result.get("success", False):
            _raise_ingestion_failure(
                provenance,
                "extract_markitdown",
                markitdown_result.get("error") or "unknown MarkItDown error",
                (
                    f"{get_file_type(path).upper()} extraction failed with MarkItDown: "
                    f"{markitdown_result.get('error') or 'unknown error'}"
                ),
            )

        raw_text = markitdown_result.get("text", "") or ""
        normalized_text = _normalize_extracted_text(raw_text)
        provenance["primary_extractor_succeeded"] = True
        provenance["raw_text_char_count"] = len(raw_text)
        provenance["normalized_text_char_count"] = len(normalized_text)
        if not normalized_text:
            _raise_ingestion_failure(
                provenance,
                "extract_markitdown",
                "MarkItDown returned empty or whitespace-only text.",
                f"No extractable text was found in this {get_file_type(path).upper()} file.",
            )

        return {
            "raw_text_char_count": len(raw_text),
            "normalized_text_char_count": len(normalized_text),
            "text": normalized_text,
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "ingestion_method": "markitdown",
            "file_type": get_file_type(path),
            "failed_pages": [],
        }

    _raise_ingestion_failure(
        provenance,
        "file_validation",
        f"Unsupported file type: {ext}",
    )


def ingest_document(path: str, conn, document_name: str | None = None) -> dict:
    timings = IngestionTimings()
    timings.start_total()

    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    doc_name = document_name or os.path.basename(path)
    file_hash = get_file_hash(path)
    file_size = os.path.getsize(path)
    ingested_at = datetime.utcnow().isoformat()
    doc_id = str(uuid.uuid4())

    ext = get_file_extension(path)
    file_type = get_file_type(path)
    provenance = _build_provenance(file_type)
    text = ""
    structured_chunks = None
    ocr_used = False
    ocr_char_count = 0
    ocr_page_count = 0
    ingestion_method = "markitdown"
    failed_pages = []

    provenance["stage_reached"] = "file_validation"
    with StageTimer(timings, "open_pdf"):
        # Keep PDF validation/page counting isolated so non-PDF uploads stay on the MarkItDown path.
        if ext == ".pdf":
            try:
                with fitz.open(path) as doc:
                    ocr_page_count = len(doc)
            except Exception as e:
                _raise_ingestion_failure(
                    provenance,
                    "file_validation",
                    f"Failed to open PDF: {e}",
                    f"Failed to open PDF: {e}",
                )

    try:
        extraction_result = _extract_text_for_ingestion(path, ext, timings, provenance)
        text = extraction_result["text"]
        structured_chunks = extraction_result.get("structured_chunks")
        ocr_used = extraction_result["ocr_used"]
        ocr_char_count = extraction_result["ocr_char_count"]
        ocr_page_count = extraction_result["ocr_page_count"]
        ingestion_method = extraction_result["ingestion_method"]
        file_type = extraction_result["file_type"]
        failed_pages = extraction_result["failed_pages"]
        provenance["ingestion_method"] = ingestion_method
        provenance["file_type"] = file_type
        provenance["ocr_used"] = ocr_used
        provenance["ocr_char_count"] = ocr_char_count
        provenance["ocr_page_count"] = ocr_page_count
        provenance["failed_pages"] = failed_pages
        provenance["raw_text_char_count"] = extraction_result.get("raw_text_char_count", provenance["raw_text_char_count"])
        provenance["normalized_text_char_count"] = extraction_result.get("normalized_text_char_count", provenance["normalized_text_char_count"])
    except IngestionFailure:
        raise

    provenance["stage_reached"] = "text_normalization"
    with StageTimer(timings, "cleanup"):
        text = _normalize_extracted_text(text)
        provenance["normalized_text_char_count"] = len(text)

    provenance["stage_reached"] = "layout_normalization"
    with StageTimer(timings, "layout_normalization"):
        layout_result = normalize_layout_aware_text(text, file_type)
        text = layout_result["text"]
        provenance["layout_normalization_applied"] = layout_result.get("applied", False)
        provenance["layout_mode"] = layout_result.get("layout_mode")
        provenance["layout_warnings"] = layout_result.get("warnings", [])
        provenance["normalized_text_char_count"] = len(text)
        provenance["extraction_details"]["layout_heuristic"] = layout_result.get("heuristic")

    provenance["stage_reached"] = "chunking"
    with StageTimer(timings, "chunking"):
        if structured_chunks:
            text_chunks = [chunk["text"] for chunk in structured_chunks if chunk.get("text", "").strip()]
            chunk_metadata = [
                {
                    "region_type": chunk.get("region_type"),
                    "sheet_name": chunk.get("sheet_name"),
                    "row_index": chunk.get("row_index"),
                    "cell_range": chunk.get("cell_range"),
                }
                for chunk in structured_chunks
                if chunk.get("text", "").strip()
            ]
        else:
            text_chunks = chunk_text(text)
            chunk_metadata = [{} for _ in text_chunks]
        provenance["non_empty_chunk_count"] = len([chunk for chunk in text_chunks if chunk.strip()])

    processed_chunks = []
    provenance["stage_reached"] = "embedding"
    with StageTimer(timings, "embedding"):
        embed_tasks = [
            (index, text_chunk, doc_id, chunk_metadata[index])
            for index, text_chunk in enumerate(text_chunks)
            if text_chunk.strip()
        ]

        with ThreadPoolExecutor(max_workers=INGESTION_EMBED_MAX_WORKERS) as executor:
            for embedded_chunk in executor.map(_embed_chunk, embed_tasks):
                if embedded_chunk:
                    processed_chunks.append(embedded_chunk)

        processed_chunks.sort(key=lambda chunk: chunk["chunk_index"])

    chunk_count = len(processed_chunks)
    if chunk_count == 0:
        _raise_ingestion_failure(
            provenance,
            "chunking",
            "No non-empty chunks could be created after extraction and normalization.",
            f"No non-empty chunks could be created from {file_type.upper()} text.",
        )
    provenance["chunk_count"] = chunk_count

    doc_record = {
        "document_id": doc_id,
        "document_name": doc_name,
        "source_path": os.path.abspath(path),
        "file_hash": file_hash,
        "file_size_bytes": file_size,
        "ingested_at": ingested_at,
        "chunk_count": chunk_count,
        "ingestion_method": ingestion_method,
        "file_type": file_type,
        "primary_extractor": provenance["primary_extractor"],
        "fallback_extractor": provenance["fallback_extractor"],
        "failure_stage": provenance["failure_stage"],
        "failure_reason": provenance["failure_reason"],
        "raw_text_char_count": provenance["raw_text_char_count"],
        "normalized_text_char_count": provenance["normalized_text_char_count"],
        "extraction_details_json": json.dumps({
            "layout_normalization_applied": provenance["layout_normalization_applied"],
            "layout_mode": provenance["layout_mode"],
            "layout_warnings": provenance["layout_warnings"],
            "sheet_count": provenance["sheet_count"],
            "sheet_names": provenance["sheet_names"],
            "row_count": provenance["row_count"],
            "header_detection_used": provenance["header_detection_used"],
            "header_detection_warnings": provenance["header_detection_warnings"],
            "skipped_object_types": provenance["skipped_object_types"],
            "has_table_rows": provenance["has_table_rows"],
            "has_summary_blocks": provenance["has_summary_blocks"],
            "region_counts": provenance["region_counts"],
            "extraction_details": provenance["extraction_details"],
        }),
        "ocr_used": ocr_used,
        "ocr_char_count": ocr_char_count,
        "ocr_page_count": ocr_page_count,
    }

    provenance["stage_reached"] = "db_write"
    with StageTimer(timings, "db_write"):
        try:
            insert_document(conn, doc_record)
            for chunk in processed_chunks:
                insert_chunk(conn, chunk)
        except Exception as exc:
            _raise_ingestion_failure(
                provenance,
                "db_write",
                str(exc),
            )

    provenance["timings"] = timings.get_summary()
    provenance["status"] = "success"
    provenance["failure_stage"] = None
    provenance["failure_reason"] = None
    doc_record["timings"] = provenance["timings"]
    doc_record["failed_pages"] = failed_pages
    doc_record["max_workers"] = INGESTION_MAX_WORKERS
    doc_record["embed_max_workers"] = INGESTION_EMBED_MAX_WORKERS
    doc_record["provenance"] = provenance

    return doc_record


def ingest_pdf(path: str, conn, document_name: str | None = None) -> dict:
    return ingest_document(path, conn, document_name)
