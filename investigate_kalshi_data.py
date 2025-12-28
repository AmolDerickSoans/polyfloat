
import asyncio
import os
from polycli.providers.kalshi import KalshiProvider

async def main():
    # Set Credentials 
    os.environ["KALSHI_KEY_ID"] = "0248916e-2f36-4245-830b-a0931d6fd387"
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = "/Users/amoldericksoans/Documents/polyfloat/private.pem"
    os.environ["KALSHI_API_HOST"] = "https://api.elections.kalshi.com/trade-api/v2"

    provider = KalshiProvider()
    if provider.config:
        provider.config.host = "https://api.elections.kalshi.com/trade-api/v2"

    print("--- Verifying get_public_events ---")
    events = await provider.get_public_events(limit=5)
    print(f"Fetched {len(events)} events.")
    if len(events) > 0:
        print(f"Sample Event: {events[0].get('title')}")
    else:
        print("FAILED: No events returned.")

    print("\n--- Verifying SEARCH ---")
    # Search for something known like "Mars" or "Pope" or "Government"
    query = "Mars"
    print(f"Searching for '{query}'...")
    results = await provider.search(query)
    print(f"Found {len(results)} results.")
    
    for r in results:
        print(f"Result: {r.title} | ID: {r.token_id} | Price: {r.price}")
        # Verify ID is a market ticker (contains hyphens usually)
        if "-" not in r.token_id:
            print(f"  [WARNING] Token ID '{r.token_id}' looks like a Series Ticker, not a Market Ticker!")
        else:
            print(f"  [OK] Token ID looks tradeable.")

if __name__ == "__main__":
    asyncio.run(main())
