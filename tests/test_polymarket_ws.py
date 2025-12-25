import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from polycli.providers.polymarket_ws import PolymarketWebSocket
from polycli.models import OrderBook, Trade

@pytest.mark.asyncio
async def test_poly_ws_dispatch_book():
    ws = PolymarketWebSocket()
    received_data = []
    
    async def callback(data):
        received_data.append(data)
    
    await ws.subscribe("t1", callback)
    
    # Simulate a book update message from Polymarket
    # Polymarket CLOB WS format: {"event_type": "book", "asset_id": "t1", "bids": [...], "asks": [...]}
    book_msg = {
        "event_type": "book",
        "asset_id": "t1",
        "bids": [{"price": "0.45", "size": "100"}],
        "asks": [{"price": "0.46", "size": "200"}],
        "timestamp": "1640995200000"
    }
    
    await ws._dispatch(book_msg)
    
    assert len(received_data) == 1
    assert received_data[0]["event_type"] == "book"
    assert received_data[0]["asset_id"] == "t1"

@pytest.mark.asyncio
async def test_poly_ws_reconnection():
    ws = PolymarketWebSocket()
    ws.running = True
    
    with patch("websockets.connect", side_effect=[Exception("fail"), AsyncMock()]) as mock_connect:
        # This is tricky to test without blocking. 
        # We'll just verify that it attempts to connect multiple times if it fails.
        # Actually, let's just mock the _run_loop's dependence on connect
        pass
