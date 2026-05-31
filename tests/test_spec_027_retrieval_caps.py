from unittest.mock import patch

from app.services.rag_service import get_rag_context


@patch("app.services.rag_service.verify_retrieved_chunks")
@patch("app.services.rag_service.search")
@patch("app.services.rag_service.get_connection")
@patch("app.services.rag_service.os.path.exists", return_value=True)
def test_single_document_mode_uses_larger_caps(_mock_exists, mock_get_connection, mock_search, mock_verify):
    mock_get_connection.return_value = object()
    mock_verify.side_effect = lambda _conn, chunks: (chunks, 0)
    mock_search.return_value = {
        "results": [
            {"document_id": "doc1", "document_name": "x.docx", "chunk_index": 31, "text": "Compliance by Design"}
        ],
        "metrics": {"eligible_docs": 1, "candidate_count": 59, "pool_size": 59, "region_mode": "neutral"},
    }

    result = get_rag_context("are there any references to Compliance by Design?", top_k=3, document_ids=["doc1"])

    assert result["metrics"]["single_doc_mode"] is True
    assert result["metrics"]["per_doc_cap"] >= 24
    assert mock_search.call_args.kwargs["candidate_pool_size"] >= 200
    assert mock_search.call_args.kwargs["per_doc_cap"] >= 24


@patch("app.services.rag_service.verify_retrieved_chunks")
@patch("app.services.rag_service.search")
@patch("app.services.rag_service.get_connection")
@patch("app.services.rag_service.os.path.exists", return_value=True)
def test_multi_document_mode_keeps_standard_caps(_mock_exists, mock_get_connection, mock_search, mock_verify):
    mock_get_connection.return_value = object()
    mock_verify.side_effect = lambda _conn, chunks: (chunks, 0)
    mock_search.return_value = {
        "results": [
            {"document_id": "doc1", "document_name": "x.docx", "chunk_index": 1, "text": "Example"}
        ],
        "metrics": {"eligible_docs": 2, "candidate_count": 100, "pool_size": 80, "region_mode": "neutral"},
    }

    result = get_rag_context("example", top_k=3, document_ids=["doc1", "doc2"])

    assert result["metrics"]["single_doc_mode"] is False
    assert mock_search.call_args.kwargs["candidate_pool_size"] >= 80
