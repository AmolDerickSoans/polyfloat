import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from polycli.providers.polymarket import PolyProvider

async def test_search():
    # Use higher timeout for the test to avoid easy failures
    provider = PolyProvider(timeout=30.0)
    
    query = "election"
    print(f"Searching for: {query}")
    results = await provider.search(query)
    
    print(f"Found {len(results)} markets")
    for market in results[:5]:
        print(f"  - {market.question}")
        print(f"    ID: {market.id}")
        print(f"    Status: {market.status}")
        print(f"    Outcomes: {market.outcomes}")
        print()

if __name__ == "__main__":
    asyncio.run(test_search())
