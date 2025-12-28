import asyncio
from unittest.mock import AsyncMock
from polycli.providers.kalshi import KalshiProvider
import os

async def test_mapping():
    os.environ['KALSHI_KEY_ID'] = 'test'
    os.environ['KALSHI_PRIVATE_KEY_PATH'] = 'test'
    p = KalshiProvider()
    p.api_instance = True
    p.get_public_events = AsyncMock(return_value=[{'event_ticker': 'E1', 'title': 'Test Event', 'status': 'open'}])
    
    events = await p.get_events()
    print(f"Mapped {len(events)} events.")
    print(f"First event: {events[0].id}, Status: {events[0].status}")

if __name__ == "__main__":
    asyncio.run(test_mapping())
