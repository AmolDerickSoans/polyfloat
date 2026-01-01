import pytest
from pydantic import ValidationError
from polycli.models import Event, Market, OrderBook, Trade, Position, Order, MarketStatus, Side, OrderType, OrderStatus

def test_event_model():
    data = {
        "id": "event-123",
        "provider": "polymarket",
        "title": "US Presidential Election 2024",
        "description": "Who will win the election?",
        "status": "active",
        "markets": []
    }
    event = Event(**data)
    assert event.id == "event-123"
    assert event.title == "US Presidential Election 2024"

def test_market_model():
    data = {
        "id": "poly-123",
        "event_id": "event-123",
        "provider": "polymarket",
        "question": "Will Trump win?",
        "status": "active",
        "outcomes": ["Yes", "No"]
    }
    market = Market(**data)
    assert market.id == "poly-123"
    assert market.event_id == "event-123"
    assert market.status == MarketStatus.ACTIVE
    assert "Yes" in market.outcomes

def test_order_book_model():
    data = {
        "market_id": "poly-123",
        "bids": [{"price": 0.45, "size": 100}],
        "asks": [{"price": 0.47, "size": 200}],
        "timestamp": 1640995200.0
    }
    book = OrderBook(**data)
    assert book.market_id == "poly-123"
    assert len(book.bids) == 1
    assert book.bids[0].price == 0.45

def test_trade_model():
    data = {
        "id": "trade-456",
        "market_id": "poly-123",
        "price": 0.46,
        "size": 50,
        "side": "buy",
        "timestamp": 1640995201.0
    }
    trade = Trade(**data)
    assert trade.side == Side.BUY
    assert trade.price == 0.46

def test_order_model():
    data = {
        "id": "order-789",
        "market_id": "poly-123",
        "price": 0.45,
        "size": 100,
        "side": "buy",
        "type": "limit",
        "status": "open",
        "timestamp": 1640995202.0
    }
    order = Order(**data)
    assert order.status == OrderStatus.OPEN
    assert order.type == OrderType.LIMIT

def test_position_model():
    data = {
        "market_id": "poly-123",
        "outcome": "Yes",
        "size": 500,
        "avg_price": 0.42,
        "realized_pnl": 10.5,
        "unrealized_pnl": 5.0
    }
    pos = Position(**data)
    assert pos.size == 500
    assert pos.avg_price == 0.42
