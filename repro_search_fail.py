import asyncio
import os
import sys
from polycli.providers.polymarket import PolyProvider
from polycli.providers.kalshi import KalshiProvider

async def check_providers():
    print("Checking Providers Search Functionality...")
    
    # Polymarket Check
    try:
        poly = PolyProvider()
        print("  > Querying Polymarket for 'Trump'...")
        results = await poly.search("Trump")
        print(f"  > Polymarket Results: {len(results)}")
        if not results:
            print("  [WARN] Polymarket returned 0 results. Check API or Query.")
    except Exception as e:
        print(f"  [FAIL] Polymarket Search Error: {e}")

    # Kalshi Check
    try:
        kalshi = KalshiProvider()
        # We need to ensure we can connect first? 
        # search_markets in kalshi provider usually requires auth or public endpoint.
        # Assuming the environment has keys or we skip auth if it's public.
        print("  > Querying Kalshi for 'Fed'...")
        results = await kalshi.search("Fed")
        print(f"  > Kalshi Results: {len(results)}")
        if not results:
             print("  [WARN] Kalshi returned 0 results.")
    except Exception as e:
        print(f"  [FAIL] Kalshi Search Error: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_providers())
