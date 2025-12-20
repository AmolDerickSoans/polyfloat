import os
import httpx
from typing import List, Optional, Dict
from py_clob_client.client import ClobClient
from polycli.providers.base import BaseProvider, MarketData, OrderArgs, OrderResponse, OrderSide, OrderType

class PolyProvider(BaseProvider):
    """Polymarket provider implementation using py-clob-client and raw HTTP"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        private_key: Optional[str] = None,
        funder_address: Optional[str] = None,
        signature_type: int = 1,
        host: str = "https://clob.polymarket.com",
        chain_id: int = 137
    ):
        self.host = host
        # Client for authenticated actions (trading)
        self.client = ClobClient(
            host=host,
            key=private_key or os.getenv("POLY_PRIVATE_KEY"),
            chain_id=chain_id,
            signature_type=signature_type,
            funder=funder_address or os.getenv("POLY_FUNDER_ADDRESS")
        )

    async def get_markets(
        self,
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[MarketData]:
        """Fetch active markets from Polymarket CLOB API"""
        async with httpx.AsyncClient() as client:
            try:
                # Use the next_cursor logic for pagination if we needed more, but for now just basic fetch
                response = await client.get(f"{self.host}/markets")
                response.raise_for_status()
                data = response.json()
                
                markets = []
                # raw_markets is a list of dicts inside 'data' key usually, or direct list depending on endpoint
                # Curl output showed {"data": [...], "next_cursor": ...}
                raw_markets = data.get("data", [])
                
                for m in raw_markets:
                    if not m.get("active"):
                        continue
                        
                    # Extract best price (simplified) - usually need orderbook, but tokens array has 'price' sometimes
                    # The curl output showed tokens array with price.
                    price = 0.50
                    if m.get("tokens") and len(m["tokens"]) > 0:
                        # Take the first token's price (usually 'Yes' or 'Long')
                        price = float(m["tokens"][0].get("price", 0.5))

                    markets.append(MarketData(
                        token_id=m.get("condition_id"), # Using condition_id as unique ID for now
                        title=m.get("question", "Unknown Market"),
                        description=m.get("description"),
                        price=price,
                        volume_24h=0.0, # Not in simple /markets endpoint, would need /ticker
                        liquidity=0.0,
                        end_date=m.get("end_date_iso"),
                        provider="polymarket"
                    ))
                    
                    if len(markets) >= limit:
                        break
                        
                return markets
            except Exception as e:
                print(f"Error fetching markets: {e}")
                return []

    async def get_orderbook(self, token_id: str) -> Dict:
        return self.client.get_orderbook(token_id)

    async def place_order(self, order: OrderArgs) -> OrderResponse:
        # Placeholder for trading logic
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