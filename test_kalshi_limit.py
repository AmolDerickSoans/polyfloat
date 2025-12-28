
import asyncio
import os
import json
from dotenv import load_dotenv
load_dotenv(".env", override=True)
from polycli.providers.kalshi import KalshiProvider

async def main():
    provider = KalshiProvider()
    
    for limit in [1]:
        try:
            events = await provider.get_public_events(limit=limit)
            if events:
                print(f"Event Keys: {list(events[0].keys())}")
                print(f"Event Data: {events[0]}")
        except Exception as e:
            print(f"  Failed! {e}")

if __name__ == "__main__":
    asyncio.run(main())
