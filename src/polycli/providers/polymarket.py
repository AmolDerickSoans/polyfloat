import os
import httpx
import json
from typing import List, Optional, Dict, Any
from py_clob_client.client import ClobClient
from polycli.providers.base import BaseProvider
from polycli.models import Event, Market, OrderBook, Trade, Position, Order, Side, OrderType, MarketStatus, OrderStatus, PriceLevel
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
        chain_id: int = 137,
        timeout: float = 15.0  # Add configurable timeout
    ):
        self.clob_host = clob_host
        self.gamma_host = gamma_host
        self.data_host = data_host
        self.timeout = timeout  # Store for reuse
        
        self.private_key = private_key or os.getenv("POLY_PRIVATE_KEY")
        self.funder_address = funder_address or os.getenv("POLY_FUNDER_ADDRESS")
        
        # Client for authenticated actions (trading)
        self.client = ClobClient(
            host=clob_host,
            key=self.private_key,
            chain_id=chain_id,
            signature_type=signature_type,
            funder=self.funder_address
        )

    async def get_events(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """Fetch available events from Polymarket Gamma API"""
        async with httpx.AsyncClient() as client:
            try:
                params = {"limit": limit}
                response = await client.get(f"{self.gamma_host}/events", params=params)
                response.raise_for_status()
                raw_events = response.json()
                
                events = []
                for e in raw_events:
                    events.append(Event(
                        id=e.get("id"),
                        provider="polymarket",
                        title=e.get("title", "Unknown Event"),
                        description=e.get("description", ""),
                        status=MarketStatus.ACTIVE if e.get("active") else MarketStatus.CLOSED,
                        markets=[m.get("id") for m in e.get("markets", [])],
                        metadata=e
                    ))
                return events
            except Exception as e:
                logger.error("Error fetching events from Gamma", error=str(e))
                return []

    async def search(
        self, 
        query: str, 
        max_results: int = 20,
        include_closed: bool = False,
        debug: bool = False
    ) -> List[Market]:
        """
        Search for markets via Gamma API with pagination support
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            include_closed: Whether to include closed markets
            debug: Whether to print debug information
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                markets = []
                page = 1
                
                while len(markets) < max_results:
                    params = {
                        "q": query,
                        "limit_per_type": min(50, max_results - len(markets)),
                        "page": page,
                        "search_tags": False,
                        "search_profiles": False,
                        "events_status": "active" if not include_closed else None
                    }
                    
                    # Remove None values
                    params = {k: v for k, v in params.items() if v is not None}
                    
                    if debug:
                        print(f"[DEBUG] Request URL: {self.gamma_host}/public-search")
                        print(f"[DEBUG] Params: {params}")
                    
                    response = await client.get(
                        f"{self.gamma_host}/public-search",
                        params=params
                    )
                    
                    if debug:
                        print(f"[DEBUG] Response status: {response.status_code}")
                        print(f"[DEBUG] Response headers: {dict(response.headers)}")
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    if debug:
                        print(f"[DEBUG] Events in response: {len(data.get('events', []))}")
                    
                    # Extract markets from events
                    batch = []
                    for event in data.get("events", []):
                        event_markets = event.get("markets", [])
                        if debug:
                            print(f"[DEBUG] Event '{event.get('title', 'N/A')[:40]}' has {len(event_markets)} markets")
                        
                        for market_data in event_markets:
                            batch.append(Market(
                                id=market_data.get("conditionId") or market_data.get("id"),
                                event_id=str(event.get("id", "")),
                                provider="polymarket",
                                question=market_data.get("question") or event.get("title", "Unknown"),
                                status=MarketStatus.ACTIVE if market_data.get("active") else MarketStatus.CLOSED,
                                outcomes=self._parse_outcomes(market_data.get("outcomes")),
                                metadata=market_data
                            ))
                    
                    markets.extend(batch)
                    
                    if debug:
                        print(f"[DEBUG] Page {page}: Added {len(batch)} markets (total: {len(markets)})")
                    
                    # Check if there are more results
                    pagination = data.get("pagination", {})
                    if not pagination.get("hasMore", False) or not batch:
                        if debug:
                            print(f"[DEBUG] Stopping pagination: hasMore={pagination.get('hasMore')}, batch_empty={not batch}")
                        break
                    
                    page += 1
                
                return markets[:max_results]
                
            except httpx.TimeoutException:
                logger.error("Polymarket search timeout", query=query, timeout=self.timeout)
                if debug:
                    print(f"[DEBUG] Timeout after {self.timeout}s")
                return []
            except httpx.HTTPStatusError as e:
                logger.error("Polymarket HTTP error", query=query, status=e.response.status_code, detail=e.response.text)
                if debug:
                    print(f"[DEBUG] HTTP Error {e.response.status_code}: {e.response.text}")
                return []
            except Exception as e:
                logger.error("Error searching Polymarket", query=query, error=repr(e))
                if debug:
                    import traceback
                    print(f"[DEBUG] Exception: {traceback.format_exc()}")
                return []

    def _parse_outcomes(self, outcomes_data) -> List[str]:
        """Parse outcomes from various formats in Gamma API response"""
        if not outcomes_data:
            return ["Yes", "No"]  # Default binary outcomes
        
        # Handle string format (JSON string)
        if isinstance(outcomes_data, str):
            try:
                import json
                parsed = json.loads(outcomes_data)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                # If it's a simple comma-separated string
                return [o.strip() for o in outcomes_data.split(",")]
        
        # Handle list format
        if isinstance(outcomes_data, list):
            return outcomes_data
        
        return ["Yes", "No"]  # Fallback

    async def get_markets(
        self,
        event_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Market]:
        """Fetch active markets from Polymarket Gamma API"""
        async with httpx.AsyncClient() as client:
            try:
                params = {
                    "active": "true",
                    "closed": "false",
                    "limit": limit
                }
                if event_id:
                    # In Gamma, markets are often fetched via the events endpoint
                    response = await client.get(f"{self.gamma_host}/events/{event_id}")
                    raw_markets = response.json().get("markets", [])
                else:
                    response = await client.get(f"{self.gamma_host}/markets", params=params)
                    raw_markets = response.json()
                
                markets = []
                for m in raw_markets:
                    markets.append(Market(
                        id=m.get("conditionId") or m.get("id"),
                        event_id=str(m.get("eventId", "")),
                        provider="polymarket",
                        question=m.get("question", "Unknown Market"),
                        status=MarketStatus.ACTIVE if m.get("active") else MarketStatus.CLOSED,
                        outcomes=self._parse_outcomes(m.get("outcomes")),
                        metadata=m
                    ))
                return markets
            except Exception as e:
                logger.error("Error fetching markets from Gamma", error=str(e))
                return []

    async def get_orderbook(self, market_id: str) -> OrderBook:
        """Get orderbook from CLOB API. market_id should be a token ID for CLOB."""
        async with httpx.AsyncClient() as client:
            try:
                # Polymarket CLOB uses token_id in the book endpoint
                response = await client.get(f"{self.clob_host}/book", params={"token_id": market_id})
                response.raise_for_status()
                data = response.json()
                
                return OrderBook(
                    market_id=market_id,
                    bids=[PriceLevel(price=float(l["price"]), size=float(l["size"])) for l in data.get("bids", [])],
                    asks=[PriceLevel(price=float(l["price"]), size=float(l["size"])) for l in data.get("asks", [])],
                    timestamp=float(data.get("timestamp", 0))
                )
            except Exception as e:
                logger.error("Error fetching orderbook", market_id=market_id, error=str(e))
                return OrderBook(market_id=market_id, bids=[], asks=[], timestamp=0)

    async def place_order(
        self, 
        market_id: str,
        side: Side,
        size: float,
        price: float,
        order_type: OrderType = OrderType.LIMIT
    ) -> Order:
        """Place an order using py-clob-client"""
        if not self.private_key:
            raise ValueError("Private key required for trading")

        try:
            # Polymarket CLOB requires a token_id. market_id here is assumed to be the token_id.
            # Real implementation would use self.client.create_and_post_order
            # For now, we mock the call logic as per typical ClobClient usage
            resp = self.client.create_and_post_order({
                "price": price,
                "size": size,
                "side": "BUY" if side == Side.BUY else "SELL",
                "token_id": market_id
            })
            
            return Order(
                id=resp.get("orderID", "unknown"),
                market_id=market_id,
                price=price,
                size=size,
                side=side,
                type=order_type,
                status=OrderStatus.OPEN if resp.get("status") == "LIVE" else OrderStatus.FILLED,
                timestamp=0.0 # Should get from response if available
            )
        except Exception as e:
            logger.error("Order placement failed", market_id=market_id, error=str(e))
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via CLOB API"""
        try:
            self.client.cancel(order_id)
            return True
        except Exception as e:
            logger.error("Error cancelling order", order_id=order_id, error=str(e))
            return False

    async def get_positions(self) -> List[Position]:
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
                data = response.json()
                
                positions = []
                for p in data:
                    positions.append(Position(
                        market_id=p.get("conditionId"),
                        outcome=p.get("outcome"),
                        size=float(p.get("size", 0)),
                        avg_price=float(p.get("avgPrice", 0)),
                        realized_pnl=float(p.get("realizedPnl", 0)),
                        unrealized_pnl=float(p.get("unrealizedPnl", 0))
                    ))
                return positions
            except Exception as e:
                logger.error("Error fetching positions", user=self.funder_address, error=str(e))
                return []

    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """Fetch open orders from CLOB API"""
        try:
            from py_clob_client.clob_types import OpenOrderParams
            params = OpenOrderParams(market=market_id) if market_id else None
            raw_orders = self.client.get_orders(params)
            orders = []
            for o in raw_orders:
                orders.append(Order(
                    id=o.get("orderID"),
                    market_id=o.get("assetID"),
                    price=float(o.get("price")),
                    size=float(o.get("size")),
                    side=Side.BUY if o.get("side") == "BUY" else Side.SELL,
                    type=OrderType.LIMIT,
                    status=OrderStatus.OPEN,
                    timestamp=0.0
                ))
            return orders
        except Exception as e:
            logger.error("Error fetching open orders", error=str(e))
            return []

    async def get_history(self, market_id: Optional[str] = None) -> List[Trade]:
        """
        Fetch price history for charting.
        
        NOTE: Polymarket CLOB API does NOT provide a public endpoint for 
        historical trade data. The /trades endpoint requires authentication
        and only returns user's own trades, not public market history.
        
        This implementation uses the available public endpoints to build
        a price history for charting purposes.
        """
        if not market_id:
            return []
        
        try:
            # Try to get last trade price (public endpoint that works)
            last_trade = self.client.get_last_trade_price(market_id)
            
            if last_trade and 'price' in last_trade:
                price = float(last_trade['price'])
                side = Side.BUY if last_trade.get('side') == 'buy' else Side.SELL
                
                # Create a single trade entry with current timestamp
                import time
                return [Trade(
                    id="last_trade",
                    market_id=market_id,
                    price=price,
                    size=100.0,  # Default size for charting
                    side=side,
                    timestamp=time.time()
                )]
            return []
            
        except Exception as e:
            logger.error("Error fetching last trade price for charting", market_id=market_id, error=str(e))
            return []

    async def get_news(
        self,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[Any]:
        """
        Fetch market-related news.
        Currently a placeholder to satisfy BaseProvider interface.
        Full implementation will be added in Phase 2.
        """
        logger.info("Fetching news (placeholder)", query=query, limit=limit)
        return []
