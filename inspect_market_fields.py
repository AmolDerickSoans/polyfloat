
import asyncio
import os
import kalshi_python
from dotenv import load_dotenv
load_dotenv(".env", override=True)
from polycli.providers.kalshi import KalshiProvider

async def main():
    provider = KalshiProvider()
    resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: provider.api_instance.get_markets(limit=1, status="open")
    )
    markets = getattr(resp, "markets", [])
    if markets:
        m = markets[0]
        print(f"Market Ticker: {m.ticker}")
        print(f"All keys: {sorted(dir(m))}")
        print(f"Subtitle: {getattr(m, 'subtitle', 'N/A')}")
        print(f"Event Ticker: {getattr(m, 'event_ticker', 'N/A')}")
        print(f"Series Ticker: {getattr(m, 'series_ticker', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(main())
