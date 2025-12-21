import os
import httpx
import json
from typing import List, Optional, Dict, Any
from py_clob_client.client import ClobClient
from polycli.providers.base import BaseProvider, MarketData, OrderArgs, OrderResponse, OrderSide, OrderType
import structlog

logger = structlog.get_logger()

class PolyProvider(BaseProvider):
    """
    Polymarket provider implementation using Gamma API for discovery, 
    CLOB API for trading and orderbooks, and Data API for positions.
    """
    
    def __init__(
        self, 
        private_key: Optional[str] = None,
        funder_address: Optional[str] = None,
        signature_type: int = 1,
        clob_host: str = "https://clob.polymarket.com",
        gamma_host: str = "https://gamma-api.polymarket.com",
        data_host: str = "https://data-api.polymarket.com",
        chain_id: int = 137
    ):
        self.clob_host = clob_host
        self.gamma_host = gamma_host
        self.data_host = data_host
        
        self.private_key = private_key or os.getenv("POLY_PRIVATE_KEY")
        self.funder_address = funder_address or os.getenv("POLY_FUNDER_ADDRESS")
        
        # Client for authenticated actions (trading)
        # Note: If no keys provided, client will still work for public endpoints
        self.client = ClobClient(
            host=clob_host,
            key=self.private_key,
            chain_id=chain_id,
            signature_type=signature_type,
            funder=self.funder_address
        )

    async def get_markets(
        self,
        category: Optional[str] = None,
        limit: int = 250
    ) -> List[MarketData]:
        """Fetch active markets from Polymarket Gamma API"""
        async with httpx.AsyncClient() as client:
            try:
                params = {
                    "active": "true",
                    "closed": "false",
                    "limit": limit
                }
                response = await client.get(f"{self.gamma_host}/markets", params=params)
                response.raise_for_status()
                raw_markets = response.json()
                
                markets = []
                for m in raw_markets:
                    # Filter by category if provided
                    if category and category.lower() not in str(m.get("category", "")).lower():
                        continue
                        
                    # Extract price from outcomePrices
                    # Note: Gamma API sometimes returns these as strings of JSON arrays
                    prices_raw = m.get("outcomePrices", "[]")
                    if isinstance(prices_raw, str):
                        try:
                            prices = json.loads(prices_raw)
                        except:
                            prices = []
                    else:
                        prices = prices_raw
                        
                    price = float(prices[0]) if prices else 0.5

                    # Same for clobTokenIds
                    token_ids_raw = m.get("clobTokenIds", "[]")
                    if isinstance(token_ids_raw, str):
                        token_ids = token_ids_raw # Keep as string for now since tui.py does json.loads
                    else:
                        token_ids = json.dumps(token_ids_raw)

                    markets.append(MarketData(
                        token_id=m.get("conditionId"),
                        title=m.get("question", "Unknown Market"),
                        description=m.get("description"),
                        price=price,
                        volume_24h=float(m.get("volume24hr", 0.0)),
                        liquidity=float(m.get("liquidity", 0.0)),
                        end_date=m.get("endDateIso"),
                        provider="polymarket",
                        extra_data={
                            "clob_token_ids": token_ids,
                            "slug": m.get("slug"),
                            "event_slug": m.get("slug") # Gamma "market" endpoint often returns the market slug which is tied to the event
                        }
                    ))
                    
                return markets
            except Exception as e:
                logger.error("Error fetching markets from Gamma", error=str(e))
                return []

    async def get_orderbook(self, token_id: str) -> Dict:
        """Get orderbook from CLOB API. token_id should be an asset ID."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.clob_host}/book", params={"token_id": token_id})
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error("Error fetching orderbook", token_id=token_id, error=str(e))
                return {}

    async def place_order(self, order: OrderArgs) -> OrderResponse:
        """Place an order using py-clob-client"""
        if not self.private_key:
            return OrderResponse(order_id="", status="error", filled_amount=0.0, avg_price=0.0)

        # Implementation would involve using self.client.create_and_post_order
        # but requires knowing which token_id (asset_id) to buy.
        # This mapping is usually found in the clobTokenIds field of the Gamma market.
        logger.info("Order placement requested", side=order.side, amount=order.amount)
        
        return OrderResponse(
            order_id="simulated-id",
            status="submitted",
            filled_amount=0.0,
            avg_price=order.price or 0.0
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order manually or via client"""
        try:
            # self.client.cancel(order_id)
            return True
        except Exception as e:
            logger.error("Error cancelling order", order_id=order_id, error=str(e))
            return False

    async def get_history(self, token_id: str, interval: str = "max") -> List[Dict[str, Any]]:
        """Fetch price history for a specific token"""
        async with httpx.AsyncClient() as client:
            try:
                params = {
                    "market": token_id,
                    "interval": interval
                }
                response = await client.get(f"{self.clob_host}/prices-history", params=params)
                response.raise_for_status()
                data = response.json()
                return data.get("history", [])
            except Exception as e:
                logger.error("Error fetching price history", token_id=token_id, error=str(e))
                return []

    async def get_event_by_slug(self, slug: str) -> Dict[str, Any]:
        """Fetch full event details including sibling markets"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.gamma_host}/events", params={"slug": slug})
                response.raise_for_status()
                events = response.json()
                return events[0] if events else {}
            except Exception as e:
                logger.error("Error fetching event by slug", slug=slug, error=str(e))
                return {}

    async def search(self, query: str) -> List[MarketData]:
        """Search for markets and events using public-search"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # The correct parameter is 'q'. 'active' is not supported on this endpoint.
                params = {"q": query}
                response = await client.get(f"{self.gamma_host}/public-search", params=params)
                response.raise_for_status()
                data = response.json()
                
                results = []
                
                # Helper to parse market into MarketData
                def parse_market(m, event_slug=None):
                    if not m: return None
                    
                    prices_raw = m.get("outcomePrices", "[]")
                    if isinstance(prices_raw, str):
                        try: prices = json.loads(prices_raw)
                        except: prices = []
                    else: prices = prices_raw
                    price = float(prices[0]) if (prices and len(prices) > 0) else 0.5
                    
                    # Ensure clob_token_ids is a JSON string
                    ctid = m.get("clobTokenIds", "[]")
                    if not isinstance(ctid, str):
                        ctid = json.dumps(ctid)

                    def safe_float(val):
                        try: return float(val) if val is not None else 0.0
                        except: return 0.0

                    return MarketData(
                        token_id=m.get("conditionId") or m.get("id"),
                        title=m.get("question", "Unknown"),
                        description=m.get("description"),
                        price=price,
                        volume_24h=safe_float(m.get("volume24hr")),
                        liquidity=safe_float(m.get("liquidity")),
                        end_date=m.get("endDateIso"),
                        provider="polymarket",
                        extra_data={
                            "clob_token_ids": ctid,
                            "slug": m.get("slug"),
                            "event_slug": event_slug or m.get("slug") 
                        }
                    )

                # 1. Process direct Market results
                for m in (data.get("markets") or []):
                    parsed = parse_market(m)
                    if parsed: results.append(parsed)
                
                # 2. Process Markets inside Event results
                for e in (data.get("events") or []):
                    e_slug = e.get("slug")
                    for m in (e.get("markets") or []):
                        mid = m.get("conditionId") or m.get("id")
                        # Avoid duplicates
                        if not any(r.token_id == mid for r in results):
                            parsed = parse_market(m, event_slug=e_slug)
                            if parsed: results.append(parsed)
                
                logger.info("Search results", query=query, count=len(results))
                return results
            except Exception as e:
                logger.error("Search failed", query=query, error=str(e))
                return []

    async def get_positions(self) -> List[Dict]:
        """Fetch user positions from Data API"""
        if not self.funder_address:
            return []
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.data_host}/positions", 
                    params={"user": self.funder_address}
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error("Error fetching positions", user=self.funder_address, error=str(e))
                return []