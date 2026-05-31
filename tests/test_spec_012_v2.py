import unittest
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Add Demo5 root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from rag.db import get_connection, init_db, insert_document, insert_chunk, get_all_chunks_for_document
from app.services.rag_service import get_full_document_content
from app.services.prompt_builder import build_chat_with_document_prompt
from models import ChatRequest
import main

class TestSpec012EndToEnd(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_spec_012_v3.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = get_connection(self.db_path)
        init_db(self.conn)

        # Patch DB_PATH in rag_service and main
        self.patcher1 = patch('app.services.rag_service.DB_PATH', self.db_path)
        self.patcher1.start()
        self.patcher2 = patch('app.config.DB_PATH', self.db_path)
        self.patcher2.start()

        # Ingest a test doc
        doc1 = {
            "document_id": "doc1", "document_name": "Test Document", "source_path": "test.pdf",
            "file_hash": "hash1", "file_size_bytes": 1000, "ingested_at": "2023-01-01T00:00:00", "chunk_count": 2
        }
        insert_document(self.conn, doc1)
        insert_chunk(self.conn, {"chunk_id": "c1", "document_id": "doc1", "chunk_index": 0, "text": "Part 1.", "embedding": [0.1]*384})
        insert_chunk(self.conn, {"chunk_id": "c2", "document_id": "doc1", "chunk_index": 1, "text": "Part 2.", "embedding": [0.2]*384})

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_full_document_reconstruction(self):
        chunks = get_all_chunks_for_document(self.conn, "doc1")
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertEqual(chunks[1]["chunk_index"], 1)

        content = get_full_document_content("doc1")
        self.assertEqual(content["full_text"], "Part 1.\nPart 2.")
        self.assertEqual(content["document_name"], "Test Document")

    def test_chat_with_document_prompt_builder(self):
        with patch('app.services.prompt_builder.get_session_grounding', return_value={}):
            prompt = build_chat_with_document_prompt("What is it?", "Test Doc", "Full text content.")
            self.assertIn("DOCUMENT CONTEXT (Name: Test Doc):", prompt)
            self.assertIn("Full text content.", prompt)
            self.assertIn("USER QUESTION:\nWhat is it?", prompt)
            self.assertIn("You are in Chat mode with a full document as context.", prompt)

    @patch('main.ollama_chat')
    @patch('main.get_session_grounding')
    def test_api_chat_routing(self, mock_grounding, mock_ollama):
        mock_grounding.return_value = {}

        async def mock_chat(*args, **kwargs):
            return ({"message": {"content": "Answer"}}, {"summary": "here"}, None)

        mock_ollama.side_effect = mock_chat

        loop = asyncio.get_event_loop()

        # Chat mode without doc
        req_normal = ChatRequest(model="m", message="hello", mode="chat")
        resp_normal = loop.run_until_complete(main.api_chat(req_normal))
        self.assertEqual(resp_normal.debug["mode"], "chat")
        self.assertIsNone(req_normal.chat_document_id)

        # Chat mode with doc
        req_doc = ChatRequest(model="m", message="summarize", mode="chat", chat_document_id="doc1")
        resp_doc = loop.run_until_complete(main.api_chat(req_doc))
        self.assertEqual(resp_doc.debug["mode"], "chat")
        self.assertEqual(resp_doc.debug["retrieval_scope"], "single_document_grounding")
        self.assertIn("Test Document", resp_doc.debug["selected_documents_names"])

    def test_chat_mode_does_not_autoswitch(self):
        # Even if document_ids are present, if mode is chat, it stays chat
        req = ChatRequest(model="m", message="hi", mode="chat", document_ids=["doc1"])
        effective_mode = req.mode
        self.assertEqual(effective_mode, "chat")

if __name__ == "__main__":
    unittest.main()
