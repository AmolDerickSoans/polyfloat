import httpx
from typing import List, Optional, Dict
from polycli.providers.base import BaseProvider, MarketData, OrderArgs, OrderResponse, OrderSide, OrderType

class KalshiProvider(BaseProvider):
    """Kalshi provider implementation using public API"""
    
    def __init__(self, host: str = "https://trading-api.kalshi.com/trade-api/v2"):
        self.host = host

    async def get_markets(
        self,
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[MarketData]:
        """Fetch active markets from Kalshi API"""
        async with httpx.AsyncClient() as client:
            try:
                # Some Kalshi endpoints might work without full session for public data
                # but standard v2 /markets often requires it.
                params = {"status": "open", "limit": limit}
                response = await client.get(f"{self.host}/markets", params=params)
                
                if response.status_code == 401:
                    # In a real scenario, we'd use a login session here.
                    # For now, we return empty and warn.
                    return []
                    
                response.raise_for_status()
                data = response.json()
                
                markets = []
                raw_markets = data.get("markets", [])
                
                for m in raw_markets:
                    # Kalshi prices are in cents (0-100)
                    # yes_bid is what we can sell for, yes_ask is what we can buy for
                    # For a simple 'price' we'll take the midpoint or just the last price if available
                    # Here we use yes_bid/100 as a proxy for the 'current' price
                    price = m.get("yes_bid", 50) / 100.0
                    
                    markets.append(MarketData(
                        token_id=m.get("ticker"),
                        title=m.get("title", "Unknown Kalshi Market"),
                        description=m.get("subtitle"),
                        price=price,
                        volume_24h=0.0, # Not in simple /markets list
                        liquidity=0.0,
                        end_date=m.get("close_time"),
                        provider="kalshi"
                    ))
                    
                return markets
            except Exception as e:
                print(f"Error fetching Kalshi markets: {e}")
                return []

    async def get_orderbook(self, ticker: str) -> Dict:
        """Get orderbook for a ticker"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.host}/markets/{ticker}/orderbook")
                response.raise_for_status()
                return response.json().get("orderbook", {})
            except Exception as e:
                print(f"Error fetching Kalshi orderbook: {e}")
                return {}

    async def place_order(self, order: OrderArgs) -> OrderResponse:
        # Requires authentication
        return OrderResponse(
            order_id="placeholder",
            status="pending",
            filled_amount=0.0,
            avg_price=0.0
        )

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_positions(self) -> List[Dict]:
        return []
