import os
import sys

import pytest


current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from rag.personal_db import get_connection, init_personal_db, insert_personal_entity, insert_personal_memory
from app.services.personal_service import (
    AMBIGUITY_RESPONSE,
    NO_ENTITY_RESPONSE,
    NO_FACT_RESPONSE,
    persist_user_input,
    retrieve_personal_store_records,
)


TEST_DB = "test_personal_spec019.db"


@pytest.fixture
def personal_conn(monkeypatch):
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    from app.services import personal_service

    monkeypatch.setattr(personal_service, "DB_PATH", TEST_DB)
    conn = get_connection(TEST_DB)
    init_personal_db(conn)
    yield conn
    conn.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_personal_mode_returns_relevant_records(personal_conn):
    insert_personal_entity(personal_conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife",
        "aliases_json": '["my wife"]',
    })
    insert_personal_memory(personal_conn, {
        "raw_user_input": "Cornelia's birthday is on 22 November.",
        "mode": "personal",
        "category": "fact",
    })

    result = retrieve_personal_store_records("When is Cornelia's birthday?")

    assert result["status"] == "records_found"
    assert result["memories"][0]["raw_user_input"] == "Cornelia's birthday is on 22 November."
    assert result["metrics"]["retrieved_count"] >= 1


def test_personal_mode_missing_fact_returns_bounded_response(personal_conn):
    insert_personal_entity(personal_conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife",
    })

    result = retrieve_personal_store_records("What is Cornelia's favorite color?")

    assert result["status"] == "no_fact"


def test_personal_mode_missing_entity_returns_bounded_response(personal_conn):
    result = retrieve_personal_store_records("When is Alex's birthday?")

    assert result["status"] == "no_entity"


def test_personal_mode_does_not_borrow_other_persons_fact(personal_conn):
    insert_personal_entity(personal_conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife",
    })
    insert_personal_memory(personal_conn, {
        "raw_user_input": "Cornelia's birthday is on 22 November.",
        "mode": "personal",
        "category": "fact",
    })

    result = retrieve_personal_store_records("When is Nina's birthday?")

    assert result["status"] == "no_entity"
    assert result["memories"] == []


def test_personal_mode_ambiguous_reference_returns_bounded_response(personal_conn):
    insert_personal_entity(personal_conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife",
    })
    insert_personal_entity(personal_conn, {
        "canonical_name": "Lebo",
        "entity_type": "person",
        "relationship_to_user": "wife",
    })

    result = retrieve_personal_store_records("When is my wife's birthday?")

    assert result["status"] == "ambiguous"


def test_personal_mode_does_not_answer_from_user_input_records(personal_conn):
    insert_personal_entity(personal_conn, {
        "canonical_name": "Cornelia",
        "entity_type": "person",
        "relationship_to_user": "wife",
    })
    insert_personal_memory(personal_conn, {
        "raw_user_input": "When is Cornelia's birthday?",
        "mode": "personal",
        "category": "user_input",
    })

    result = retrieve_personal_store_records("When is Cornelia's birthday?")

    assert result["status"] == "no_fact"


def test_personal_mode_statement_is_promoted_to_fact(personal_conn):
    from app.services import personal_service

    personal_service.persist_user_input("Nina's birthday is 11 January.")

    result = retrieve_personal_store_records("When is Nina's birthday?")

    assert result["status"] == "records_found"
    assert result["memories"][0]["raw_user_input"] == "Nina's birthday is 11 January."


def test_personal_mode_residence_statement_is_stored_and_retrievable(personal_conn):
    from app.services import personal_service

    personal_service.persist_user_input("We live in 22 Spes Bona Avenue, Parow, 7500.")

    result = retrieve_personal_store_records("Where do we stay?")

    assert result["status"] == "records_found"
    assert result["memories"][0]["raw_user_input"] == "We live in 22 Spes Bona Avenue, Parow, 7500."


def test_personal_mode_question_is_not_stored_as_fact(personal_conn):
    from app.services import personal_service

    personal_service.persist_user_input("Where do we stay?")
    result = retrieve_personal_store_records("Where do we stay?")

    assert result["status"] == "no_fact"
