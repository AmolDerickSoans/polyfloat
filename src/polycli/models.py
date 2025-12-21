from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class PricePoint:
    t: float
    p: float

@dataclass
class PriceSeries:
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
