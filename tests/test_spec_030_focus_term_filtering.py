from unittest.mock import patch

from rag.search import search


@patch("rag.search.embed_text", return_value=[0.0, 1.0])
@patch("rag.search.get_all_embeddings")
def test_focus_term_filtering_prioritizes_dentistry_rows(mock_embeddings, _mock_embed):
    mock_embeddings.return_value = [
        {
            "text": "[Sheet] Date: 13 January 2026 | Description: Braces / Dentistry | Amount: 1151.11",
            "embedding": [0.0, 0.95],
            "chunk_index": 2,
            "region_type": "table_row",
            "sheet_name": "MSA Deductions Summary Q1 2026",
            "row_index": 4,
            "cell_range": "A4:E4",
            "document_id": "doc1",
            "document_name": "MSA Deductions Summary_ Q1 2026.xlsx",
            "ingested_at": "2026-01-01",
        },
        {
            "text": "[Sheet] Date: 16 February 2026 | Description: GP Consultation | Amount: 339.06",
            "embedding": [0.0, 0.92],
            "chunk_index": 10,
            "region_type": "table_row",
            "sheet_name": "MSA Deductions Summary Q1 2026",
            "row_index": 12,
            "cell_range": "A12:E12",
            "document_id": "doc1",
            "document_name": "MSA Deductions Summary_ Q1 2026.xlsx",
            "ingested_at": "2026-01-01",
        },
        {
            "text": "Systems Inventory: Completing a comprehensive audit of where all City records currently reside.",
            "embedding": [0.0, 0.9],
            "chunk_index": 40,
            "region_type": "paragraph",
            "sheet_name": None,
            "row_index": None,
            "cell_range": None,
            "document_id": "doc2",
            "document_name": "Records Management Strategic Update.docx",
            "ingested_at": "2026-01-01",
        },
    ]

    result = search(
        object(),
        "show our dentistry records from the MSA deductions 2026",
        top_k=3,
        candidate_pool_size=10,
        per_doc_cap=10,
        retrieval_mode="enumeration",
        lexical_match_cap=10,
    )

    assert result["results"][0]["chunk_index"] == 2
    assert "dentistry" in [token.lower() for token in result["results"][0]["matched_focus_tokens"]]
