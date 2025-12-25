import pytest
from polycli.providers.base import BaseProvider
from polycli.models import Market, OrderBook, Trade, Position, Order, OrderType

class MockProvider(BaseProvider):
    async def get_markets(self, category=None, limit=100):
        return []
    async def get_orderbook(self, market_id):
        return None
    async def place_order(self, market_id, side, size, price, order_type=OrderType.LIMIT):
        return None
    async def cancel_order(self, order_id):
        return False
    async def get_positions(self):
        return []
    async def get_orders(self, market_id=None):
        return []
    async def get_history(self, market_id=None):
        return []

@pytest.mark.asyncio
async def test_base_provider_interface():
    provider = MockProvider()
    assert await provider.get_markets() == []
    assert await provider.get_orderbook("test") is None
    assert await provider.get_orders() == []
    assert await provider.get_history() == []
