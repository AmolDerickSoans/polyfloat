import asyncio
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from polycli.models import Trade

class ArbOpportunity(BaseModel):
    market_name: str
    poly_price: float
    kalshi_price: float
    edge: float
    direction: str  # e.g., "Poly Yes / Kalshi No"
    recommendation: str
    poly_id: str
    kalshi_id: str

def calculate_arbitrage(poly_price: float, kalshi_price: float, threshold: float = 0.03) -> Optional[ArbOpportunity]:
    """Calculate arbitrage opportunity between two prices (simplified)"""
    edge = abs(poly_price - kalshi_price)
    
    if edge >= threshold:
        rec = "BUY POLY / SELL KALSHI" if poly_price < kalshi_price else "BUY KALSHI / SELL POLY"
        return ArbOpportunity(
            market_name="Unknown", 
            poly_price=poly_price,
            kalshi_price=kalshi_price,
            edge=edge,
            direction="Direct Comparison",
            recommendation=rec,
            poly_id="N/A",
            kalshi_id="N/A"
        )
    return None

def find_opportunities(matches: List[Dict], min_edge: float = 0.02, fee_poly: float = 0.002, fee_kalshi: float = 0.01) -> List[ArbOpportunity]:
    """
    Find arbitrage opportunities from matched markets.
    Direction 1: Buy Poly Yes (pm.price) + Buy Kalshi No (1 - km.price)
    Direction 2: Buy Poly No (1 - pm.price) + Buy Kalshi Yes (km.price)
    Total cost = Price1 + Price2. If < 1.0, there's a theoretical arb.
    """
    opportunities = []
    
    for match in matches:
        pm: MarketData = match["poly"]
        km: MarketData = match["kalshi"]
        
        # Direction 1: Poly YES + Kalshi NO
        # Poly YES cost is pm.price
        # Kalshi NO cost is approx (1 - km.price)
        cost1 = pm.price + (1.0 - km.price)
        edge1 = 1.0 - cost1 - (fee_poly + fee_kalshi)
        
        # Direction 2: Poly NO + Kalshi YES
        # Poly NO cost is approx (1 - pm.price)
        # Kalshi YES cost is km.price
        cost2 = (1.0 - pm.price) + km.price
        edge2 = 1.0 - cost2 - (fee_poly + fee_kalshi)
        
        best_edge = max(edge1, edge2)
        if best_edge >= min_edge:
            direction = "Poly YES + Kalshi NO" if edge1 > edge2 else "Poly NO + Kalshi YES"
            rec = f"BUY {direction.split(' + ')[0]} & {direction.split(' + ')[1]}"
            
            opportunities.append(ArbOpportunity(
                market_name=pm.title,
                poly_price=pm.price,
                kalshi_price=km.price,
                edge=best_edge,
                direction=direction,
                recommendation=rec,
                poly_id=pm.token_id,
                kalshi_id=km.token_id
            ))
            
    return sorted(opportunities, key=lambda x: x.edge, reverse=True)

async def aggregate_history(providers: List[Any], market_id: Optional[str] = None) -> List[Trade]:
    """Aggregate trade history from multiple providers and sort by timestamp"""
    tasks = [p.get_history(market_id) for p in providers]
    results = await asyncio.gather(*tasks)
    
    all_trades = []
    for trades in results:
        all_trades.extend(trades)
        
    all_trades.sort(key=lambda x: x.timestamp, reverse=True)
    return all_trades

