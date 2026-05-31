import unittest
from unittest.mock import patch

from app.services.prompt_builder import build_grounded_prompt
from app.services.rag_service import get_rag_context
from rag.search import detect_retrieval_mode, search


class TestSpec029EnumerationRetrieval(unittest.TestCase):
    def test_detect_enumeration_mode_for_reference_query(self):
        self.assertEqual(detect_retrieval_mode("are there any references to Compliance by Design?"), "enumeration")
        self.assertEqual(detect_retrieval_mode("list GP consultations"), "enumeration")
        self.assertEqual(detect_retrieval_mode("summarize this document"), "default")

    @patch("rag.search.embed_text", return_value=[0.0, 1.0])
    @patch("rag.search.get_all_embeddings")
    def test_enumeration_mode_returns_multiple_normalized_lexical_hits(self, mock_embeddings, _mock_embed):
        mock_embeddings.return_value = [
            {
                "text": "GP Consultation entry for Member A.",
                "embedding": [0.0, 0.1],
                "chunk_index": 1,
                "region_type": "table_row",
                "sheet_name": "Claims",
                "row_index": 3,
                "cell_range": "A3:E3",
                "document_id": "doc1",
                "document_name": "claims.xlsx",
                "ingested_at": "2026-01-01",
            },
            {
                "text": "Another GP Consultation entry for Member B.",
                "embedding": [0.0, 0.2],
                "chunk_index": 2,
                "region_type": "table_row",
                "sheet_name": "Claims",
                "row_index": 4,
                "cell_range": "A4:E4",
                "document_id": "doc1",
                "document_name": "claims.xlsx",
                "ingested_at": "2026-01-01",
            },
            {
                "text": "Medication entry unrelated to GP consultation.",
                "embedding": [1.0, 0.0],
                "chunk_index": 3,
                "region_type": "table_row",
                "sheet_name": "Claims",
                "row_index": 5,
                "cell_range": "A5:E5",
                "document_id": "doc1",
                "document_name": "claims.xlsx",
                "ingested_at": "2026-01-01",
            },
        ]

        result = search(
            object(),
            "any GP consultations in here?",
            top_k=10,
            candidate_pool_size=1,
            per_doc_cap=20,
            retrieval_mode="enumeration",
            lexical_match_cap=50,
        )

        self.assertEqual(result["metrics"]["retrieval_mode"], "enumeration")
        returned_indexes = [item["chunk_index"] for item in result["results"]]
        self.assertIn(1, returned_indexes)
        self.assertIn(2, returned_indexes)
        self.assertGreaterEqual(result["metrics"]["normalized_lexical_hits"], 2)

    @patch("app.services.rag_service.verify_retrieved_chunks")
    @patch("app.services.rag_service.search")
    @patch("app.services.rag_service.get_connection")
    @patch("app.services.rag_service.os.path.exists", return_value=True)
    def test_get_rag_context_expands_top_k_for_enumeration(self, _mock_exists, mock_get_connection, mock_search, mock_verify):
        class _Conn:
            def close(self):
                return None

        mock_get_connection.return_value = _Conn()
        mock_verify.side_effect = lambda _conn, chunks: (chunks, 0)
        mock_search.return_value = {
            "results": [
                {"document_id": "doc1", "document_name": "claims.xlsx", "chunk_index": index, "text": f"row {index}"}
                for index in range(1, 21)
            ],
            "metrics": {
                "eligible_docs": 1,
                "candidate_count": 25,
                "pool_size": 25,
                "region_mode": "table_row_preferred",
                "retrieval_mode": "enumeration",
                "lexical_match_cap": 100,
            },
        }

        result = get_rag_context("list all GP consultations", top_k=3, document_ids=["doc1"])

        self.assertEqual(result["metrics"]["coverage_mode"], "coverage_required")
        self.assertEqual(result["metrics"]["retrieval_top_k_requested"], 12)
        self.assertGreaterEqual(result["metrics"]["effective_top_k"], 12)
        self.assertEqual(len(result["chunks"]), 20)
        self.assertEqual(mock_search.call_args.kwargs["retrieval_mode"], "enumeration")

    @patch("app.services.rag_service.verify_retrieved_chunks")
    @patch("app.services.rag_service.search")
    @patch("app.services.rag_service.get_connection")
    @patch("app.services.rag_service.os.path.exists", return_value=True)
    def test_get_rag_context_keeps_narrow_lookup_small(self, _mock_exists, mock_get_connection, mock_search, mock_verify):
        class _Conn:
            def close(self):
                return None

        mock_get_connection.return_value = _Conn()
        mock_verify.side_effect = lambda _conn, chunks: (chunks, 0)
        mock_search.return_value = {
            "results": [
                {"document_id": "doc1", "document_name": "glossary.docx", "chunk_index": index, "text": f"row {index}", "score": 0.8}
                for index in range(1, 5)
            ],
            "metrics": {
                "eligible_docs": 1,
                "candidate_count": 4,
                "pool_size": 4,
                "region_mode": "neutral",
                "retrieval_mode": "default",
                "lexical_match_cap": 20,
            },
        }

        result = get_rag_context("what is APO13?", top_k=3, document_ids=["doc1"])

        self.assertEqual(result["metrics"]["coverage_mode"], "narrow_lookup")
        self.assertEqual(result["metrics"]["retrieval_top_k_requested"], 3)
        self.assertEqual(len(result["chunks"]), 3)

    def test_prompt_builder_uses_list_instruction_for_enumeration(self):
        prompt = build_grounded_prompt(
            "list all GP consultations",
            [{"document_name": "claims.xlsx", "chunk_index": 1, "text": "GP Consultation"}],
            retrieval_mode="enumeration",
        )
        self.assertIn("assemble the matching items into a list first", prompt)
        self.assertIn("present them as a list", prompt)


if __name__ == "__main__":
    unittest.main()
