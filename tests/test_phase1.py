import pytest
from polycli.models import Side, OrderType, Order

def test_mock_order():
    # Simple sanity check for models
    order = Order(
        id="o1",
        market_id="m1",
        price=0.5,
        size=10,
        side=Side.BUY,
        type=OrderType.LIMIT,
        status="open",
        timestamp=0.0
    )
    assert order.side == Side.BUY