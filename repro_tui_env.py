
import os
import asyncio
from dotenv import load_dotenv

# Simulate TUI startup logic (which now calls load_dotenv)
load_dotenv()

from polycli.providers.kalshi import KalshiProvider

async def main():
    print(f"DEBUG: SHELL_KEY_ID={os.getenv('KALSHI_KEY_ID')}")
    
    provider = KalshiProvider()
    print(f"DEBUG: Provider API Instance: {provider.api_instance}")
    
    if provider.api_instance:
        print("SUCCESS: Auth worked")
    else:
        print("FAILURE: Auth failed")

    res = await provider.search("Mars")
    print(f"Search Results: {len(res)}")

if __name__ == "__main__":
    asyncio.run(main())
