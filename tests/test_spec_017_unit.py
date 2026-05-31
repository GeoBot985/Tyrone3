import os
import sys
import pytest
from datetime import datetime, timezone
import json

# Ensure rag can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from rag.personal_db import (
    get_connection, init_personal_db, insert_personal_memory,
    insert_personal_entity, resolve_personal_entities, retrieve_personal_memories
)

TEST_DB = "test_personal.db"

@pytest.fixture
def conn():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    c = get_connection(TEST_DB)
    init_personal_db(c)
    yield c
    c.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_persistence(conn):
    insert_personal_memory(conn, {
        "raw_user_input": "Hello world",
        "mode": "personal",
        "session_id": "test_session"
    })

    mems = retrieve_personal_memories(conn, "Hello")
    assert len(mems) == 1
    assert mems[0]["raw_user_input"] == "Hello world"
    assert mems[0]["session_id"] == "test_session"

def test_entity_resolution_name(conn):
    insert_personal_entity(conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife"
    })

    resolved = resolve_personal_entities(conn, "When is Cornelia's birthday?")
    assert len(resolved) == 1
    assert resolved[0]["canonical_name"] == "Cornelia"

def test_entity_resolution_alias(conn):
    insert_personal_entity(conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife",
        "aliases_json": json.dumps(["my wife"])
    })

    resolved = resolve_personal_entities(conn, "What is my wife's favorite color?")
    assert len(resolved) == 1
    assert resolved[0]["canonical_name"] == "Cornelia"

def test_entity_resolution_relationship(conn):
    insert_personal_entity(conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife"
    })

    resolved = resolve_personal_entities(conn, "Tell me about my wife.")
    assert len(resolved) == 1
    assert resolved[0]["canonical_name"] == "Cornelia"

def test_retrieval_empty(conn):
    mems = retrieve_personal_memories(conn, "Unknown")
    assert len(mems) == 0
