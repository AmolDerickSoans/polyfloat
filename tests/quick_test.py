# quick_test.py
import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from polycli.providers.polymarket import PolyProvider

async def quick_test():
    provider = PolyProvider(timeout=30.0)
    
    query = input("Enter search query (or press Enter for 'trump'): ").strip() or "trump"
    print(f"\nSearching for: {query}...")
    
    results = await provider.search(query, max_results=5)
    
    if results:
        print(f"\n✅ Found {len(results)} markets:\n")
        for i, m in enumerate(results, 1):
            print(f"{i}. {m.question}")
            print(f"   Status: {m.status.value} | Outcomes: {', '.join(m.outcomes)}\n")
    else:
        print("❌ No results found")

if __name__ == "__main__":
    asyncio.run(quick_test())
