import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from polycli.tui import MarketDetail, OrderbookDepth
from polycli.models import OrderBook, PriceLevel, Market, MarketStatus

@pytest.mark.asyncio
async def test_market_detail_on_k_ob():
    # We avoid setting .app directly as it's a property
    detail = MarketDetail()
    
    # Mock query_one to simulate the child widget
    mock_depth_wall = MagicMock()
    detail.query_one = MagicMock(return_value=mock_depth_wall)
    
    # Standardized Kalshi OB update
    data = {
        "market_ticker": "M1",
        "bids": [{"price": 0.45, "size": 10}],
        "asks": [{"price": 0.46, "size": 20}]
    }
    
    await detail.on_k_ob(data)
    
    # Verify that query_one was called to find depth_wall
    detail.query_one.assert_called_with("#depth_wall", OrderbookDepth)
    # Verify snapshot was updated on the mock depth wall
    assert mock_depth_wall.snapshot is not None
    assert mock_depth_wall.snapshot.market_id == "M1"