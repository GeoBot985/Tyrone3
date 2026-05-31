import pytest
from app.services.prompt_builder import build_grounded_prompt

def test_build_grounded_prompt_empty_chunks():
    query = "What is the capital of France?"
    prompt = build_grounded_prompt(query, [])

    assert "QUESTION:\nWhat is the capital of France?" in prompt
    assert "Insufficient information" in prompt
    assert "You have no context provided." in prompt

def test_build_grounded_prompt_with_chunks():
    query = "What color is the sky?"
    chunks = [
        {
            "document_name": "facts.pdf",
            "chunk_index": 0,
            "text": "The sky is blue."
        },
        {
            "document_name": "facts2.pdf",
            "chunk_index": 5,
            "text": "Grass is green."
        }
    ]

    prompt = build_grounded_prompt(query, chunks)

    # Assert query presence
    assert "QUESTION:\nWhat color is the sky?" in prompt

    # Assert context blocks
    assert "[Doc: facts.pdf | Chunk 0]" in prompt
    assert "The sky is blue." in prompt
    assert "[Doc: facts2.pdf | Chunk 5]" in prompt
    assert "Grass is green." in prompt

    # Assert instructions
    assert "Only use the provided context to answer the question." in prompt
    assert "Do not use outside knowledge." in prompt
    assert "Do not guess." in prompt
    assert "Insufficient information" in prompt
    assert "Do not use any prior knowledge or external frameworks not explicitly present in the context." in prompt
    assert "Cite your sources for every claim using the format [Doc: name | Chunk X]." in prompt
    assert "Do not force a Yes/No structure unless the question is actually binary." in prompt

def test_build_grounded_prompt_binary_instructions():
    prompt = build_grounded_prompt(
        "is there any GP consultation in here?",
        [{"document_name": "claims.xlsx", "chunk_index": 1, "text": "GP Consultation"}],
        response_format="binary",
    )

    assert "Start the answer with 'Yes' or 'No'." in prompt
    assert "Keep the answer concise." in prompt

def test_build_grounded_prompt_list_instructions():
    prompt = build_grounded_prompt(
        "please list all GP consultations",
        [{"document_name": "claims.xlsx", "chunk_index": 1, "text": "GP Consultation"}],
        response_format="list",
    )

    assert "Present multiple records as a markdown bullet list." in prompt
    assert "Use one record per bullet." in prompt

def test_build_grounded_prompt_table_instructions():
    prompt = build_grounded_prompt(
        "show all GP consultations with date and amount",
        [{"document_name": "claims.xlsx", "chunk_index": 1, "text": "2026-01-01 | 120.00"}],
        response_format="table",
    )

    assert "Prefer a markdown table" in prompt
    assert "fall back to a markdown bullet list" in prompt

def test_build_grounded_prompt_default_does_not_force_yes_no():
    prompt = build_grounded_prompt(
        "tell me about the controls",
        [{"document_name": "controls.docx", "chunk_index": 2, "text": "Control owners review access monthly."}],
        response_format="default",
    )

    assert "Do not force a Yes/No structure unless the question is actually binary." in prompt
    assert "Start the answer with 'Yes' or 'No'." not in prompt

def test_build_grounded_prompt_adds_partial_coverage_honesty_rules():
    prompt = build_grounded_prompt(
        "summarize the medical deductions please",
        [{"document_name": "claims.xlsx", "chunk_index": 1, "text": "GP Consultation"}],
        response_format="summary",
        coverage_mode="coverage_required",
        coverage_truncated=True,
    )

    assert "only claim completeness if the provided context appears to cover the full relevant set" in prompt
    assert "the answer may be partial" in prompt
