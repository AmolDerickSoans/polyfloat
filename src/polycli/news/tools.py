from typing import List, Optional, Dict, Any
import structlog
from polycli.news.api_client import NewsAPIClient
from polycli.news.websocket_client import NewsWebSocketClient
from polycli.news.models import NewsItem, UserSubscription, SystemStats

logger = structlog.get_logger()

_news_api_client: Optional[NewsAPIClient] = None
_news_ws_client: Optional[NewsWebSocketClient] = None


def init_news_clients(api_client: NewsAPIClient, ws_client: NewsWebSocketClient):
    global _news_api_client, _news_ws_client
    _news_api_client = api_client
    _news_ws_client = ws_client
    logger.info("News clients initialized for agent tools")


async def get_recent_news(
    limit: int = 20,
    category: Optional[str] = None,
    min_impact: Optional[float] = None,
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    person: Optional[str] = None,
) -> Dict[str, Any]:
    if not _news_api_client:
        raise RuntimeError("News API client not initialized")

    try:
        news_items = await _news_api_client.get_news(
            limit=limit,
            category=category,
            min_impact=min_impact,
            source=source,
            ticker=ticker,
            person=person,
        )

        logger.info(
            "get_recent_news executed",
            limit=limit,
            category=category,
            min_impact=min_impact,
            results=len(news_items),
        )

        return {
            "success": True,
            "count": len(news_items),
            "items": [item.model_dump() for item in news_items],
            "filters_applied": {
                "limit": limit,
                "category": category,
                "min_impact": min_impact,
                "source": source,
                "ticker": ticker,
                "person": person,
            },
        }
    except Exception as e:
        logger.error("get_recent_news failed", error=str(e))
        return {"success": False, "error": str(e)}


async def get_news_by_entity(
    ticker: Optional[str] = None,
    person: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    if not _news_api_client:
        raise RuntimeError("News API client not initialized")

    try:
        if ticker:
            news_items = await _news_api_client.get_news(ticker=ticker, limit=limit)
        elif person:
            news_items = await _news_api_client.get_news(person=person, limit=limit)
        elif keyword:
            all_items = await _news_api_client.get_news(limit=500)
            keyword_lower = keyword.lower()
            news_items = [
                item
                for item in all_items
                if keyword_lower in item.content.lower()
                or (keyword_lower in item.title.lower() if item.title else False)
                or any(keyword_lower in tag.lower() for tag in item.tags)
            ][:limit]
        else:
            news_items = []

        logger.info(
            "get_news_by_entity executed",
            ticker=ticker,
            person=person,
            keyword=keyword,
            results=len(news_items),
        )

        return {
            "success": True,
            "entity": ticker or person or keyword,
            "count": len(news_items),
            "items": [item.model_dump() for item in news_items],
        }
    except Exception as e:
        logger.error("get_news_by_entity failed", error=str(e))
        return {"success": False, "error": str(e)}


async def search_news(query: str, limit: int = 20) -> Dict[str, Any]:
    if not _news_api_client:
        raise RuntimeError("News API client not initialized")

    try:
        all_items = await _news_api_client.get_news(limit=500)
        query_lower = query.lower()

        filtered_items = [
            item
            for item in all_items
            if query_lower in item.content.lower()
            or (item.title and query_lower in item.title.lower())
            or any(query_lower in tag.lower() for tag in item.tags)
            or any(query_lower in person.lower() for person in item.people)
            or any(query_lower in ticker.lower() for ticker in item.tickers)
        ][:limit]

        logger.info("search_news executed", query=query, results=len(filtered_items))

        return {
            "success": True,
            "query": query,
            "count": len(filtered_items),
            "items": [item.model_dump() for item in filtered_items],
        }
    except Exception as e:
        logger.error("search_news failed", error=str(e))
        return {"success": False, "error": str(e)}


async def get_news_stats() -> Dict[str, Any]:
    if not _news_api_client:
        raise RuntimeError("News API client not initialized")

    try:
        stats = await _news_api_client.get_stats()

        logger.info("get_news_stats executed", stats=stats.model_dump())

        return {"success": True, "stats": stats.model_dump()}
    except Exception as e:
        logger.error("get_news_stats failed", error=str(e))
        return {"success": False, "error": str(e)}


async def create_news_subscription(
    user_id: str,
    categories: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    impact_threshold: int = 70,
    alert_channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not _news_api_client:
        raise RuntimeError("News API client not initialized")

    try:
        categories = categories or []
        keywords = keywords or []
        alert_channels = alert_channels or ["terminal"]

        result = await _news_api_client.create_subscription(
            user_id=user_id,
            categories=categories,
            keywords=keywords,
            impact_threshold=impact_threshold,
            alert_channels=alert_channels,
        )

        logger.info(
            "create_news_subscription executed",
            user_id=user_id,
            categories=categories,
            keywords=keywords,
            impact_threshold=impact_threshold,
        )

        return {"success": True, "result": result}
    except Exception as e:
        logger.error("create_news_subscription failed", error=str(e))
        return {"success": False, "error": str(e)}


async def get_news_subscription(user_id: str) -> Dict[str, Any]:
    if not _news_api_client:
        raise RuntimeError("News API client not initialized")

    try:
        subscription = await _news_api_client.get_subscription(user_id)

        if subscription:
            logger.info("get_news_subscription executed", user_id=user_id)
            return {"success": True, "subscription": subscription.model_dump()}
        else:
            return {
                "success": True,
                "subscription": None,
                "message": "No subscription found",
            }
    except Exception as e:
        logger.error("get_news_subscription failed", error=str(e))
        return {"success": False, "error": str(e)}


TOOL_METADATA = {
    "get_recent_news": {
        "name": "get_recent_news",
        "description": "Get recent news items with optional filters (category, impact, source, ticker, person)",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of items (max 100)",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (politics, crypto, economics, sports)",
                },
                "min_impact": {
                    "type": "number",
                    "description": "Minimum impact score (0-100)",
                },
                "source": {
                    "type": "string",
                    "description": "Filter by source (nitter, rss)",
                },
                "ticker": {"type": "string", "description": "Filter by ticker symbol"},
                "person": {"type": "string", "description": "Filter by person name"},
            },
        },
        "category": "news",
    },
    "get_news_by_entity": {
        "name": "get_news_by_entity",
        "description": "Get news related to a specific entity (ticker symbol, person, or keyword)",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., BTC, ETH)",
                },
                "person": {
                    "type": "string",
                    "description": "Person name (e.g., Trump, Powell)",
                },
                "keyword": {
                    "type": "string",
                    "description": "Keyword (e.g., election, fed)",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of results",
                },
            },
        },
        "category": "news",
    },
    "search_news": {
        "name": "search_news",
        "description": "Search news by full-text query",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of results",
                },
            },
            "required": ["query"],
        },
        "category": "news",
    },
    "get_news_stats": {
        "name": "get_news_stats",
        "description": "Get system statistics (total items, items in 24h, average impact)",
        "parameters": {"type": "object"},
        "category": "news",
    },
    "create_news_subscription": {
        "name": "create_news_subscription",
        "description": "Create or update news subscription for a user",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User identifier"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories to follow",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords to track",
                },
                "impact_threshold": {
                    "type": "integer",
                    "default": 70,
                    "description": "Minimum impact score",
                },
                "alert_channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alert channels",
                },
            },
            "required": ["user_id"],
        },
        "category": "news",
    },
    "get_news_subscription": {
        "name": "get_news_subscription",
        "description": "Get user subscription settings",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User identifier"}
            },
            "required": ["user_id"],
        },
        "category": "news",
    },
}

TOOL_FUNCTIONS = {
    "get_recent_news": get_recent_news,
    "get_news_by_entity": get_news_by_entity,
    "search_news": search_news,
    "get_news_stats": get_news_stats,
    "create_news_subscription": create_news_subscription,
    "get_news_subscription": get_news_subscription,
}
