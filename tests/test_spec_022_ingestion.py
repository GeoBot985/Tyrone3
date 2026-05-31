import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from rag.ingest import ingest_document


class _FakePdfDocument:
    def __init__(self, page_count: int):
        self.page_count = page_count

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def __len__(self):
        return self.page_count


class TestSpec022Ingestion(unittest.TestCase):
    def _make_temp_file(self, suffix: str) -> str:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        handle.write(b"test")
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return handle.name

    @patch("rag.ingest.insert_chunk")
    @patch("rag.ingest.insert_document")
    @patch("rag.ingest.embed_text", return_value=[0.1, 0.2, 0.3])
    @patch("rag.ingest.extract_text_with_ocr")
    @patch("rag.ingest.extract_with_markitdown")
    @patch("rag.ingest.fitz.open", return_value=_FakePdfDocument(2))
    def test_pdf_markitdown_happy_path(
        self,
        _mock_open_pdf,
        mock_markitdown,
        mock_ocr,
        _mock_embed,
        mock_insert_document,
        mock_insert_chunk,
    ):
        pdf_path = self._make_temp_file(".pdf")
        mock_markitdown.return_value = {
            "text": "A" * 800,
            "success": True,
            "error": None,
            "file_type": "pdf",
            "method": "markitdown",
        }

        result = ingest_document(pdf_path, MagicMock(), document_name="sample.pdf")

        self.assertEqual(result["file_type"], "pdf")
        self.assertEqual(result["ingestion_method"], "markitdown")
        self.assertFalse(result["ocr_used"])
        self.assertEqual(result["ocr_char_count"], 0)
        self.assertEqual(result["failed_pages"], [])
        self.assertGreater(result["chunk_count"], 0)
        self.assertIn("extract_markitdown", result["timings"])
        self.assertEqual(result["provenance"]["primary_extractor"], "markitdown")
        self.assertFalse(result["provenance"]["fallback_attempted"])
        self.assertTrue(result["provenance"]["primary_extractor_attempted"])
        self.assertTrue(result["provenance"]["primary_extractor_succeeded"])
        self.assertEqual(result["provenance"]["failure_stage"], None)
        mock_ocr.assert_not_called()
        mock_insert_document.assert_called_once()
        self.assertGreaterEqual(mock_insert_chunk.call_count, 1)

    @patch("rag.ingest.insert_chunk")
    @patch("rag.ingest.insert_document")
    @patch("rag.ingest.embed_text", return_value=[0.1, 0.2, 0.3])
    @patch("rag.ingest.extract_text_with_ocr")
    @patch("rag.ingest.extract_with_markitdown")
    @patch("rag.ingest.fitz.open", return_value=_FakePdfDocument(3))
    def test_pdf_uses_ocr_fallback_when_markitdown_text_is_insufficient(
        self,
        _mock_open_pdf,
        mock_markitdown,
        mock_ocr,
        _mock_embed,
        _mock_insert_document,
        _mock_insert_chunk,
    ):
        pdf_path = self._make_temp_file(".pdf")
        mock_markitdown.return_value = {
            "text": "tiny",
            "success": True,
            "error": None,
            "file_type": "pdf",
            "method": "markitdown",
        }
        mock_ocr.return_value = {
            "text": "OCR text " * 100,
            "ocr_used": True,
            "ocr_char_count": 900,
            "ocr_page_count": 3,
            "failed_pages": [2],
            "granular_timings": {"ocr_render": 0.1, "ocr_recognize": 0.2},
            "error": None,
        }

        result = ingest_document(pdf_path, MagicMock(), document_name="scan.pdf")

        self.assertEqual(result["ingestion_method"], "markitdown+ocr_fallback")
        self.assertTrue(result["ocr_used"])
        self.assertEqual(result["ocr_page_count"], 3)
        self.assertEqual(result["failed_pages"], [2])
        self.assertIn("extract_ocr_fallback", result["timings"])
        self.assertIn("ocr_render", result["timings"])
        self.assertIn("ocr_recognize", result["timings"])
        self.assertTrue(result["provenance"]["fallback_attempted"])
        self.assertTrue(result["provenance"]["fallback_succeeded"])
        self.assertEqual(result["provenance"]["ingestion_method"], "markitdown+ocr_fallback")
        mock_ocr.assert_called_once()

    @patch("rag.ingest.extract_text_with_ocr")
    @patch("rag.ingest.extract_with_markitdown")
    @patch("rag.ingest.fitz.open", return_value=_FakePdfDocument(1))
    def test_pdf_fails_cleanly_if_markitdown_and_ocr_fail(
        self,
        _mock_open_pdf,
        mock_markitdown,
        mock_ocr,
    ):
        pdf_path = self._make_temp_file(".pdf")
        mock_markitdown.return_value = {
            "text": "",
            "success": False,
            "error": "parser error",
            "file_type": "pdf",
            "method": "markitdown",
        }
        mock_ocr.return_value = {
            "text": "",
            "ocr_used": True,
            "ocr_char_count": 0,
            "ocr_page_count": 1,
            "failed_pages": [],
            "granular_timings": {},
            "error": "OCR processing failed: tesseract crashed",
        }

        with self.assertRaisesRegex(Exception, "MarkItDown and OCR fallback") as ctx:
            ingest_document(pdf_path, MagicMock(), document_name="broken.pdf")
        self.assertEqual(ctx.exception.provenance["failure_stage"], "extract_ocr_fallback")
        self.assertIn("ocr_reason", ctx.exception.provenance["failure_reason"])

    @patch("rag.ingest.insert_chunk")
    @patch("rag.ingest.insert_document")
    @patch("rag.ingest.embed_text", return_value=[0.1, 0.2, 0.3])
    @patch("rag.ingest.extract_docx_structured")
    def test_docx_uses_markitdown_without_ocr(
        self,
        mock_docx_extract,
        _mock_embed,
        _mock_insert_document,
        _mock_insert_chunk,
    ):
        docx_path = self._make_temp_file(".docx")
        mock_docx_extract.return_value = {
            "text": "[DOCX | Block: 1 | Ref: Paragraph 1 | Region: paragraph]\nDocument content " * 20,
            "success": True,
            "error": None,
            "file_type": "docx",
            "method": "python_docx_structured",
            "paragraph_count": 1,
            "table_count": 0,
            "table_row_count": 0,
            "blocks": [
                {
                    "region_type": "paragraph",
                    "block_index": 1,
                    "reference": "Paragraph 1",
                    "text": "[DOCX | Block: 1 | Ref: Paragraph 1 | Region: paragraph]\nDocument content",
                }
            ],
            "region_counts": {"paragraph": 1, "table_header": 0, "table_row": 0},
            "warnings": [],
        }

        result = ingest_document(docx_path, MagicMock(), document_name="sample.docx")

        self.assertEqual(result["file_type"], "docx")
        self.assertEqual(result["ingestion_method"], "python_docx_structured")
        self.assertFalse(result["ocr_used"])
        self.assertEqual(result["failed_pages"], [])
        self.assertIn("extract_docx", result["timings"])
        self.assertEqual(result["provenance"]["file_type"], "docx")
        self.assertEqual(result["provenance"]["primary_extractor"], "python_docx_structured")
        self.assertEqual(result["provenance"]["chunk_count"], result["chunk_count"])

    @patch("rag.ingest.extract_text_with_ocr")
    @patch("rag.ingest.extract_docx_structured")
    def test_docx_failure_does_not_attempt_ocr(self, mock_docx_extract, mock_ocr):
        docx_path = self._make_temp_file(".docx")
        mock_docx_extract.return_value = {
            "text": "",
            "success": False,
            "error": "Failed to read DOCX file: conversion failure",
            "file_type": "docx",
            "method": "python_docx_structured",
            "paragraph_count": 0,
            "table_count": 0,
            "table_row_count": 0,
            "blocks": [],
            "region_counts": {"paragraph": 0, "table_header": 0, "table_row": 0},
            "warnings": [],
        }

        with self.assertRaisesRegex(Exception, "Failed to read DOCX file") as ctx:
            ingest_document(docx_path, MagicMock(), document_name="bad.docx")
        self.assertEqual(ctx.exception.provenance["failure_stage"], "extract_docx")

        mock_ocr.assert_not_called()
