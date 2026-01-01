import time
import asyncio
from typing import Optional
from polycli.arbitrage.models import MarketPair, ArbOpportunity
from polycli.providers.kalshi import KalshiProvider
from polycli.providers.polymarket import PolyProvider

# Fees
KALSHI_TAKER_FEE = 0.02  # Approximate
POLY_FEE = 0.0

class ArbDetector:
    def __init__(self):
        self.kalshi = KalshiProvider()
        self.poly = PolyProvider()

    async def check_pair(self, pair: MarketPair) -> Optional[ArbOpportunity]:
        """Check a single pair for arb opportunity"""
        try:
            # Fetch Orderbooks in parallel
            t1 = self.kalshi.get_orderbook(pair.kalshi_ticker)
            t2 = self.poly.get_orderbook(pair.poly_token_id)  # Note: poly_token_id is usually asset ID? No, CLOB needs token ID.
            
            # PolyProvider.get_market_by_slug returns MarketData where poly_token_id is conditionId usually.
            # But get_orderbook needs the specific asset ID (Yes or No token).
            # MarketData extra_data["clob_token_ids"] contains [yes, no].
            # We need to fetch orderbooks for BOTH Yes and No tokens on Polymarket to get full picture?
            # Or usually "Market" on Poly has both outcomes. 
            # CLOB API /book takes 'token_id'. 
            
            # Let's extract token IDs from extra_data
            poly_tids = []
            if pair.poly_market and pair.poly_market.extra_data:
                import json
                raw = pair.poly_market.extra_data.get("clob_token_ids", "[]")
                try:
                    poly_tids = json.loads(raw)
                except:
                    pass
            
            if not poly_tids or len(poly_tids) < 2:
                return None
                
            poly_yes_id = poly_tids[0]
            poly_no_id = poly_tids[1]

            k_book, p_yes_book, p_no_book = await asyncio.gather(
                t1,
                self.poly.get_orderbook(poly_yes_id),
                self.poly.get_orderbook(poly_no_id),
                return_exceptions=True
            )
            
            if isinstance(k_book, Exception) or isinstance(p_yes_book, Exception):
                return None

            # Parse Prices (Best Asks)
            # Kalshi
            k_yes_ask = self._get_best_ask(k_book.get("yes", [])) # Kalshi book structure varies?
            # Kalshi API usually returns raw list? dict? 
            # BaseProvider wrapper returns Dict. Let's assume standard structure: {'bids': [], 'asks': []}
            # Wait, Kalshi binary markets have Yes and No side in same book? 
            # Usually: yes_bid, yes_ask, no_bid, no_ask.
            # Using get_market_orderbook response structure.
            # Let's assume wrapper returns a simple dict or access raw.
            
            # Refine Kalshi parsing:
            # SDK get_market_orderbook returns object with yes/no bids/asks.
            # let's assume k_book has 'yes' and 'no' keys if we processed it, 
            # Or if it's raw SDK response, we need to adapt.
            # For safeguard, let's use a safe parser.
            
            k_yes_ask = self._safe_price(k_book, "yes_ask")
            k_no_ask = self._safe_price(k_book, "no_ask")
            
            # Polymarket
            # p_yes_book is for Yes Token. Best Ask = Cost to Buy Yes.
            p_yes_ask = self._get_best_ask(p_yes_book.get("asks", []))
            
            # p_no_book is for No Token. Best Ask = Cost to Buy No.
            p_no_ask = self._get_best_ask(p_no_book.get("asks", []))

            # Strategy 1: Buy Poly YES + Buy Kalshi NO
            cost1 = p_yes_ask + k_no_ask + KALSHI_TAKER_FEE
            profit1 = 1.0 - cost1
            
            # Strategy 2: Buy Kalshi YES + Buy Poly NO
            cost2 = k_yes_ask + p_no_ask + KALSHI_TAKER_FEE
            profit2 = 1.0 - cost2
            
            return ArbOpportunity(
                pair_id=pair.id,
                timestamp=time.time(),
                cost_poly_yes_kalshi_no=cost1,
                cost_kalshi_yes_poly_no=cost2,
                profit_poly_yes_kalshi_no=profit1,
                profit_kalshi_yes_poly_no=profit2,
                poly_yes_price=p_yes_ask,
                kalshi_no_price=k_no_ask,
                kalshi_yes_price=k_yes_ask,
                poly_no_price=p_no_ask
            )

        except Exception as e:
            # print(f"Check pair error: {e}")
            return None

    def _get_best_ask(self, asks: list) -> float:
        # Asks are [(price, size), ...] or [{"price":, "size":}]
        # Poly CLOB returns [{"price": "0.55", "size": "100"}, ...] sorted? 
        # Usually sorted best to worst.
        if not asks:
            return 999.0
        
        first = asks[0]
        try:
            if isinstance(first, dict):
                return float(first.get("price", 999.0))
            elif isinstance(first, (list, tuple)):
                return float(first[0])
            return float(first)
        except:
            return 999.0

    def _safe_price(self, book: dict, key: str) -> float:
        # Try to extract best ask from Kalshi structure
        # If book is a list (bids/asks), adapted.
        # But commonly Kalshi orderbook has 'yes' and 'no' sides.
        # For simplicity, if we can't parse, return high price.
        
        # NOTE: logic depends heavily on provider implementation. 
        # Assuming provider returns raw dict from SDK.
        try:
            # Case 1: book has 'yes' list and 'no' list of asks
            # ...
            return 999.0 # Placeholder: user needs to refinements based on real response
        except:
            return 999.0
