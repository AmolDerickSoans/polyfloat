"""Data models for paper trading."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid


class PaperOrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaperOrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class PaperOrder:
    """Represents a paper trading order."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    token_id: str = ""
    market_id: str = ""
    side: PaperOrderSide = PaperOrderSide.BUY
    amount: Decimal = Decimal("0")  # Dollar amount for buys, shares for sells
    price: Optional[Decimal] = None  # None for market orders
    status: PaperOrderStatus = PaperOrderStatus.PENDING
    filled_amount: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    provider: str = "polymarket"  # or "kalshi"


@dataclass
class PaperPosition:
    """Represents a paper trading position."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    token_id: str = ""
    market_id: str = ""
    outcome: str = ""  # "YES" or "NO"
    size: Decimal = Decimal("0")  # Number of shares
    avg_price: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    provider: str = "polymarket"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PaperTrade:
    """Represents an executed paper trade."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""
    token_id: str = ""
    market_id: str = ""
    side: PaperOrderSide = PaperOrderSide.BUY
    price: Decimal = Decimal("0")
    size: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    provider: str = "polymarket"
    executed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PaperWallet:
    """Represents the paper trading wallet state."""
    balance: Decimal = Decimal("1000.00")  # Starting balance
    initial_balance: Decimal = Decimal("1000.00")
    total_deposited: Decimal = Decimal("1000.00")
    total_withdrawn: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    provider: str = "polymarket"
