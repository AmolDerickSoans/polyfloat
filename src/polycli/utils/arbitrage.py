from typing import Dict, List, Optional
from pydantic import BaseModel

class ArbOpportunity(BaseModel):
    market_name: str
    poly_price: float
    kalshi_price: float
    edge: float
    recommendation: str

def calculate_arbitrage(poly_price: float, kalshi_price: float, threshold: float = 0.03) -> Optional[ArbOpportunity]:
    """Calculate arbitrage opportunity between two prices"""
    edge = abs(poly_price - kalshi_price)
    
    if edge >= threshold:
        rec = "BUY POLY / SELL KALSHI" if poly_price < kalshi_price else "BUY KALSHI / SELL POLY"
        return ArbOpportunity(
            market_name="TRUMP24", # Placeholder for actual mapping logic
            poly_price=poly_price,
            kalshi_price=kalshi_price,
            edge=edge,
            recommendation=rec
        )
    return None
