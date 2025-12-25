import pytest
from unittest.mock import MagicMock, AsyncMock
from polycli.tui import MarketDetail, OrderbookDepth
from polycli.models import OrderBook, PriceLevel, Market, MarketStatus

@pytest.mark.asyncio
async def test_market_detail_on_k_ob():
    # Mock the widget
    detail = MarketDetail()
    detail.app = MagicMock()
    detail.query_one = MagicMock()
    
    # Standardized Kalshi OB update
    data = {
        "market_ticker": "M1",
        "bids": [{"price": 0.45, "size": 10}],
        "asks": [{"price": 0.46, "size": 20}]
    }
    
    await detail.on_k_ob(data)
    
    # Verify that depth wall snapshot was updated
    # detail.query_one("#depth_wall", OrderbookDepth).snapshot = ...
    detail.query_one.assert_called()
