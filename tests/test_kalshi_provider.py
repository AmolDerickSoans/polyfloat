import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from polycli.providers.kalshi import KalshiProvider
from polycli.models import MarketStatus, Side, OrderType, OrderStatus

@pytest.fixture
def provider():
    with patch("polycli.providers.kalshi.KalshiProvider._authenticate"):
        p = KalshiProvider()
        p.api_instance = MagicMock()
        return p

@pytest.mark.asyncio
async def test_kalshi_get_events(provider):
    with patch.object(provider, "get_public_events", new_callable=AsyncMock) as mock_get_public:
        mock_get_public.return_value = [{"event_ticker": "E1", "title": "Election", "subtitle": "Desc", "status": "open"}]
        
        events = await provider.get_events(limit=1)
        assert len(events) == 1
        assert events[0].id == "E1"
        assert events[0].status == MarketStatus.ACTIVE

@pytest.mark.asyncio
async def test_kalshi_get_markets(provider):
    mock_market = MagicMock()
    mock_market.ticker = "M1"
    mock_market.event_ticker = "E1"
    mock_market.title = "Trump wins?"
    mock_market.status = "open"
    mock_market.yes_bid = 45
    mock_market.close_time = "2024-11-05T00:00:00Z"
    
    # Pydantic validation fix: ensure attributes are real strings not MagicMocks
    mock_market.title = "Trump wins?"
    mock_market.ticker = "M1"
    mock_market.event_ticker = "E1"
    mock_market.status = "open"

    mock_resp = MagicMock()
    mock_resp.markets = [mock_market]
    
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_resp)
        
        markets = await provider.get_markets(limit=1)
        assert len(markets) == 1
        assert markets[0].id == "M1"
        assert markets[0].event_id == "E1"

@pytest.mark.asyncio
async def test_kalshi_place_order(provider):
    mock_resp = MagicMock()
    mock_resp.order_id = "o1"
    mock_resp.status = "placed"
    
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_resp)
        
        order = await provider.place_order(
            market_id="M1",
            side=Side.BUY,
            size=10,
            price=0.45
        )
        assert order.id == "o1"
        assert order.status == OrderStatus.OPEN