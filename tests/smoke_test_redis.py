import asyncio
import json
import time
from polycli.storage.redis_store import RedisStore

async def smoke_test():
    store = RedisStore(prefix="polycli:")
    if not store._redis:
        print("Redis not available")
        return

    # Test case: Command results
    # We want to ensure that one round of json.loads(msg["data"]) results in a DICT, not a STR
    channel = "command:results"
    test_payload = {"command": "TEST", "result": "Success"}
    
    # 1. Clear old messages if possible or just subscribe
    pubsub = await store.subscribe(channel)
    
    # 2. Publish (using our fixed internal logic: store.publish calls json.dumps once)
    await store.publish(channel, test_payload)
    
    # 3. Listen for the message
    async for msg in pubsub.listen():
        if msg["type"] == "message":
            print(f"Raw data from Redis: {repr(msg['data'])}")
            try:
                data = json.loads(msg["data"])
                print(f"After one json.loads: {type(data)} -> {data}")
                if isinstance(data, dict):
                    print("SUCCESS: Data is a dictionary as expected by TUI.")
                else:
                    print("FAILURE: Data is still a string (double encoded).")
            except Exception as e:
                print(f"ERROR: {e}")
            break
    
    await store.close()

if __name__ == "__main__":
    asyncio.run(smoke_test())
