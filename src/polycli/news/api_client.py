from typing import List, Optional, Dict, Any
import aiohttp
import os
import structlog
from .models import NewsItem, UserSubscription, SystemStats

logger = structlog.get_logger()


class NewsAPIClient:
    def __init__(self):
        self.base_url = os.getenv("NEWS_API_URL", "http://localhost:8000")
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_news(
        self,
        limit: int = 50,
        category: Optional[str] = None,
        min_impact: Optional[float] = None,
        source: Optional[str] = None,
        ticker: Optional[str] = None,
        person: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[NewsItem]:
        params = {"limit": limit}
        if category:
            params["category"] = category
        if min_impact:
            params["min_impact"] = min_impact
        if source:
            params["source"] = source
        if ticker:
            params["ticker"] = ticker
        if person:
            params["person"] = person
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        if not self.session:
            self.session = aiohttp.ClientSession()

        async with self.session.get(
            f"{self.base_url}/api/v1/news", params=params
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return [NewsItem(**item) for item in data["items"]]
            else:
                error_text = await resp.text()
                logger.error("News API error", status=resp.status, error=error_text)
                raise Exception(f"API Error: {resp.status} - {error_text}")

    async def create_subscription(self, user_id: str, **kwargs) -> Dict:
        payload = {"user_id": user_id, **kwargs}

        if not self.session:
            self.session = aiohttp.ClientSession()

        async with self.session.post(
            f"{self.base_url}/api/v1/subscriptions", json=payload
        ) as resp:
            return await resp.json()

    async def get_subscription(self, user_id: str) -> Optional[UserSubscription]:
        if not self.session:
            self.session = aiohttp.ClientSession()

        async with self.session.get(
            f"{self.base_url}/api/v1/subscriptions/{user_id}"
        ) as resp:
            if resp.status == 200:
                return UserSubscription(**await resp.json())
            return None

    async def get_stats(self) -> SystemStats:
        if not self.session:
            self.session = aiohttp.ClientSession()

        async with self.session.get(f"{self.base_url}/api/v1/stats") as resp:
            return SystemStats(**await resp.json())

    async def health_check(self) -> Dict:
        if not self.session:
            self.session = aiohttp.ClientSession()

        async with self.session.get(f"{self.base_url}/health") as resp:
            return await resp.json()

    async def close(self):
        if self.session:
            await self.session.close()
