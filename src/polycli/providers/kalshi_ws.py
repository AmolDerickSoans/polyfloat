import asyncio
import json
import os
import time
import websockets
from typing import Dict, List, Optional, Any, Callable, Set
import structlog
from polycli.providers.kalshi_auth import KalshiAuth

logger = structlog.get_logger()

class KalshiWebSocket:
    """Kalshi WebSocket Client for Real-time Data"""
    
    URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    
    def __init__(self):
        self.ws = None
        self.keep_running = False
        self.callbacks: Dict[str, List[Callable]] = {}
        self.msg_id = 1
        self.subscriptions: Set[str] = set()
        self.orderbooks: Dict[str, Dict] = {} # {ticker: {'bids': {price: size}, 'asks': {price: size}}}
        self._listen_task: Optional[asyncio.Task] = None
        
    def add_callback(self, channel: str, callback: Callable):
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)

    async def connect(self):
        """Connect to Kalshi WebSocket with reconnection logic"""
        self.keep_running = True
        self._listen_task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        reconnect_delay = 1
        while self.keep_running:
            try:
                headers = self._get_auth_headers()
                async with websockets.connect(self.URL, additional_headers=headers) as ws:
                    self.ws = ws
                    reconnect_delay = 1
                    logger.info("Connected to Kalshi WS")
                    
                    # Re-subscribe to existing tickers
                    if self.subscriptions:
                        await self._send_subscription(list(self.subscriptions))
                    
                    async for msg in ws:
                        data = json.loads(msg)
                        await self._dispatch(data)
                        
            except Exception as e:
                logger.error("Kalshi WS loop error", error=str(e))
                if not self.keep_running:
                    break
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def _dispatch(self, data: Dict[str, Any]):
        type_ = data.get("type")
        if type_ == "ticker":
            await self._handle_ticker(data)
        elif type_ in ["orderbook_delta", "orderbook_snapshot"]:
            await self._handle_orderbook(data)
        elif type_ == "trade":
            await self._handle_trade(data)
        elif type_ == "fill":
            await self._handle_fill(data)
        elif type_ == "position":
            await self._handle_position(data)

    async def disconnect(self):
        self.keep_running = False
        if self.ws:
            await self.ws.close()
        if self._listen_task:
            self._listen_task.cancel()

    async def subscribe(self, ticker: str):
        """Subscribe to market updates for a ticker"""
        self.subscriptions.add(ticker)
        if self.ws and self.ws.open:
            await self._send_subscription([ticker])

    async def _send_subscription(self, tickers: List[str]):
        channels = ["ticker", "orderbook_delta", "trade"]
        cmd = {
            "id": self.msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": channels,
                "market_tickers": tickers
            }
        }
        self.msg_id += 1
        await self.ws.send(json.dumps(cmd))

    async def _handle_ticker(self, data):
        ticker = data.get("market_ticker")
        if not ticker: return
        funcs = self.callbacks.get("ticker", [])
        for f in funcs:
            if asyncio.iscoroutinefunction(f): await f(data)
            else: f(data)

    async def _handle_orderbook(self, data):
        ticker = data.get("market_ticker")
        if not ticker: return
        
        if ticker not in self.orderbooks:
            self.orderbooks[ticker] = {"bids": {}, "asks": {}}
            
        ob = self.orderbooks[ticker]
        msg_type = data.get("type")
        
        if msg_type == "orderbook_snapshot":
            ob["bids"] = {}
            ob["asks"] = {}
            
        def apply_update(levels, is_bid=True):
            for level in levels:
                price = level[0]
                size = level[1]
                if is_bid:
                    target_price = price / 100.0
                    if size == 0:
                        if target_price in ob["bids"]: del ob["bids"][target_price]
                    else:
                        ob["bids"][target_price] = size
                else:
                    target_price = (100 - price) / 100.0
                    if size == 0:
                        if target_price in ob["asks"]: del ob["asks"][target_price]
                    else:
                        ob["asks"][target_price] = size

        apply_update(data.get("yes", []), is_bid=True)
        apply_update(data.get("no", []), is_bid=False)
        
        sorted_bids = [{"price": p, "size": s} for p, s in sorted(ob["bids"].items(), key=lambda x: x[0], reverse=True)]
        sorted_asks = [{"price": p, "size": s} for p, s in sorted(ob["asks"].items(), key=lambda x: x[0])]
        
        full_book = {"market_ticker": ticker, "bids": sorted_bids, "asks": sorted_asks}
        
        funcs = self.callbacks.get("orderbook", [])
        for f in funcs:
            if asyncio.iscoroutinefunction(f): await f(full_book)
            else: f(full_book)

    async def _handle_trade(self, data):
        funcs = self.callbacks.get("trade", [])
        for f in funcs:
            t = {
                "market_ticker": data.get("market_ticker"),
                "price": data.get("yes_price", 0)/100.0,
                "size": data.get("count", 0),
                "side": "buy" if data.get("taker_side") == "yes" else "sell",
                "time": str(data.get("ts", time.time()))
            }
            if asyncio.iscoroutinefunction(f): await f(t)
            else: f(t)

    async def _handle_fill(self, data):
        funcs = self.callbacks.get("fill", [])
        for f in funcs:
            if asyncio.iscoroutinefunction(f): await f(data)
            else: f(data)

    async def _handle_position(self, data):
        funcs = self.callbacks.get("position", [])
        for f in funcs:
            if asyncio.iscoroutinefunction(f): await f(data)
            else: f(data)

    def _get_auth_headers(self) -> Dict[str, str]:
        key_id = os.getenv("KALSHI_KEY_ID")
        key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        if not key_id or not key_path: return {}
        try:
            auth = KalshiAuth(key_id, key_path)
            return auth.get_ws_headers("GET", "/trade-api/ws/v2")
        except Exception as e:
            logger.error("WS Auth Error", error=str(e))
            return {}