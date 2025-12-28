
import asyncio
import os
import json
import time
from dotenv import load_dotenv
load_dotenv(".env", override=True)
from polycli.providers.kalshi import KalshiProvider

async def main():
    print("Initializing KalshiProvider...")
    provider = KalshiProvider()

    # Auth check
    if not provider.api_instance:
        print("ERROR: api_instance is None. Authentication failed.")
        return
    else:
        print("✓ api_instance initialized successfully.")

    # Test get_markets with various limits
    print("\n--- Testing get_markets ---")
    for limit in [50, 100, 200, 300, 500]:
        print(f"Testing get_markets limit={limit}...")
        start_time = time.time()
        try:
            markets = await provider.get_markets(limit=limit)
            duration = time.time() - start_time
            print(f"  ✓ Success! Fetched {len(markets)} markets in {duration:.2f}s.")
            if markets:
                print(f"    Sample: {markets[0].title} ({markets[0].token_id}) - ${markets[0].price:.2f}")
        except Exception as e:
            print(f"  ✗ Failed! {e}")

    # Test get_public_events with various limits
    print("\n--- Testing get_public_events ---")
    for limit in [50, 100, 200, 300]:
        print(f"Testing get_public_events limit={limit}...")
        start_time = time.time()
        try:
            events = await provider.get_public_events(limit=limit)
            duration = time.time() - start_time
            print(f"  ✓ Success! Fetched {len(events)} events in {duration:.2f}s.")
            if events:
                sample = events[0]
                print(f"    Sample: {sample.get('title', 'No title')} ({sample.get('ticker', 'No ticker')})")
        except Exception as e:
            print(f"  ✗ Failed! {e}")

if __name__ == "__main__":
    asyncio.run(main())
