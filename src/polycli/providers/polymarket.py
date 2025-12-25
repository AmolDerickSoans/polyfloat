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
        chain_id: int = 137
    ):
        self.clob_host = clob_host
        self.gamma_host = gamma_host
        self.data_host = data_host
        
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
                        outcomes=m.get("outcomes", []),
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
        """Fetch trade history from CLOB API"""
        async with httpx.AsyncClient() as client:
            try:
                # This endpoint might vary depending on CLOB version
                params = {}
                if market_id:
                    params["token_id"] = market_id
                response = await client.get(f"{self.clob_host}/trades", params=params)
                response.raise_for_status()
                data = response.json()
                
                trades = []
                for t in data:
                    trades.append(Trade(
                        id=t.get("id", "unknown"),
                        market_id=t.get("asset_id") or market_id,
                        price=float(t.get("price")),
                        size=float(t.get("size")),
                        side=Side.BUY if t.get("side") == "buy" else Side.SELL,
                        timestamp=float(t.get("timestamp", 0))
                    ))
                return trades
            except Exception as e:
                logger.error("Error fetching trade history", market_id=market_id, error=str(e))
                return []
