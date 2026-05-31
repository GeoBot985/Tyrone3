import unittest
from unittest.mock import patch

from rag.search import search


class TestSpec025ExcelReferences(unittest.TestCase):
    @patch("rag.search.embed_text", return_value=[1.0, 0.0])
    @patch("rag.search.get_all_embeddings")
    def test_top_expenses_prefers_table_rows(self, mock_embeddings, _mock_embed):
        mock_embeddings.return_value = [
            {
                "text": "[Sheet: Claims | Range: A10:C10 | Row: 10 | Region: summary_block]\nTotal: 1000",
                "embedding": [1.0, 0.0],
                "chunk_index": 0,
                "region_type": "summary_block",
                "sheet_name": "Claims",
                "row_index": 10,
                "cell_range": "A10:C10",
                "document_id": "doc1",
                "document_name": "claims.xlsx",
                "ingested_at": "2026-01-01",
            },
            {
                "text": "[Sheet: Claims | Range: A2:C2 | Row: 2 | Region: table_row]\nMember: Nina\nAmount: 953.95",
                "embedding": [1.0, 0.0],
                "chunk_index": 1,
                "region_type": "table_row",
                "sheet_name": "Claims",
                "row_index": 2,
                "cell_range": "A2:C2",
                "document_id": "doc1",
                "document_name": "claims.xlsx",
                "ingested_at": "2026-01-01",
            },
        ]

        result = search(object(), "top 3 expenses", top_k=5)

        self.assertEqual(result["metrics"]["region_mode"], "table_row_preferred")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["region_type"], "table_row")
        self.assertEqual(result["results"][0]["cell_range"], "A2:C2")

    @patch("rag.search.embed_text", return_value=[1.0, 0.0])
    @patch("rag.search.get_all_embeddings")
    def test_total_queries_allow_summary_blocks(self, mock_embeddings, _mock_embed):
        mock_embeddings.return_value = [
            {
                "text": "[Sheet: Claims | Range: A10:C10 | Row: 10 | Region: summary_block]\nTotal: 1000",
                "embedding": [1.0, 0.0],
                "chunk_index": 0,
                "region_type": "summary_block",
                "sheet_name": "Claims",
                "row_index": 10,
                "cell_range": "A10:C10",
                "document_id": "doc1",
                "document_name": "claims.xlsx",
                "ingested_at": "2026-01-01",
            },
        ]

        result = search(object(), "what is the total amount", top_k=5)

        self.assertEqual(result["metrics"]["region_mode"], "summary_allowed")
        self.assertEqual(result["results"][0]["region_type"], "summary_block")
