import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from polycli.providers.kalshi_ws import KalshiWebSocket
from polycli.models import OrderBook, Trade

@pytest.mark.asyncio
async def test_kalshi_ws_handle_orderbook():
    ws = KalshiWebSocket()
    received_books = []
    
    async def callback(data):
        received_books.append(data)
    
    ws.add_callback("orderbook", callback)
    
    # Simulate an orderbook snapshot from Kalshi
    snapshot_msg = {
        "type": "orderbook_snapshot",
        "market_ticker": "M1",
        "yes": [[45, 10]], # Price in cents
        "no": [[54, 20]], # No price 54 -> Yes price 100-54=46
    }
    
    await ws._handle_orderbook(snapshot_msg)
    
    assert len(received_books) == 1
    book = received_books[0]
    assert book["bids"][0]["price"] == 0.45
    assert book["bids"][0]["size"] == 10
    assert book["asks"][0]["price"] == 0.46
    assert book["asks"][0]["size"] == 20

@pytest.mark.asyncio
async def test_kalshi_ws_handle_trade():
    ws = KalshiWebSocket()
    received_trades = []
    
    async def callback(data):
        received_trades.append(data)
    
    ws.add_callback("trade", callback)
    
    trade_msg = {
        "type": "trade",
        "market_ticker": "M1",
        "yes_price": 45,
        "count": 5,
        "taker_side": "yes",
        "ts": 1640995200
    }
    
    await ws._handle_trade(trade_msg)
    
    assert len(received_trades) == 1
    trade = received_trades[0]
    assert trade["price"] == 0.45
    assert trade["size"] == 5
    assert trade["side"] == "buy"
