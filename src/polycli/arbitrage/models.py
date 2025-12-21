from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum
from polycli.providers.base import MarketData

class MarketType(str, Enum):
    MONEYLINE = "MONEYLINE"
    SPREAD = "SPREAD"
    TOTAL = "TOTAL"

class MarketPair(BaseModel):
    """
    Links a Kalshi market to a Polymarket market.
    """
    id: str
    league: str
    market_type: MarketType
    description: str
    
    # Kalshi side
    kalshi_ticker: str
    kalshi_market: Optional[MarketData] = None
    
    # Polymarket side
    poly_slug: str
    poly_token_id: Optional[str] = None
    poly_market: Optional[MarketData] = None
    
    # Metadata
    team_suffix: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True

class ArbOpportunity(BaseModel):
    """
    Represents a detected arbitrage opportunity.
    """
    pair_id: str
    timestamp: float
    
    # Costs to buy $1.00 payout
    cost_poly_yes_kalshi_no: float
    cost_kalshi_yes_poly_no: float
    
    # Best execution path
    profit_poly_yes_kalshi_no: float  # (1.0 - cost - fees)
    profit_kalshi_yes_poly_no: float
    
    # Details
    poly_yes_price: float
    kalshi_no_price: float
    kalshi_yes_price: float
    poly_no_price: float
    
    def best_strategy(self) -> str:
        if self.profit_poly_yes_kalshi_no > self.profit_kalshi_yes_poly_no:
            return "Buy Poly YES / Kalshi NO"
        else:
            return "Buy Kalshi YES / Poly NO"
    
    def max_profit(self) -> float:
        return max(self.profit_poly_yes_kalshi_no, self.profit_kalshi_yes_poly_no)

    def is_profitable(self) -> bool:
        return self.max_profit() > 0
