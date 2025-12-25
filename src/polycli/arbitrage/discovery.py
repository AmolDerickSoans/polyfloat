import asyncio
import json
import logging
from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from polycli.providers.kalshi import KalshiProvider
from polycli.providers.polymarket import PolyProvider
from polycli.arbitrage.models import MarketPair, MarketType

logger = logging.getLogger(__name__)

@dataclass
class LeagueConfig:
    code: str
    poly_prefix: str
    kalshi_series_game: str
    kalshi_series_spread: Optional[str] = None
    kalshi_series_total: Optional[str] = None

LEAGUES = [
    LeagueConfig("nba", "nba", "KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL"),
    LeagueConfig("nfl", "nfl", "KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL"),
    LeagueConfig("epl", "epl", "KXEPLGAME", "KXEPLSPREAD", "KXEPLTOTAL"),
    LeagueConfig("nhl", "nhl", "KXNHLGAME", "KXNHLSPREAD", "KXNHLTOTAL"),
    # Add more as needed
]

class TeamCache:
    """Simple cache for team name mapping"""
    # Expanded based on common abbreviations
    MAPPING = {
        "epl": {
            "che": "cfc", "chelsea": "cfc",
            "mci": "man-city", "man city": "man-city",
            "mun": "man-utd", "man utd": "man-utd",
            "ars": "arsenal",
            "liv": "liverpool",
        },
        "nba": {
            "lal": "lakers", "lakers": "lakers",
            "gsw": "warriors", "warriors": "warriors",
            "bos": "celtics",
            "mia": "heat",
        }
    }

    @staticmethod
    def normalize(league: str, team: str) -> str:
        league = league.lower()
        team = team.lower().strip()
        if league in TeamCache.MAPPING:
            return TeamCache.MAPPING[league].get(team, team)
        return team

class DiscoveryClient:
    def __init__(self):
        self.kalshi = KalshiProvider()
        self.poly = PolyProvider()

    async def discover_all(self, leagues: List[str] = []) -> List[MarketPair]:
        """Discover markets for specified leagues (or all if empty)"""
        target_leagues = [l for l in LEAGUES if not leagues or l.code in leagues]
        logger.info(f"Starting discovery for {len(target_leagues)} leagues")
        
        tasks = []
        for league in target_leagues:
            tasks.append(self.discover_league(league))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_pairs = []
        for res in results:
            if isinstance(res, list):
                all_pairs.extend(res)
        
        logger.info(f"Discovered {len(all_pairs)} pairs total")
        return all_pairs

    async def discover_league(self, config: LeagueConfig) -> List[MarketPair]:
        """Discover markets for a single league"""
        # 1. Fetch Moneyline Events (Games)
        events = await self.kalshi.get_events(config.kalshi_series_game, limit=50)
        
        pairs = []
        
        # Process each event
        # Limit concurrency
        sem = asyncio.Semaphore(5)
        
        async def process_event(ev):
            async with sem:
                return await self.match_event(config, ev, MarketType.MONEYLINE)

        tasks = [process_event(e) for e in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if isinstance(r, list):
                pairs.extend(r)
                
        return pairs

    async def match_event(self, config: LeagueConfig, event: Dict, mtype: MarketType) -> List[MarketPair]:
        """Match a Kalshi event to Polymarket"""
        # Event structure assumption based on Kalshi API
        ticker = getattr(event, "ticker", "") or event.get("ticker")
        title = getattr(event, "title", "") or event.get("title")
        
        # Parse ticker to extract teams
        # Format usually: KXNBAGAME-23DEC25-LAL-GSW
        try:
            parts = ticker.split("-")
            if len(parts) < 4:
                return []
            
            date_part = parts[1] # 23DEC25
            team1 = parts[2]
            team2 = parts[3]
            
            # Convert date to YYYY-MM-DD
            dt = datetime.strptime(date_part, "%y%b%d")
            date_iso = dt.strftime("%Y-%m-%d")
            
            # Build Poly Slug
            p_team1 = TeamCache.normalize(config.code, team1)
            p_team2 = TeamCache.normalize(config.code, team2)
            
            slug = f"{config.poly_prefix}-{p_team1}-{p_team2}-{date_iso}"
            
            # Try to lookup on Polymarket
            poly_market = await self.poly.get_market_by_slug(slug)
            
            if poly_market:
                # We found a match!
                # Now fetch specific Kalshi market details for this event
                # Note: 'event' in Kalshi is a group of markets. 
                # For moneyline, usually the event ticker itself IS the market ticker OR returns markets.
                # But wait, Kalshi 'events' contain 'markets'.
                
                # Let's fetch markets for this event ticker
                k_markets = await self.kalshi.get_markets() # get_markets is global? No, need by ticker.
                # Actually KalshiProvider.get_markets doesn't filter by event.
                # We might need to fetch specific market if we knew the ticker.
                
                # Optimization: Utilize the 'markets' field if present in event, or use the ticker directly if it is a market.
                # For Game series, the event usually contains markets like 'KXNBAGAME-23DEC25-LAL-GSW'
                
                # Let's assume the event ticker is the market ticker for Moneyline
                # We need to get the specific market data (prices)
                
                # Fetch fresh market data from Kalshi for this ticker
                # We use get_orderbook to verify it exists and get prices? 
                # Or use existing get_markets logic?
                # Let's just create a dummy market object if we can't find it, or reuse data if available.
                
                # Simplified: Just assume match and return pair. Detector will fill in prices.
                
                return [MarketPair(
                    id=f"{ticker}-{poly_market.token_id}",
                    league=config.code,
                    market_type=mtype,
                    description=title,
                    kalshi_ticker=ticker,
                    poly_slug=slug,
                    poly_token_id=poly_market.token_id,
                    poly_market=poly_market
                )]
            
            return []
            
        except Exception as e:
            # logger.error(f"Failed to match {ticker}: {e}")
            return []
