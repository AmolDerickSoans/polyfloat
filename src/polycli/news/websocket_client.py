import asyncio
import json
import os
from typing import Callable, Dict, Any, Optional, Set, List
import websockets
import structlog

logger = structlog.get_logger()


class NewsWebSocketClient:
    URL_TEMPLATE = "ws://{base_url}/ws/news"

    def __init__(self):
        base_url = (
            os.getenv("NEWS_API_URL", "localhost:8000")
            .replace("http://", "")
            .replace("https://", "")
        )
        self.url = self.URL_TEMPLATE.format(base_url=base_url)
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.keep_running = False
        self.callbacks: Dict[str, List[Callable]] = {"news_item": []}
        self._listen_task: Optional[asyncio.Task] = None
        self.user_id: str = os.getenv("NEWS_API_USER_ID", "terminal_user")
        self.filters: Dict[str, Any] = {}

    def add_callback(self, channel: str, callback: Callable):
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)

    async def connect(self, user_id: str = None, filters: Dict[str, Any] = None):
        if user_id is not None:
            self.user_id = user_id
        if filters is not None:
            self.filters = filters

        self.keep_running = True
        self._listen_task = asyncio.create_task(self._run_loop())
        logger.info("News WebSocket connecting", url=self.url)

    async def _run_loop(self):
        reconnect_delay = 1
        while self.keep_running:
            try:
                ws_url = f"{self.url}?user_id={self.user_id}"
                async with websockets.connect(ws_url) as ws:
                    self.ws = ws
                    reconnect_delay = 1
                    logger.info("News WebSocket connected")

                    if self.filters:
                        await self._send_subscription()

                    async for msg in ws:
                        data = json.loads(msg)
                        await self._dispatch(data)

            except Exception as e:
                logger.error("News WebSocket error", error=str(e))
                if not self.keep_running:
                    break
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def _dispatch(self, data: Dict[str, Any]):
        msg_type = data.get("type")

        if msg_type == "news_item":
            news_data = data.get("data")
            for callback in self.callbacks["news_item"]:
                if asyncio.iscoroutinefunction(callback):
                    await callback(news_data)
                else:
                    callback(news_data)
        elif msg_type == "keep_alive":
            logger.debug("Keep-alive received")
        elif msg_type == "error":
            logger.error("WebSocket error", message=data.get("message"))

    async def subscribe(self, filters: Dict[str, Any]):
        self.filters = filters
        if self.ws:
            await self._send_subscription()

    async def _send_subscription(self):
        if not self.ws:
            logger.warning("Cannot send subscription - WebSocket not connected")
            return

        msg = {"type": "subscribe", "filters": self.filters}
        await self.ws.send(json.dumps(msg))

    async def disconnect(self):
        self.keep_running = False
        if self.ws:
            await self.ws.close()
        if self._listen_task:
            self._listen_task.cancel()
        logger.info("News WebSocket disconnected")
