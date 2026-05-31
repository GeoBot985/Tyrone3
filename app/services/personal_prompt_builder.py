def build_personal_grounded_prompt(query: str, resolved_entities: list[dict], memories: list[dict]) -> str:
    """
    Builds a strict retrieved-store-only prompt for Personal Mode.
    The LLM may answer only from the provided personal-store records.
    """
    entity_lines = []
    for entity in resolved_entities:
        entity_lines.append(
            f"- {entity['canonical_name']} ({entity['entity_type']}), relationship: "
            f"{entity.get('relationship_to_user', 'N/A')}, aliases: {entity.get('aliases_json', '[]')}"
        )

    memory_lines = []
    for index, memory in enumerate(memories, start=1):
        memory_lines.append(
            f"[Record {index} | {memory['created_at']}]: {memory['raw_user_input']}"
        )

    entity_block = "\n".join(entity_lines) if entity_lines else "None"
    memory_block = "\n".join(memory_lines) if memory_lines else "None"

    return (
        "You are answering in Personal Mode.\n\n"
        "The retrieved personal-store records below are the only allowed source of truth.\n"
        "Do not use outside knowledge, world knowledge, hidden memory, or model knowledge.\n"
        "Do not guess.\n"
        "Do not infer missing personal facts.\n"
        "If the answer is not explicitly present in the provided personal-store records, "
        "say exactly: 'I do not have that in your personal store.'\n\n"
        f"USER QUESTION:\n{query}\n\n"
        f"RESOLVED PERSONAL ENTITIES:\n{entity_block}\n\n"
        f"RETRIEVED PERSONAL-STORE RECORDS:\n{memory_block}\n\n"
        "ANSWER:"
    )
