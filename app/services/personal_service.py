import json
import re

from rag.personal_db import (
    bootstrap_personal_data,
    get_connection,
    init_personal_db,
    insert_personal_memory,
    list_personal_memories,
    resolve_personal_entities,
)

from app.config import DB_PATH

NO_FACT_RESPONSE = "I do not have that in your personal store."
NO_ENTITY_RESPONSE = "I do not have any record for that in your personal store."
AMBIGUITY_RESPONSE = "The provided personal store data does not clearly identify that person/fact."

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "do",
    "did",
    "can",
    "could",
    "will",
    "would",
    "s",
    "tell",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "to",
    "was",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "you",
    "your",
}

PERSONAL_FACT_TERMS = {
    "age",
    "birthday",
    "called",
    "communication",
    "dob",
    "email",
    "family",
    "favorite",
    "job",
    "live",
    "lives",
    "name",
    "phone",
    "relationship",
    "reside",
    "resides",
    "spouse",
    "stay",
    "stays",
    "work",
    "works",
}

TOKEN_SYNONYMS = {
    "reside": "live",
    "resides": "live",
    "stay": "live",
    "stays": "live",
}


def initialize_personal_service():
    conn = get_connection(DB_PATH)
    try:
        init_personal_db(conn)
        bootstrap_personal_data(conn)
    finally:
        conn.close()


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    normalized_tokens = []
    for token in tokens:
        if not token or token in STOP_WORDS:
            continue
        normalized_tokens.append(TOKEN_SYNONYMS.get(token, token))
    return set(normalized_tokens)


def _entity_terms(entity: dict) -> set[str]:
    terms = set()
    canonical_name = entity.get("canonical_name")
    relationship = entity.get("relationship_to_user")

    if canonical_name:
        terms.update(tokenize(canonical_name))
    if relationship:
        terms.update(tokenize(relationship))

    aliases_json = entity.get("aliases_json") or "[]"
    try:
        aliases = json.loads(aliases_json)
    except Exception:
        aliases = []

    for alias in aliases:
        terms.update(tokenize(alias))

    return terms


def _is_question(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True

    lowered = stripped.lower()
    return bool(
        re.match(
            r"^(who|what|when|where|why|how|is|are|do|does|did|can|could|would|will)\b", lowered
        )
    )


def _fact_already_exists(conn, fact_text: str) -> bool:
    existing_memories = list_personal_memories(conn, mode="personal")
    normalized_fact = normalize_text(fact_text)
    for memory in existing_memories:
        if (memory.get("category") or "").lower() != "fact":
            continue
        if normalize_text(memory.get("raw_user_input", "")) == normalized_fact:
            return True
    return False


def _store_personal_fact_if_statement(conn, text: str) -> bool:
    if _is_question(text):
        return False

    fact_text = (text or "").strip()
    if not fact_text:
        return False

    if not _fact_already_exists(conn, fact_text):
        insert_personal_memory(
            conn,
            {
                "raw_user_input": fact_text,
                "normalized_text": normalize_text(fact_text),
                "mode": "personal",
                "category": "fact",
            },
        )

    return True


def persist_user_input(text: str, session_id: str | None = None):
    conn = get_connection(DB_PATH)
    try:
        insert_personal_memory(
            conn,
            {
                "raw_user_input": text,
                "normalized_text": normalize_text(text),
                "session_id": session_id,
                "mode": "personal",
                "category": "user_input",
            },
        )
        _store_personal_fact_if_statement(conn, text)
    finally:
        conn.close()


def get_personal_context(query: str):
    conn = get_connection(DB_PATH)
    try:
        resolved_entities = resolve_personal_entities(conn, query)
        memories = list_personal_memories(conn, mode="personal")
        return {
            "resolved_entities": resolved_entities,
            "memories": memories,
        }
    finally:
        conn.close()


def _memory_is_fact(memory: dict) -> bool:
    return (memory.get("category") or "").lower() != "user_input"


def _score_memory(memory: dict, query_terms: set[str], entity_terms: set[str]) -> int:
    memory_terms = tokenize(memory.get("raw_user_input", ""))
    if not memory_terms:
        return 0

    overlap_terms = query_terms.intersection(memory_terms)
    score = len(overlap_terms)
    if entity_terms and entity_terms.intersection(memory_terms):
        score += 2
    return score


def _filter_relevant_memories(
    memories: list[dict],
    query: str,
    resolved_entity: dict | None,
) -> tuple[list[dict], dict]:
    query_terms = tokenize(query)
    entity_terms = _entity_terms(resolved_entity) if resolved_entity else set()
    explicit_name_terms = _extract_possessive_entity_candidates(query).union(
        _extract_named_entity_candidates(query)
    )
    candidate_count = 0

    scored = []
    for memory in memories:
        if not _memory_is_fact(memory):
            continue

        candidate_count += 1
        text = memory.get("raw_user_input", "")
        memory_terms = tokenize(text)
        if not memory_terms:
            continue

        if resolved_entity and entity_terms and not entity_terms.intersection(memory_terms):
            continue

        if explicit_name_terms and not explicit_name_terms.intersection(memory_terms):
            continue

        overlap_terms = query_terms.intersection(memory_terms)
        score = _score_memory(memory, query_terms, entity_terms)
        has_strong_match = len(overlap_terms) >= 2 or (
            query_terms and len(overlap_terms) == len(query_terms)
        )

        if score > 0 and has_strong_match:
            scored.append((score, memory))

    scored.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
    return (
        [memory for _, memory in scored],
        {
            "candidate_count": candidate_count,
            "retrieved_count": len(scored),
            "query_terms": sorted(query_terms),
        },
    )


def _extract_possessive_entity_candidates(query: str) -> set[str]:
    matches = re.findall(r"\b([a-z0-9]+)'s\b", (query or "").lower())
    return {
        candidate
        for candidate in matches
        if candidate not in STOP_WORDS and candidate not in PERSONAL_FACT_TERMS
    }


def _extract_named_entity_candidates(query: str) -> set[str]:
    query_lower = (query or "").lower()
    patterns = [
        r"\bwho is ([a-z0-9]+)\b",
        r"\btell me about ([a-z0-9]+)\b",
        r"\bwhat do you know about ([a-z0-9]+)\b",
    ]

    candidates = set()
    for pattern in patterns:
        for candidate in re.findall(pattern, query_lower):
            if candidate not in STOP_WORDS and candidate not in PERSONAL_FACT_TERMS:
                candidates.add(candidate)
    return candidates


def _query_has_unresolved_entity_reference(query: str) -> bool:
    return bool(
        _extract_possessive_entity_candidates(query) or _extract_named_entity_candidates(query)
    )


def retrieve_personal_store_records(query: str, top_k: int = 3) -> dict:
    context = get_personal_context(query)
    resolved_entities = context["resolved_entities"]
    memories = context["memories"]

    if len(resolved_entities) > 1:
        return {
            "status": "ambiguous",
            "resolved_entities": resolved_entities,
            "memories": [],
            "metrics": {
                "candidate_count": 0,
                "retrieved_count": 0,
                "query_terms": sorted(tokenize(query)),
            },
        }

    resolved_entity = resolved_entities[0] if resolved_entities else None

    relevant_memories, metrics = _filter_relevant_memories(memories, query, resolved_entity)
    relevant_memories = relevant_memories[:top_k]
    metrics["retrieved_count"] = len(relevant_memories)

    if relevant_memories:
        return {
            "status": "records_found",
            "resolved_entities": resolved_entities,
            "memories": relevant_memories,
            "metrics": metrics,
        }

    if resolved_entity:
        return {
            "status": "no_fact",
            "resolved_entities": resolved_entities,
            "memories": [],
            "metrics": metrics,
        }

    if _query_has_unresolved_entity_reference(query):
        return {
            "status": "no_entity",
            "resolved_entities": [],
            "memories": [],
            "metrics": metrics,
        }

    return {
        "status": "no_fact",
        "resolved_entities": [],
        "memories": [],
        "metrics": metrics,
    }
