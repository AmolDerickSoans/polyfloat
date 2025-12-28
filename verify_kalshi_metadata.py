
import asyncio
import os
import json
from dotenv import load_dotenv
load_dotenv(".env", override=True)
from polycli.providers.kalshi import KalshiProvider

async def main():
    provider = KalshiProvider()
    ticker = "KXUSTAKEOVER-30" # A known ticker from previous tests
    print(f"Fetching details for {ticker}...")
    m = await provider.get_market(ticker)
    if m:
        print(f"Title: {m.title}")
        print(f"Extra Data: {json.dumps(m.extra_data, indent=2)}")
        
        # Check specific fields used in TUI
        extra = m.extra_data
        print(f"Status: {extra.get('status')}")
        print(f"Last Price: {extra.get('last_price')}")
        print(f"Open Interest: {extra.get('open_interest')}")
        print(f"Result: {extra.get('result')}")
        print(f"End Date: {m.end_date}")
    else:
        print("Market not found.")

if __name__ == "__main__":
    asyncio.run(main())
