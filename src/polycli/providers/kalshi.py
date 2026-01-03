import os
import asyncio
import kalshi_python
import json
from typing import List, Optional, Dict, Any
from polycli.providers.base import BaseProvider
from polycli.providers.kalshi_auth import KalshiAuth
from polycli.models import (
    Event,
    Market,
    OrderBook,
    Trade,
    Position,
    Order,
    Side,
    OrderType,
    MarketStatus,
    OrderStatus,
    PriceLevel,
    PricePoint,
)
import structlog
import time

logger = structlog.get_logger()


class KalshiProvider(BaseProvider):
    """Kalshi provider implementation using official SDK"""

    def __init__(self, host: Optional[str] = None):
        self.host = (
            host
            or os.getenv("KALSHI_API_HOST")
            or "https://api.kalshi.com/trade-api/v2"
        )
        self.config = kalshi_python.Configuration()
        self.config.host = self.host
        self.api_instance = None
        self._authenticate()

    def close(self):
        """Cleanup resources"""
        if self.api_instance and hasattr(self.api_instance, "api_client"):
            try:
                if hasattr(self.api_instance.api_client, "pool"):
                    self.api_instance.api_client.pool.close()
                    self.api_instance.api_client.pool.join()
            except Exception as e:
                logger.error("Error closing Kalshi pool", error=str(e))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _authenticate(self):
        """RSA Authentication logic"""
        import sys

        sys.stderr.write(
            f"[KALSHI AUTH] key_id={os.getenv('KALSHI_KEY_ID')}, path={os.getenv('KALSHI_PRIVATE_KEY_PATH')}\n"
        )
        sys.stderr.flush()

        key_id = os.getenv("KALSHI_KEY_ID")
        key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")

        if key_id and key_path:
            try:
                self.api_instance = kalshi_python.ApiInstance(configuration=self.config)
                signer = KalshiAuth(key_id=key_id, private_key_path=key_path)

                # Apply the signing patch to api_client.call_api (keeping previous robust implementation)
                internal_client = self.api_instance.api_client
                original_call_api = internal_client.call_api

                def signed_call_api(*args, **kwargs):
                    try:
                        # Extract params based on standard swagger-codegen signature:
                        # (resource_path, method, path_params, query_params, header_params, body, ...)
                        path = args[0] if len(args) > 0 else kwargs.get("resource_path")
                        method = args[1] if len(args) > 1 else kwargs.get("method")

                        body = None
                        if len(args) > 5:
                            body = args[5]
                        elif "body" in kwargs:
                            body = kwargs["body"]

                        # Generate headers
                        if path and method:
                            auth_headers = signer.get_headers(method, path, body)

                            # Merge into header_params
                            # Check args index 4
                            if len(args) > 4:
                                args_list = list(args)
                                existing = args_list[4] or {}
                                args_list[4] = {**existing, **auth_headers}
                                args = tuple(args_list)
                            else:
                                existing = kwargs.get("header_params") or {}
                                kwargs["header_params"] = {**existing, **auth_headers}
                    except Exception as e:
                        logger.error("Signing Error", error=str(e))
                        # Proceed without signing if error (likely to fail but better than crash)

                    return original_call_api(*args, **kwargs)

                internal_client.call_api = signed_call_api
                logger.info("Authenticated via RSA Key")
            except Exception as e:
                logger.error("Kalshi RSA Auth Failed", error=str(e))
                self.api_instance = None
        else:
            self.api_instance = None

    async def check_connection(self) -> bool:
        """Verify authentication status by fetching a small amount of public data"""
        if not self.api_instance:
            return False
        try:
            # use get_public_events manual call which is proven robust.
            # Add timeout to prevent hangs
            events = await asyncio.wait_for(
                self.get_public_events(limit=1), timeout=10.0
            )
            return len(events) > 0
        except asyncio.TimeoutError:
            logger.error("Connection Check Timeout")
            return False
        except Exception as e:
            logger.error("Connection Check Error", error=str(e))
            return False

    async def get_balance(self) -> Dict[str, Any]:
        """Fetch account balance from Kalshi"""
        if not self.api_instance:
            return {"balance": 0.0, "allowance": 0.0, "error": "Not authenticated"}

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self.api_instance.get_balance()
            )
            # Kalshi balance is in cents
            balance_cents = getattr(response, "balance", 0)
            balance_usd = float(balance_cents) / 100.0

            return {
                "balance": balance_usd,
                "allowance": 1000000.0,  # Arbitrary high allowance for Kalshi
                "error": None,
            }
        except Exception as e:
            logger.error("Error fetching Kalshi balance", error=str(e))
            return {"balance": 0.0, "allowance": 0.0, "error": str(e)}

    async def get_events(
        self, category: Optional[str] = None, limit: int = 100
    ) -> List[Event]:
        """Fetch available events from Kalshi API"""
        if not self.api_instance:
            return []
        try:
            raw_events = await self.get_public_events(limit=limit)
            events = []
            for e in raw_events:
                events.append(
                    Event(
                        id=e.get("event_ticker") or e.get("ticker"),
                        provider="kalshi",
                        title=e.get("title", "Unknown Event"),
                        description=e.get("subtitle", ""),
                        status=MarketStatus.ACTIVE
                        if e.get("status") == "open"
                        else MarketStatus.CLOSED,
                        markets=[],  # populated via get_markets
                        metadata=e,
                    )
                )
            return events
        except Exception as e:
            logger.error("Error fetching Kalshi events", error=str(e))
            return []

    async def search(self, query: str) -> List[Market]:
        """Search for markets by query (Local filter of active markets)"""
        try:
            # Fetch a broad set of active markets to filter locally
            # Real implementation would use a search endpoint if available
            all_markets = await self.get_markets(limit=200)
            q = query.lower()

            matches = []
            for m in all_markets:
                if q in m.question.lower() or q in m.id.lower():
                    matches.append(m)
            return matches[:20]
        except Exception as e:
            logger.error("Error searching Kalshi", query=query, error=str(e))
            return []

    async def get_markets(
        self,
        event_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> List[Market]:
        """Fetch active markets from Kalshi API"""
        if not self.api_instance:
            return []

        try:
            loop = asyncio.get_event_loop()
            kwargs = {"status": "open", "limit": limit, "_request_timeout": 10}
            if event_id:
                kwargs["event_ticker"] = event_id

            response = await loop.run_in_executor(
                None, lambda: self.api_instance.get_markets(**kwargs)
            )

            raw_markets = getattr(response, "markets", [])
            markets = []
            for m in raw_markets:
                markets.append(
                    Market(
                        id=m.ticker,
                        event_id=getattr(m, "event_ticker", ""),
                        provider="kalshi",
                        question=getattr(m, "title", m.ticker),
                        status=MarketStatus.ACTIVE
                        if getattr(m, "status") == "open"
                        else MarketStatus.CLOSED,
                        outcomes=["Yes", "No"],
                        metadata=m.__dict__ if hasattr(m, "__dict__") else {},
                    )
                )
            return markets
        except Exception as e:
            logger.error("Error fetching Kalshi markets", error=str(e))
            return []

    async def get_orderbook(self, market_id: str) -> OrderBook:
        """Get orderbook for specific ticker"""
        if not self.api_instance:
            return OrderBook(market_id=market_id, bids=[], asks=[], timestamp=0)
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.get_market_orderbook(
                    market_id, _request_timeout=10
                ),
            )

            obs = getattr(resp, "order_book", None) or resp
            yes_bids = getattr(obs, "yes", []) or []
            no_bids = getattr(obs, "no", []) or []

            bids = []
            for level in yes_bids:
                if isinstance(level, list):
                    p, s = level[0], level[1]
                else:
                    p, s = getattr(level, "price", 0), getattr(level, "count", 0)
                bids.append(PriceLevel(price=float(p) / 100.0, size=float(s)))

            asks = []
            for level in no_bids:
                if isinstance(level, list):
                    p, s = level[0], level[1]
                else:
                    p, s = getattr(level, "price", 0), getattr(level, "count", 0)
                asks.append(PriceLevel(price=float(100 - p) / 100.0, size=float(s)))

            bids.sort(key=lambda x: x.price, reverse=True)
            asks.sort(key=lambda x: x.price)

            return OrderBook(market_id=market_id, bids=bids, asks=asks, timestamp=0.0)
        except Exception as e:
            logger.error(
                "Error fetching Kalshi orderbook", market_id=market_id, error=str(e)
            )
            return OrderBook(market_id=market_id, bids=[], asks=[], timestamp=0)

    async def place_order(
        self,
        market_id: str,
        side: Side,
        size: float,
        price: float,
        order_type: OrderType = OrderType.LIMIT,
    ) -> Order:
        """Place an order on Kalshi"""
        if not self.api_instance:
            raise ValueError("Kalshi API not initialized")

        try:
            import uuid

            # Simplified: always trade 'yes' side, action Buy=Long, Sell=Short
            req = kalshi_python.CreateOrderRequest(
                ticker=market_id,
                action="buy" if side == Side.BUY else "sell",
                side="yes",
                count=int(size),
                type="limit",
                yes_price=int(price * 100),
                client_order_id=str(uuid.uuid4()),
            )

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, lambda: self.api_instance.create_order(req, _request_timeout=10)
            )

            return Order(
                id=getattr(resp, "order_id", "unknown"),
                market_id=market_id,
                price=price,
                size=size,
                side=side,
                type=order_type,
                status=OrderStatus.OPEN
                if getattr(resp, "status") in ["placed", "submitted"]
                else OrderStatus.FILLED,
                timestamp=0.0,
            )
        except Exception as e:
            logger.error(
                "Kalshi order placement failed", market_id=market_id, error=str(e)
            )
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order on Kalshi"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.api_instance.cancel_order(order_id, _request_timeout=10),
            )
            return True
        except Exception as e:
            logger.error(
                "Error cancelling Kalshi order", order_id=order_id, error=str(e)
            )
            return False

    async def get_positions(self) -> List[Position]:
        """Fetch user positions"""
        if not self.api_instance:
            return []
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.get_portfolio_positions(_request_timeout=10),
            )

            raw_pos = getattr(resp, "market_positions", [])
            positions = []
            for p in raw_pos:
                count = getattr(p, "position", 0)
                if count == 0:
                    continue

                positions.append(
                    Position(
                        market_id=getattr(p, "ticker", ""),
                        outcome="Yes",  # Default assumption
                        size=float(count),
                        avg_price=float(getattr(p, "cost_basis", 0)) / (count * 100.0)
                        if count
                        else 0,
                        realized_pnl=float(getattr(p, "realized_pnl", 0)) / 10000.0,
                        unrealized_pnl=0.0,  # Calculate if needed
                    )
                )
            return positions
        except Exception as e:
            logger.error("Error fetching Kalshi positions", error=str(e))
            return []

    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """Fetch open orders from Kalshi"""
        if not self.api_instance:
            return []
        try:
            loop = asyncio.get_event_loop()
            # Note: SDK endpoint might vary, using get_orders with status=open
            response = await loop.run_in_executor(
                None,
                lambda: self.api_instance.get_orders(
                    status="open", ticker=market_id, _request_timeout=10
                ),
            )
            raw_orders = getattr(response, "orders", [])
            orders = []
            for o in raw_orders:
                orders.append(
                    Order(
                        id=o.order_id,
                        market_id=o.ticker,
                        price=float(o.yes_price) / 100.0,
                        size=float(o.count),
                        side=Side.BUY if o.action == "buy" else Side.SELL,
                        type=OrderType.LIMIT,
                        status=OrderStatus.OPEN,
                        timestamp=0.0,
                    )
                )
            return orders
        except Exception as e:
            logger.error("Error fetching Kalshi open orders", error=str(e))
            return []

    async def get_history(self, market_id: Optional[str] = None) -> List[Trade]:
        """Fetch trade history from Kalshi"""
        if not self.api_instance or not market_id:
            return []
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.api_instance.get_trades(
                    ticker=market_id, limit=100, _request_timeout=10
                ),
            )
            raw_trades = getattr(response, "trades", [])
            trades = []
            for t in raw_trades:
                trades.append(
                    Trade(
                        id=str(t.trade_id),
                        market_id=market_id,
                        price=float(t.yes_price) / 100.0,
                        size=float(t.count),
                        side=Side.BUY if t.taker_side == "yes" else Side.SELL,
                        timestamp=0.0,  # Map from created_time
                    )
                )
            return trades
        except Exception as e:
            logger.error("Error fetching Kalshi history", error=str(e))
            return []

    async def get_public_events(self, limit: int = 100) -> List[Dict]:
        """Helper for raw events retrieval"""
        if not self.api_instance:
            return []
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.api_client.call_api(
                    "/events",
                    "GET",
                    query_params=[("status", "open"), ("limit", limit)],
                    auth_settings=["bearerAuth"],
                    _return_http_data_only=False,
                    _preload_content=False,
                    _request_timeout=10,
                ),
            )
            http_resp = resp[0]
            if http_resp.status != 200:
                return []
            data = json.loads(http_resp.data.decode("utf-8"))
            return data.get("events", [])
        except Exception as e:
            logger.error("Error in get_public_events", error=str(e))
            return []

    async def get_candlesticks(
        self, market_id: str, period: str = "hour", limit: int = 100
    ) -> List[PricePoint]:
        """
        Fetch candlestick data from Kalshi API

        Args:
            market_id: Kalshi market ticker (e.g., KXNEWPOPE-70-PPIZ)
            period: "minute", "hour", or "day"
            limit: Number of candlesticks to fetch

        Returns:
            List of PricePoint objects with timestamp (t) and price (p)
        """
        if not self.api_instance:
            return []

        try:
            period_map = {"minute": 1, "hour": 60, "day": 1440}
            if period not in period_map:
                logger.error("Invalid period", period=period)
                return []

            interval = period_map[period]

            end_ts = int(time.time())
            start_ts = end_ts - (interval * limit * 60)

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.api_client.call_api(
                    f"/series/{market_id}/markets/{market_id}/candlesticks",
                    "GET",
                    query_params=[
                        ("start_ts", start_ts),
                        ("end_ts", end_ts),
                        ("period_interval", interval),
                    ],
                    auth_settings=["bearerAuth"],
                    _return_http_data_only=False,
                    _preload_content=False,
                    _request_timeout=10,
                ),
            )

            http_resp = resp[0]
            if http_resp.status != 200:
                return []
            data = json.loads(http_resp.data.decode("utf-8"))
            candlesticks = data.get("candlesticks", [])

            if not candlesticks:
                logger.info("No candlesticks returned", market_id=market_id)
                return []

            price_points = []
            for candle in candlesticks:
                yes_ask = candle.get("yes_ask", {})
                yes_bid = candle.get("yes_bid", {})

                if not yes_ask or not yes_bid:
                    continue

                ask_close = yes_ask.get("close")
                if ask_close is None:
                    continue

                end_ts = candle.get("end_period_ts", 0)

                price_points.append(
                    PricePoint(t=float(end_ts), p=float(ask_close) / 100.0)
                )

            logger.info(
                "Candlesticks fetched",
                market_id=market_id,
                count=len(price_points),
                period=period,
            )

            return price_points

        except Exception as e:
            logger.error(
                "Error fetching candlesticks", market_id=market_id, error=str(e)
            )
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
