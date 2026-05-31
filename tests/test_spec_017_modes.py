import httpx
import asyncio

async def test_modes_api():
    url = "http://127.0.0.1:8000/api/chat"

    # Test Chat Mode
    payload_chat = {
        "model": "dummy",
        "message": "When is Cornelia's birthday?",
        "mode": "chat"
    }
    async with httpx.AsyncClient() as client:
        response_chat = await client.post(url, json=payload_chat)
        debug_chat = response_chat.json().get('debug', {})
        print(f"--- Mode: {debug_chat.get('mode')} ---")
        print(f"RAG query: {debug_chat.get('retrieval_query')}")
        print(f"Personal context: {debug_chat.get('personal_context')}")
        print(f"Final Prompt: {debug_chat.get('final_prompt')}")
        print(f"Input persisted: {debug_chat.get('personal_input_persisted')}")

    # Test Document Mode (Auto-activated by doc_ids)
    # Even if we don't have real doc_ids, we can test the branching logic
    payload_doc = {
        "model": "dummy",
        "message": "Is this a document question?",
        "mode": "chat", # Should auto-switch
        "document_ids": ["doc1"]
    }
    async with httpx.AsyncClient() as client:
        response_doc = await client.post(url, json=payload_doc)
        debug_doc = response_doc.json().get('debug', {})
        print(f"\n--- Effective Mode: {debug_doc.get('mode')} ---")
        print(f"RAG query: {debug_doc.get('retrieval_query')}")
        print(f"Personal context: {debug_doc.get('personal_context')}")
        # Note: If RAG doesn't find doc1, it will skip LLM, but the mode branching should work

if __name__ == "__main__":
    asyncio.run(test_modes_api())
