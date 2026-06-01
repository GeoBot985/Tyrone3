import json
import uuid
from datetime import UTC, datetime

import duckdb
from app.config import RAG_DB_PATH


def get_connection(db_path=RAG_DB_PATH):
    return duckdb.connect(db_path)


def init_personal_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS personal_memories (
        memory_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        raw_user_input TEXT NOT NULL,
        normalized_text TEXT,
        mode TEXT NOT NULL,
        session_id TEXT,
        extracted_entities_json TEXT,
        category TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS personal_entities (
        entity_id TEXT PRIMARY KEY,
        canonical_name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        relationship_to_user TEXT,
        aliases_json TEXT,
        notes_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)


def insert_personal_memory(conn, memory: dict) -> None:
    conn.execute(
        """
        INSERT INTO personal_memories (
            memory_id, created_at, raw_user_input, normalized_text,
            mode, session_id, extracted_entities_json, category
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            memory.get("memory_id", uuid.uuid4().hex),
            memory.get("created_at", datetime.now(UTC).isoformat()),
            memory["raw_user_input"],
            memory.get("normalized_text"),
            memory.get("mode", "personal"),
            memory.get("session_id"),
            memory.get("extracted_entities_json"),
            memory.get("category"),
        ],
    )


def insert_personal_entity(conn, entity: dict) -> None:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO personal_entities (
            entity_id, canonical_name, entity_type, relationship_to_user,
            aliases_json, notes_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            entity.get("entity_id", uuid.uuid4().hex),
            entity["canonical_name"],
            entity["entity_type"],
            entity.get("relationship_to_user"),
            entity.get("aliases_json", "[]"),
            entity.get("notes_json", "[]"),
            entity.get("created_at", now),
            entity.get("updated_at", now),
        ],
    )


def list_personal_entities(conn) -> list[dict]:
    results = conn.execute("SELECT * FROM personal_entities").fetchall()
    cols = [
        "entity_id",
        "canonical_name",
        "entity_type",
        "relationship_to_user",
        "aliases_json",
        "notes_json",
        "created_at",
        "updated_at",
    ]
    return [dict(zip(cols, r)) for r in results]


def resolve_personal_entities(conn, query: str) -> list[dict]:
    # Very simple resolution: exact match on name, alias, or relationship
    # Lowercase everything for comparison
    query_lower = query.lower()
    entities = list_personal_entities(conn)
    resolved = []

    for ent in entities:
        matched = False
        # Check canonical name
        if ent["canonical_name"].lower() in query_lower:
            matched = True

        # Check aliases
        if not matched and ent["aliases_json"]:
            try:
                aliases = json.loads(ent["aliases_json"])
                for alias in aliases:
                    if alias.lower() in query_lower:
                        matched = True
                        break
            except Exception:
                pass

        # Check relationship
        if not matched and ent["relationship_to_user"]:
            if ent["relationship_to_user"].lower() in query_lower:
                matched = True

        if matched:
            resolved.append(ent)

    return resolved


def retrieve_personal_memories(conn, query: str, top_k: int = 5) -> list[dict]:
    # Lexical search for now as per spec
    # We'll use simple keyword matching or LIKE.
    # For better results, we could split query into keywords.

    # Let's try simple LIKE first
    search_pattern = f"%{query}%"
    results = conn.execute(
        """
        SELECT * FROM personal_memories
        WHERE raw_user_input ILIKE ?
        ORDER BY created_at DESC
        LIMIT ?
    """,
        [search_pattern, top_k],
    ).fetchall()

    cols = [
        "memory_id",
        "created_at",
        "raw_user_input",
        "normalized_text",
        "mode",
        "session_id",
        "extracted_entities_json",
        "category",
    ]
    return [dict(zip(cols, r)) for r in results]


def list_personal_memories(conn, mode: str = "personal") -> list[dict]:
    results = conn.execute(
        """
        SELECT * FROM personal_memories
        WHERE mode = ?
        ORDER BY created_at DESC
    """,
        [mode],
    ).fetchall()

    cols = [
        "memory_id",
        "created_at",
        "raw_user_input",
        "normalized_text",
        "mode",
        "session_id",
        "extracted_entities_json",
        "category",
    ]
    return [dict(zip(cols, r)) for r in results]


def bootstrap_personal_data(conn):
    # Check if Cornelia already exists
    exists = conn.execute(
        "SELECT 1 FROM personal_entities WHERE canonical_name = 'Cornelia'"
    ).fetchone()
    if not exists:
        insert_personal_entity(
            conn,
            {
                "canonical_name": "Cornelia",
                "entity_type": "person",
                "relationship_to_user": "wife",
                "aliases_json": json.dumps(["my wife"]),
                "notes_json": json.dumps(["Birthday is 22nd November"]),
            },
        )
        print("Bootstrapped Cornelia entity.")

    # Check if we have some memories
    mem_exists = conn.execute(
        "SELECT 1 FROM personal_memories WHERE raw_user_input LIKE '%Cornelia%'"
    ).fetchone()
    if not mem_exists:
        insert_personal_memory(
            conn,
            {
                "raw_user_input": "Cornelia's birthday is on 22 November.",
                "mode": "personal",
                "category": "fact",
            },
        )
        insert_personal_memory(
            conn,
            {
                "raw_user_input": "We decided to use WhatsApp for family communication.",
                "mode": "personal",
                "category": "fact",
            },
        )
        print("Bootstrapped personal memories.")
