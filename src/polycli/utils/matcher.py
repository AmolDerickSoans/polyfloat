from rapidfuzz import fuzz
from typing import List, Dict, Any
from polycli.providers.base import MarketData

def match_markets(poly_markets: List[MarketData], kalshi_markets: List[MarketData], threshold: float = 80.0) -> List[Dict[str, Any]]:
    """
    Find matching markets between Polymarket and Kalshi using fuzzy string matching.
    """
    matches = []
    for pm in poly_markets:
        best_match = None
        highest_score = 0
        
        for km in kalshi_markets:
            # Compare titles
            score = fuzz.token_set_ratio(pm.title.lower(), km.title.lower())
            
            if score > threshold and score > highest_score:
                highest_score = score
                best_match = km
        
        if best_match:
            matches.append({
                "poly": pm,
                "kalshi": best_match,
                "score": highest_score
            })
            
    return matches
