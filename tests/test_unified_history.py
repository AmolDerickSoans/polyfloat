import pytest
from unittest.mock import AsyncMock, MagicMock
from polycli.providers.base import BaseProvider
from polycli.models import Trade, Side
from polycli.utils.arbitrage import aggregate_history

class MockProvider(BaseProvider):
    async def get_events(self, category=None, limit=100): return []
    async def get_markets(self, event_id=None, category=None, limit=100): return []
    async def get_orderbook(self, market_id): return None
    async def place_order(self, market_id, side, size, price, order_type=None): return None
    async def cancel_order(self, order_id): return True
    async def get_positions(self): return []
    async def get_orders(self, market_id=None): return []
    async def get_history(self, market_id=None):
        return []

@pytest.mark.asyncio
async def test_unified_history_aggregator():
    p1 = MockProvider()
    p1.get_history = AsyncMock(return_value=[
        Trade(id="t1", market_id="m1", price=0.5, size=10, side=Side.BUY, timestamp=100)
    ])
    
    p2 = MockProvider()
    p2.get_history = AsyncMock(return_value=[
        Trade(id="t2", market_id="m2", price=0.6, size=20, side=Side.SELL, timestamp=150)
    ])
    
    unified = await aggregate_history([p1, p2])
    
    assert len(unified) == 2
    # Should be sorted by timestamp descending
    assert unified[0].id == "t2"
    assert unified[1].id == "t1"