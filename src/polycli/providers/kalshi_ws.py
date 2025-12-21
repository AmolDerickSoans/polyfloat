import asyncio
import json
import os
import time
import websockets
from typing import Dict, List, Optional, Any, Callable
from textual import log
from polycli.providers.kalshi_auth import KalshiAuth

class KalshiWebSocket:
    """Kalshi WebSocket Client for Real-time Data"""
    
    URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    
    def __init__(self):
        self.ws = None
        self.keep_running = False
        self.callbacks: Dict[str, List[Callable]] = {}
        self.msg_id = 1
        self.subscriptions = set()
        self.orderbooks: Dict[str, Dict] = {} # {ticker: {'bids': {price: size}, 'asks': {price: size}}}
        
    def add_callback(self, channel: str, callback: Callable):
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)

    async def connect(self):
        """Connect to Kalshi WebSocket"""
        headers = self._get_auth_headers()
        try:
            self.ws = await websockets.connect(self.URL, additional_headers=headers)
            self.keep_running = True
            log("Connected to Kalshi WS")
            asyncio.create_task(self._listen())
        except Exception as e:
            log(f"Kalshi WS Connection Failed: {e}")

    async def disconnect(self):
        self.keep_running = False
        if self.ws:
            await self.ws.close()

    async def subscribe(self, ticker: str):
        """Subscribe to market updates"""
        if not self.ws: return
        channels = ["ticker", "orderbook_delta", "trade"]
        cmd = {
            "id": self.msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": channels,
                "market_tickers": [ticker]
            }
        }
        self.msg_id += 1
        await self.ws.send(json.dumps(cmd))

    async def subscribe_user_channels(self):
        """Subscribe to private user channels"""
        if not self.ws: return
        cmd = {
            "id": self.msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["market_positions", "user_fills"]
            }
        }
        self.msg_id += 1
        await self.ws.send(json.dumps(cmd))

    async def _listen(self):
        while self.keep_running and self.ws:
            try:
                msg = await self.ws.recv()
                data = json.loads(msg)
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
            except Exception as e:
                log(f"WS Error: {e}")
                await asyncio.sleep(1)

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
        
        # Initialize state if needed
        if ticker not in self.orderbooks:
            self.orderbooks[ticker] = {"bids": {}, "asks": {}}
            
        ob = self.orderbooks[ticker]
        msg_type = data.get("type")
        
        # In Kalshi, orderbook_delta has 'yes' and 'no' lists
        # Each level is [price, size]
        
        if msg_type == "orderbook_snapshot":
            ob["bids"] = {}
            ob["asks"] = {}
            
        def apply_update(side_key, levels, is_bid=True):
            for level in levels:
                price = level[0]
                size = level[1]
                
                if is_bid:
                    # YES Bids
                    target_price = price / 100.0
                    if size == 0:
                        if target_price in ob["bids"]: del ob["bids"][target_price]
                    else:
                        ob["bids"][target_price] = size
                else:
                    # NO Bids = YES Asks = 100 - NO Price
                    target_price = (100 - price) / 100.0
                    if size == 0:
                        if target_price in ob["asks"]: del ob["asks"][target_price]
                    else:
                        ob["asks"][target_price] = size

        # Apply YES bids
        apply_update("yes", data.get("yes", []), is_bid=True)
        # Apply NO bids as YES asks
        apply_update("no", data.get("no", []), is_bid=False)
        
        # Standardize and Emit
        sorted_bids = [{"price": p, "size": s} for p, s in sorted(ob["bids"].items(), key=lambda x: x[0], reverse=True)]
        sorted_asks = [{"price": p, "size": s} for p, s in sorted(ob["asks"].items(), key=lambda x: x[0])]
        
        full_book = {"bids": sorted_bids, "asks": sorted_asks}
        
        funcs = self.callbacks.get("orderbook", [])
        for f in funcs:
            if asyncio.iscoroutinefunction(f): await f(full_book)
            else: f(full_book)

    async def _handle_trade(self, data):
        funcs = self.callbacks.get("trade", [])
        for f in funcs:
            t = {
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
        """Generate RSA-PSS headers for WS Handshake"""
        key_id = os.getenv("KALSHI_KEY_ID")
        key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        
        if not key_id or not key_path:
            return {}
            
        try:
            auth = KalshiAuth(key_id, key_path)
            # Handshake is GET /trade-api/ws/v2
            headers = auth.get_ws_headers("GET", "/trade-api/ws/v2")
            return headers
        except Exception as e:
            log(f"WS Auth Error: {e}")
            return {}
