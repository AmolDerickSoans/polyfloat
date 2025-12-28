
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

    # Test check_connection
    print("Testing check_connection...")
    try:
        connected = await provider.check_connection()
        print(f"✓ check_connection: {connected}")
    except Exception as e:
        print(f"✗ check_connection failed: {e}")

    queries = ["Mars", "KXUSTAKEOVER", "Elon", "Pope", "Trump", "Election", "NBA", "Crypto", "Weather", "", "test"]

    for query in queries:
        print(f"\n--- Searching for '{query}' ---")
        start_time = time.time()
        try:
            results = await provider.search(query)
            duration = time.time() - start_time
            print(f"Found {len(results)} results in {duration:.2f}s.")
            if results:
                for i, res in enumerate(results[:5]):
                    print(f"  [{i}] {res.title} ({res.token_id}) - ${res.price:.2f}")
            else:
                print("  No results.")
        except Exception as e:
            print(f"  Search Failed for '{query}': {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
