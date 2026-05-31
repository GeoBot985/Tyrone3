import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import UploadFile

import main
from rag.ingest import get_file_type, is_supported_upload_extension, ingest_document


class TestSpec023UploadSupport(unittest.TestCase):
    def test_supported_upload_extensions_are_centralized(self):
        self.assertTrue(is_supported_upload_extension(".pdf"))
        self.assertTrue(is_supported_upload_extension(".pptx"))
        self.assertTrue(is_supported_upload_extension(".xlsx"))
        self.assertTrue(is_supported_upload_extension(".csv"))
        self.assertTrue(is_supported_upload_extension(".txt"))
        self.assertTrue(is_supported_upload_extension(".md"))
        self.assertFalse(is_supported_upload_extension(".jpg"))
        self.assertEqual(get_file_type("deck.PPTX"), "pptx")

    def test_non_pdf_markitdown_formats_record_file_type(self):
        def make_temp(suffix: str) -> str:
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            handle.write(b"content")
            handle.close()
            self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
            return handle.name

        for suffix in (".pptx", ".csv", ".txt", ".md"):
            with self.subTest(suffix=suffix):
                path = make_temp(suffix)
                with patch("rag.ingest.extract_with_markitdown") as mock_markitdown, \
                     patch("rag.ingest.embed_text", return_value=[0.1, 0.2, 0.3]), \
                     patch("rag.ingest.insert_document"), \
                     patch("rag.ingest.insert_chunk"), \
                     patch("rag.ingest.extract_text_with_ocr") as mock_ocr:
                    mock_markitdown.return_value = {
                        "text": f"content from {suffix} " * 80,
                        "success": True,
                        "error": None,
                        "file_type": suffix.lstrip("."),
                        "method": "markitdown",
                    }

                    result = ingest_document(path, MagicMock(), document_name=f"sample{suffix}")

                    self.assertEqual(result["file_type"], suffix.lstrip("."))
                    self.assertEqual(result["ingestion_method"], "markitdown")
                    self.assertFalse(result["ocr_used"])
                    self.assertGreater(result["chunk_count"], 0)
                    mock_ocr.assert_not_called()

    def test_non_pdf_blank_markitdown_result_fails_cleanly(self):
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pptx")
        handle.write(b"content")
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))

        with patch("rag.ingest.extract_with_markitdown") as mock_markitdown:
            mock_markitdown.return_value = {
                "text": "   \n\t ",
                "success": True,
                "error": None,
                "file_type": "pptx",
                "method": "markitdown",
            }

            with self.assertRaisesRegex(Exception, "No extractable text was found in this PPTX file.") as ctx:
                ingest_document(handle.name, MagicMock(), document_name="blank.pptx")
            self.assertEqual(ctx.exception.provenance["failure_stage"], "extract_markitdown")

    def test_api_ingest_rejects_unsupported_extension_cleanly(self):
        async def run_test():
            upload = UploadFile(filename="bad.jpg", file=AsyncMock())
            response = await main.api_ingest(upload)
            return response.body.decode("utf-8")

        import asyncio
        body = asyncio.run(run_test())
        self.assertIn("Unsupported file type", body)
        self.assertIn("PPTX", body)
        self.assertIn("TXT", body)

    def test_duplicate_skip_returns_provenance(self):
        with patch("app.services.ingest_service.get_connection"), \
             patch("app.services.ingest_service.init_db"), \
             patch("app.services.ingest_service.get_file_hash", return_value="abc"), \
             patch("app.services.ingest_service.get_document_by_hash", return_value={
                 "document_id": "doc-1",
                 "chunk_count": 42,
                 "file_type": "pdf",
                 "ingestion_method": "markitdown",
                 "primary_extractor": "markitdown",
                 "ocr_used": False,
             }):
            from app.services.ingest_service import ingest_file
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            handle.write(b"content")
            handle.close()
            self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))

            result = ingest_file(handle.name, document_name="dup.pdf")

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["provenance"]["status"], "duplicate_skipped")
            self.assertEqual(result["provenance"]["existing_chunk_count"], 42)
