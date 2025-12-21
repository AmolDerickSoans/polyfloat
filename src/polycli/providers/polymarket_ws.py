import asyncio
import json
from typing import Callable, Dict, Any, List, Optional, Set
import websockets
import structlog

logger = structlog.get_logger()

class PolymarketWebSocket:
    """
    Robust WebSocket client for Polymarket orderbook and price streams.
    Supports dynamic subscriptions, auto-reconnect, and heartbeat monitoring.
    """
    
    def __init__(self, url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"):
        self.url = url
        self.subscriptions: Dict[str, Set[Callable[[Dict[str, Any]], Any]]] = {}
        self.running = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._listen_task: Optional[asyncio.Task] = None
        self._active_tokens: Set[str] = set()

    async def subscribe(self, token_id: str, callback: Callable[[Dict[str, Any]], Any]):
        """
        Subscribe to updates for a specific token.
        If the connection is active, sends the subscription message immediately.
        """
        if token_id not in self.subscriptions:
            self.subscriptions[token_id] = set()
            # Queue a subscription command for the main loop
            await self._command_queue.put({"type": "subscribe", "token_id": token_id})
        
        self.subscriptions[token_id].add(callback)
        logger.info("Added local subscription", token_id=token_id)

    async def unsubscribe(self, token_id: str, callback: Optional[Callable] = None):
        """
        Unsubscribe from updates. If callback is None, removes all for that token.
        """
        if token_id in self.subscriptions:
            if callback:
                self.subscriptions[token_id].discard(callback)
            
            if not callback or not self.subscriptions[token_id]:
                del self.subscriptions[token_id]
                await self._command_queue.put({"type": "unsubscribe", "token_id": token_id})
                logger.info("Removed all local subscriptions for token", token_id=token_id)

    async def _send_subscription(self, token_id: str):
        """Send the wire-level subscription message"""
        if self._ws and self._ws.open:
            msg = {
                "assets_ids": [token_id],
                "type": "market"
            }
            await self._ws.send(json.dumps(msg))
            self._active_tokens.add(token_id)
            logger.debug("Sent wire subscription", token_id=token_id)

    async def _handle_commands(self):
        """Process subscription commands from the queue while connected"""
        while self.running:
            # Check if there is a command, but don't block forever if ws closes
            try:
                # Use a timeout or just wait for the queue
                cmd = await self._command_queue.get()
                if cmd["type"] == "subscribe":
                    await self._send_subscription(cmd["token_id"])
                self._command_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error processing WS command", error=str(e))

    async def _run_loop(self):
        """Main connection loop with reconnection logic"""
        reconnect_delay = 1
        max_reconnect_delay = 60

        while self.running:
            try:
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    self._active_tokens.clear()
                    reconnect_delay = 1
                    logger.info("Connected to Polymarket WebSocket")
                    
                    # Re-subscribe to all existing tokens
                    for token_id in self.subscriptions:
                        await self._send_subscription(token_id)
                    
                    # Start command handler for this connection
                    command_task = asyncio.create_task(self._handle_commands())
                    
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            await self._dispatch(data)
                    except websockets.ConnectionClosed:
                        logger.warning("WebSocket connection closed")
                    finally:
                        command_task.cancel()
                        self._ws = None
                        
            except Exception as e:
                logger.error("WebSocket loop error", error=str(e))
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    async def _dispatch(self, data: Dict[str, Any]):
        """Route incoming messages to the correct callbacks"""
        # Polymarket 'market' messages usually contain asset_id or related fields
        asset_id = data.get("asset_id") or data.get("token_id")
        
        if not asset_id:
            # Some versions use assets_ids list in response or event-specific formats
            return

        callbacks = self.subscriptions.get(asset_id, set())
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception as e:
                logger.error("Error in WS callback", token_id=asset_id, error=str(e))

    def start(self):
        """Start the WebSocket client in the background"""
        if not self.running:
            self.running = True
            self._listen_task = asyncio.create_task(self._run_loop())
            logger.info("Started Polymarket WS background task")

    async def stop(self):
        """Gracefully stop the WebSocket client"""
        self.running = False
        if self._ws:
            await self._ws.close()
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped Polymarket WS")
