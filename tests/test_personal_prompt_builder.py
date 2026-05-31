from app.services.personal_prompt_builder import build_personal_grounded_prompt


def test_personal_prompt_is_store_only():
    prompt = build_personal_grounded_prompt(
        "When is Cornelia's birthday?",
        [
            {
                "canonical_name": "Cornelia",
                "entity_type": "person",
                "relationship_to_user": "wife",
                "aliases_json": '["my wife"]',
            }
        ],
        [
            {
                "created_at": "2026-04-04T10:00:00+00:00",
                "raw_user_input": "Cornelia's birthday is on 22 November.",
            }
        ],
    )

    assert "only allowed source of truth" in prompt
    assert "Do not use outside knowledge" in prompt
    assert "Do not guess." in prompt
    assert "Do not infer missing personal facts." in prompt
    assert "I do not have that in your personal store." in prompt
    assert "When is Cornelia's birthday?" in prompt
    assert "Cornelia's birthday is on 22 November." in prompt
