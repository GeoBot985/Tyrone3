import httpx
import json
import asyncio

async def test_personal_mode_api():
    url = "http://127.0.0.1:8000/api/chat"
    payload = {
        "model": "dummy",
        "message": "When is Cornelia's birthday?",
        "mode": "personal"
    }

    async with httpx.AsyncClient() as client:
        # First request to Cornelia (should resolve and retrieve)
        response = await client.post(url, json=payload)
        data = response.json()
        print("--- Personal Mode Response ---")
        # Since LLM is not running, we expect an error in the reply but debug should be populated
        print(f"Reply: {data.get('reply')}")
        debug = data.get('debug', {})
        print(f"Mode: {debug.get('mode')}")
        print(f"Input persisted: {debug.get('personal_input_persisted')}")
        pc = debug.get('personal_context', {})
        print(f"Resolved entities: {[e['canonical_name'] for e in pc.get('resolved_entities', [])]}")
        print(f"Memories retrieved: {len(pc.get('memories', []))}")
        print(f"Final Prompt preview: {debug.get('final_prompt')[:200]}...")

        # Verify persistence by searching for the message we just sent
        payload_search = {
            "model": "dummy",
            "message": "When is Cornelia's birthday?",
            "mode": "personal"
        }
        response2 = await client.post(url, json=payload_search)
        data2 = response2.json()
        pc2 = data2.get('debug', {}).get('personal_context', {})
        print(f"\n--- Second Request (Persistence Check) ---")
        print(f"Memories retrieved: {len(pc2.get('memories', []))}")
        # One of the memories should be the previous message
        found = False
        for mem in pc2.get('memories', []):
            if "When is Cornelia's birthday?" in mem['raw_user_input']:
                found = True
                break
        print(f"Previous message found in memories: {found}")

if __name__ == "__main__":
    asyncio.run(test_personal_mode_api())
