import unittest
import sys
import os
from unittest.mock import MagicMock

# Add Demo5 root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from rag.search import score_lexical, search
from rag.db import get_connection, init_db, insert_document, insert_chunk

class TestSpec012(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_spec_012.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = get_connection(self.db_path)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_lexical_scorer(self):
        # Exact term presence
        score1 = score_lexical("apple banana", "this is an apple and a banana")
        self.assertEqual(score1, 1.0)

        # Partial match
        score2 = score_lexical("apple banana cherry", "this is an apple")
        self.assertAlmostEqual(score2, 1/3)

        # Filename boost
        score3 = score_lexical("apple", "something else", "apple_doc.pdf")
        self.assertGreater(score3, 0)

        # Case insensitivity and punctuation
        score4 = score_lexical("Apple!", "apple.")
        self.assertEqual(score4, 1.0)

    def test_working_set_filtering(self):
        # Ingest two docs
        doc1 = {
            "document_id": "doc1", "document_name": "Doc One", "source_path": "p1",
            "file_hash": "h1", "file_size_bytes": 100, "ingested_at": "2023-01-01", "chunk_count": 1
        }
        doc2 = {
            "document_id": "doc2", "document_name": "Doc Two", "source_path": "p2",
            "file_hash": "h2", "file_size_bytes": 100, "ingested_at": "2023-01-01", "chunk_count": 1
        }
        insert_document(self.conn, doc1)
        insert_document(self.conn, doc2)

        # Insert chunks
        # Mocking embedding as [1.0, 0.0] for doc1 and [0.0, 1.0] for doc2
        insert_chunk(self.conn, {
            "chunk_id": "c1", "document_id": "doc1", "chunk_index": 0,
            "text": "content from doc one", "embedding": [1.0, 0.0]
        })
        insert_chunk(self.conn, {
            "chunk_id": "c2", "document_id": "doc2", "chunk_index": 0,
            "text": "content from doc two", "embedding": [0.0, 1.0]
        })

        # Search with working set doc1
        # Mocking embed_text to return [1.0, 0.0]
        import rag.search
        original_embed = rag.search.embed_text
        rag.search.embed_text = MagicMock(return_value=[1.0, 0.0])

        try:
            res = search(self.conn, "content", document_ids=["doc1"])
            self.assertEqual(len(res["results"]), 1)
            self.assertEqual(res["results"][0]["document_id"], "doc1")
            self.assertEqual(res["metrics"]["eligible_docs"], 1)

            # Search with working set doc2
            res = search(self.conn, "content", document_ids=["doc2"])
            self.assertEqual(len(res["results"]), 1)
            self.assertEqual(res["results"][0]["document_id"], "doc2")

            # Search with empty working set (full corpus)
            res = search(self.conn, "content", document_ids=None)
            self.assertEqual(len(res["results"]), 2)
            self.assertEqual(res["metrics"]["eligible_docs"], 2)
        finally:
            rag.search.embed_text = original_embed

    def test_diversity_control(self):
        # Doc with many similar chunks
        insert_document(self.conn, {
            "document_id": "doc1", "document_name": "Doc One", "source_path": "p1",
            "file_hash": "h1", "file_size_bytes": 100, "ingested_at": "2023-01-01", "chunk_count": 5
        })
        for i in range(5):
            insert_chunk(self.conn, {
                "chunk_id": f"c{i}", "document_id": "doc1", "chunk_index": i,
                "text": f"text {i}", "embedding": [1.0, 0.0]
            })

        import rag.search
        original_embed = rag.search.embed_text
        rag.search.embed_text = MagicMock(return_value=[1.0, 0.0])

        try:
            # top_k=5, but per_doc_cap=2
            res = search(self.conn, "text", top_k=5, per_doc_cap=2)
            self.assertEqual(len(res["results"]), 2)
        finally:
            rag.search.embed_text = original_embed

if __name__ == "__main__":
    unittest.main()
