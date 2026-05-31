from typing import List, Dict
from app.services.session_grounding import get_session_grounding

def build_format_specific_instructions(response_format: str, retrieval_mode: str = "default") -> str:
    if response_format == "binary":
        return (
            "- Start the answer with 'Yes' or 'No'.\n"
            "- Follow with a brief explanation.\n"
            "- Keep the answer concise.\n"
            "- Use citations inline or at the end of the sentence.\n"
            "- Do not output bullets or a table unless the user explicitly asked for them.\n"
        )

    if response_format == "list":
        return (
            "- Return the answer as markdown only.\n"
            "- Every result line must begin with '- '.\n"
            "- Present multiple records as a markdown bullet list.\n"
            "- Use one record per bullet.\n"
            "- Keep each bullet compact.\n"
            "- Use short labels when useful, such as Date:, Member:, Provider:, Amount:, Status:.\n"
            "- Put a citation at the end of each bullet where practical.\n"
            "- Do not collapse all records into one paragraph.\n"
            "- Do not write an introductory paragraph before the bullets unless the answer is only one very small item.\n"
            "- Example shape:\n"
            "  - Date: 31 March 2026; Member: Cornelia; Provider: Barnard Vd Merve Theron; Amount: 620.3 [Doc: claims.xlsx | Chunk 15]\n"
        )

    if response_format == "table":
        return (
            "- Return the answer as markdown only.\n"
            "- Prefer a markdown table if the retrieved evidence supports repeated structured records.\n"
            "- Use concise column names.\n"
            "- If the exact fields are unclear, fall back to a markdown bullet list instead of inventing columns.\n"
            "- Include citations immediately below the table or directly with the relevant row block.\n"
            "- Do not invent values or cells that are not present in the context.\n"
            "- Do not introduce prose before the table unless a one-line clarification is necessary.\n"
            "- Example shape:\n"
            "  | Date | Member | Provider | Amount |\n"
            "  | --- | --- | --- | --- |\n"
            "  | 31 March 2026 | Cornelia | Barnard Vd Merve Theron | 620.3 |\n"
            "  Citations: [Doc: claims.xlsx | Chunk 15]\n"
        )

    if response_format == "summary":
        return (
            "- Return the answer as markdown only.\n"
            "- Use a short heading if helpful.\n"
            "- Present 3 to 7 markdown bullet points unless the answer is extremely small.\n"
            "- Keep wording compact and factual.\n"
            "- Cite each bullet or grouped bullet block.\n"
            "- Do not output a dense paragraph when multiple points are available.\n"
        )

    if response_format == "comparison":
        return (
            "- Return the answer as markdown only.\n"
            "- Present the answer as markdown bullets under two short headings or as a two-column markdown table.\n"
            "- Highlight similarities and differences clearly.\n"
            "- Do not infer unsupported differences.\n"
            "- Cite each comparison claim.\n"
            "- Do not write the comparison as one dense paragraph.\n"
        )

    if retrieval_mode == "enumeration":
        return (
            "- For lookup, list, enumeration, or reference questions, assemble the matching items into a list first and then optionally add a short summary sentence.\n"
            "- Preserve item-level references and present them as a list instead of collapsing them into one prose claim.\n"
        )

    return (
        "- Answer naturally and concisely using a short paragraph or short bullets as appropriate.\n"
        "- Do not force a Yes/No structure unless the question is actually binary.\n"
    )


def build_grounded_prompt(
    query: str,
    retrieved_chunks: List[Dict],
    response_format: str = "default",
    retrieval_mode: str = "default",
    coverage_mode: str = "narrow_lookup",
    coverage_truncated: bool = False,
) -> str:
    """
    Constructs a strict but slightly more reasonable grounding prompt.
    """
    grounding = get_session_grounding()
    grounding_str = ""
    if grounding:
        grounding_str = (
            f"AGENT CONTEXT:\n"
            f"- Current Datetime: {grounding.get('current_datetime')}\n"
            f"- Timezone: {grounding.get('timezone')}\n"
            f"- Location: {grounding.get('location')}\n"
            f"- Purpose: {grounding.get('agent_purpose')}\n\n"
        )

    if not retrieved_chunks:
        return (
            f"{grounding_str}"
            f"QUESTION:\n{query}\n\n"
            f"INSTRUCTIONS:\n"
            f"- You have no context provided.\n"
            f"- Say exactly: 'Insufficient information' and nothing else.\n"
        )

    context_blocks = []
    for chunk in retrieved_chunks:
        doc_name = chunk.get("document_name", "Unknown")
        chunk_idx = chunk.get("chunk_index", "Unknown")
        text = chunk.get("text", "")
        block = f"[Doc: {doc_name} | Chunk {chunk_idx}]\n{text}"
        context_blocks.append(block)

    context_str = "\n\n".join(context_blocks)
    format_instruction_block = build_format_specific_instructions(response_format, retrieval_mode)
    coverage_honesty_block = (
        "- If the question asks for all items or a full summary, only claim completeness if the provided context appears to cover the full relevant set. Otherwise state that the answer is based on the retrieved records.\n"
        if coverage_mode == "coverage_required"
        else ""
    )
    coverage_truncation_block = (
        "- The retrieved evidence was truncated to a bounded subset, so explicitly note that the answer may be partial.\n"
        if coverage_truncated
        else ""
    )

    return (
        f"{grounding_str}"
        f"CONTEXT:\n\n{context_str}\n\n"
        f"QUESTION:\n{query}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Only use the provided context to answer the question.\n"
        f"- Do not use outside knowledge.\n"
        f"- Do not guess.\n"
        f"- If the answer is not supported by the context at all, say exactly: 'Insufficient information'.\n"
        f"- Do not claim that the document does not mention something unless the retrieved context explicitly supports that negative conclusion.\n"
        f"- If the question asks for an exact term or reference and the retrieved context does not show it directly, say exactly: 'Insufficient information'.\n"
        f"- If the retrieved evidence only shows weak or near matches, use bounded wording such as 'No relevant matches were found in the retrieved evidence' or 'Insufficient information'.\n"
        f"- Do not use any prior knowledge or external frameworks not explicitly present in the context.\n"
        f"- Cite your sources for every claim using the format [Doc: name | Chunk X].\n"
        f"{coverage_honesty_block}"
        f"{coverage_truncation_block}"
        f"{format_instruction_block}"
    )

def build_chat_with_document_prompt(query: str, document_name: str, full_text: str) -> str:
    """
    Constructs a prompt for Chat mode when a full document is provided as context.
    Allows for summarization, explanation, interpretation and Q&A over the whole document.
    """
    grounding = get_session_grounding()
    grounding_str = ""
    if grounding:
        grounding_str = (
            f"AGENT CONTEXT:\n"
            f"- Current Datetime: {grounding.get('current_datetime')}\n"
            f"- Timezone: {grounding.get('timezone')}\n"
            f"- Location: {grounding.get('location')}\n"
            f"- Purpose: {grounding.get('agent_purpose')}\n\n"
        )

    return (
        f"{grounding_str}"
        f"DOCUMENT CONTEXT (Name: {document_name}):\n\n{full_text}\n\n"
        f"USER QUESTION:\n{query}\n\n"
        f"INSTRUCTIONS:\n"
        f"- You are in Chat mode with a full document as context.\n"
        f"- Use the provided document as your primary source of information.\n"
        f"- You may summarize, explain, interpret, and answer questions about the document as a whole.\n"
        f"- Your answers should be natural and conversational.\n"
        f"- If the answer is not supported by the document at all, say exactly: 'Insufficient information'.\n"
        f"- Do not use prior knowledge that contradicts or is not supported by the document for specific facts.\n"
    )
