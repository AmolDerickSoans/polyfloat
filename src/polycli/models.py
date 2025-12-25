from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

class MarketStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLVED = "resolved"

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"

class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

class Event(BaseModel):
    id: str
    provider: str
    title: str
    description: str
    status: MarketStatus
    markets: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Market(BaseModel):
    id: str
    event_id: str
    provider: str
    question: str
    status: MarketStatus
    outcomes: List[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PriceLevel(BaseModel):
    price: float
    size: float

class OrderBook(BaseModel):
    market_id: str
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: float

class Trade(BaseModel):
    id: str
    market_id: str
    price: float
    size: float
    side: Side
    timestamp: float

class Order(BaseModel):
    id: str
    market_id: str
    price: float
    size: float
    side: Side
    type: OrderType
    status: OrderStatus
    timestamp: float

class Position(BaseModel):
    market_id: str
    outcome: str
    size: float
    avg_price: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

@dataclass
class PricePoint:
    t: float
    p: float

@dataclass
class PriceSeries:
    name: str  # e.g. "Trump", "Yes", "No"
    color: str # Hex code
    points: List[PricePoint] = field(default_factory=list)
    max_size: int = 1000

    def append(self, p: float, t: float) -> None:
        self.points.append(PricePoint(t=t, p=p))
        if len(self.points) > self.max_size:
            self.points = self.points[-self.max_size:]

    def prices(self) -> List[float]:
        return [pt.p for pt in self.points]
    
    def timestamps(self) -> List[float]:
        return [pt.t for pt in self.points]

@dataclass
class MultiLineSeries:
    title: str
    traces: List[PriceSeries] = field(default_factory=list)
    
    def add_trace(self, trace: PriceSeries) -> None:
        self.traces.append(trace)

@dataclass
class OrderBookSnapshot:
    bids: List[Dict[str, Any]] = field(default_factory=list)
    asks: List[Dict[str, Any]] = field(default_factory=list)

    def imbalance(self) -> float:
        bid_vol = sum(float(b["size"]) for b in self.bids)
        ask_vol = sum(float(a["size"]) for a in self.asks)
        return bid_vol - ask_vol
    
    def spread(self) -> Optional[float]:
        if not self.bids or not self.asks:
            return None
        # Assuming bids are sorted descending and asks ascending
        best_bid = float(self.bids[0]["price"])
        best_ask = float(self.asks[0]["price"])
        return best_ask - best_bid
