import pytest
from polycli.providers.base import BaseProvider
from polycli.models import Market, OrderBook, Trade, Position, Order, OrderType

class MockProvider(BaseProvider):
    async def get_events(self, category=None, limit=100):
        return []
    async def get_markets(self, event_id=None, category=None, limit=100):
        return []
    async def search(self, query):
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

    async def get_news(self, query=None, limit=10):
        return []

@pytest.mark.asyncio
async def test_base_provider_interface():
    provider = MockProvider()
    assert await provider.get_markets() == []
    assert await provider.get_orderbook("test") is None
    assert await provider.get_orders() == []
    assert await provider.get_history() == []
    assert await provider.get_news() == []

def test_instantiation_fails_without_get_news():
    """Ensure BaseProvider requires get_news implementation"""
    class NoNewsProvider(BaseProvider):
        async def get_events(self, category=None, limit=100): pass
        async def get_markets(self, event_id=None, category=None, limit=100): pass
        async def search(self, query): pass
        async def get_orderbook(self, market_id): pass
        async def place_order(self, market_id, side, size, price, order_type=OrderType.LIMIT): pass
        async def cancel_order(self, order_id): pass
        async def get_positions(self): pass
        async def get_orders(self, market_id=None): pass
        async def get_history(self, market_id=None): pass
        # Missing get_news

    with pytest.raises(TypeError) as excinfo:
        NoNewsProvider()
    assert "get_news" in str(excinfo.value)
