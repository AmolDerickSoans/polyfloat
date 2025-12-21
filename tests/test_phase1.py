import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from polycli.providers.polymarket import PolyProvider
from polycli.providers.polymarket_ws import PolymarketWebSocket
from polycli.providers.base import OrderArgs, OrderSide, OrderType

@pytest.fixture
def poly_provider():
    # Valid 32-byte hex string (64 chars)
    dummy_key = "0x" + "a" * 64
    dummy_funder = "0x" + "b" * 40
    return PolyProvider(private_key=dummy_key, funder_address=dummy_funder)

@pytest.mark.asyncio
async def test_get_markets_gamma(poly_provider):
    # Mock httpx.AsyncClient.get
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "conditionId": "0x1",
            "question": "Test Market?",
            "category": "Politics",
            "outcomePrices": ["0.4", "0.6"],
            "volume24hr": 1000,
            "liquidity": 5000,
            "endDateIso": "2024-12-31"
        }
    ]
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        markets = await poly_provider.get_markets(limit=1)
        
    assert len(markets) == 1
    assert markets[0].title == "Test Market?"
    assert markets[0].price == 0.4
    assert markets[0].volume_24h == 1000

@pytest.mark.asyncio
async def test_get_positions_data(poly_provider):
    # Mock Data API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"title": "Market A", "size": 100}]
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        positions = await poly_provider.get_positions()
        
    assert len(positions) == 1
    assert positions[0]["title"] == "Market A"

@pytest.mark.asyncio
async def test_ws_dispatch():
    ws_client = PolymarketWebSocket()
    callback = AsyncMock()
    
    # Manually populate subscriptions for test
    from typing import Set, Callable, Dict, Any
    ws_client.subscriptions["token_123"] = {callback}
    
    # Simulate incoming message
    message = {"asset_id": "token_123", "price": 0.55}
    await ws_client._dispatch(message)
    
    callback.assert_called_once_with(message)

@pytest.mark.asyncio
async def test_ws_reconnect():
    ws_client = PolymarketWebSocket()
    
    with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
        # Mock connection context manager
        mock_ws = AsyncMock()
        mock_ws.open = True
        mock_connect.return_value.__aenter__.return_value = mock_ws
        
        # Start loop
        ws_client.start()
        await asyncio.sleep(0.1)
        await ws_client.stop()
        
        assert mock_connect.called
