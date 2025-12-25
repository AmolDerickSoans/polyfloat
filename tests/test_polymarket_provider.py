import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from polycli.providers.polymarket import PolyProvider
from polycli.models import MarketStatus, Side, OrderType, OrderStatus

@pytest.fixture
def provider():
    return PolyProvider(private_key="0x" + "1" * 64, funder_address="0x" + "2" * 40)

@pytest.mark.asyncio
async def test_poly_get_events(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": "e1", "title": "Election", "description": "Desc", "slug": "election", "active": True}]
    
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client

    with patch("httpx.AsyncClient", return_value=mock_client):
        events = await provider.get_events(limit=1)
        assert len(events) == 1
        assert events[0].id == "e1"
        assert events[0].status == MarketStatus.ACTIVE

@pytest.mark.asyncio
async def test_poly_get_markets(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{
        "conditionId": "m1", 
        "question": "Trump wins?", 
        "active": True, 
        "outcomePrices": "[0.5, 0.5]", 
        "clobTokenIds": '["t1", "t2"]',
        "endDateIso": "2024-11-05T00:00:00Z"
    }]
    
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client

    with patch("httpx.AsyncClient", return_value=mock_client):
        markets = await provider.get_markets(limit=1)
        assert len(markets) == 1
        assert markets[0].id == "m1"
        assert markets[0].status == MarketStatus.ACTIVE

@pytest.mark.asyncio
async def test_poly_place_order(provider):
    with patch.object(provider.client, "create_and_post_order", return_value={"orderID": "o1", "status": "LIVE"}):
        order = await provider.place_order(
            market_id="m1",
            side=Side.BUY,
            size=100,
            price=0.45
        )
        assert order.id == "o1"
        assert order.status == OrderStatus.OPEN

@pytest.mark.asyncio
async def test_poly_get_orders(provider):
    with patch.object(provider.client, "get_orders", return_value=[{"orderID": "o1", "assetID": "t1", "price": "0.45", "size": "100", "side": "BUY"}]):
        orders = await provider.get_orders()
        assert len(orders) == 1
        assert orders[0].id == "o1"