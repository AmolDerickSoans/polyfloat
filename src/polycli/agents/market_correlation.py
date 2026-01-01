import time
import asyncio
from typing import Dict, Any, List, Optional
import structlog
import json

from .base import BaseAgent
from .state import Task, AgentExecutionState

logger = structlog.get_logger()


class MarketCorrelationAgent(BaseAgent):
    """
    Market Correlation Agent

    Purpose: Link news to specific prediction markets, identify correlations,
    find related markets, and detect news-driven price movements.

    Capabilities:
    - Link news items to markets
    - Find markets related to news entities
    - Analyze price impact after news
    - Detect news drift trends
    """

    def __init__(
        self,
        redis_store=None,
        sqlite_store=None,
        poly_provider=None,
        kalshi_provider=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            agent_id="market_correlation",
            model="gemini-2.0-flash",
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            config=config or {},
        )

        self.poly = poly_provider
        self.kalshi = kalshi_provider
        self.market_cache: Dict[str, Any] = {}
        self.news_market_links: Dict[str, List[str]] = {}
        self.correlation_cache: Dict[str, Dict] = {}
        self.cache_ttl = config.get("cache_ttl", 600)  # 10 minutes

        logger.info("Market Correlation Agent initialized")

    def _register_tools(self):
        """Register market correlation tools"""
        logger.info("Registering news tools for correlation agent")
        try:
            from polycli.news.tools import TOOL_FUNCTIONS, TOOL_METADATA

            for tool_name, metadata in TOOL_METADATA.items():
                try:
                    from polycli.news.tools import TOOL_FUNCTIONS as funcs

                    class ToolMetadata:
                        def __init__(
                            self, name, description, parameters, category="general"
                        ):
                            self.name = name
                            self.description = description
                            self.parameters = parameters
                            self.function = funcs.get(tool_name)
                            self.async_function = True

                    self.tool_registry._tools[tool_name] = ToolMetadata(
                        name=metadata["name"],
                        description=metadata["description"],
                        parameters=metadata["parameters"],
                        category=metadata["category"],
                    )
                    logger.debug(f"Registered tool: {tool_name}")
                except Exception as e:
                    logger.error(f"Failed to register tool {tool_name}: {e}")

            logger.info(f"Registered {len(self.tool_registry._tools)} news tools")
        except Exception as e:
            logger.error("Failed to register news tools", error=str(e))

    async def process(self, state: Any) -> Any:
        """Process state and return updated state"""
        await self._cleanup_cache()
        return state

    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Process market correlation task logic"""
        task_type = task["task_type"]

        if task_type == "LINK_NEWS_TO_MARKETS":
            return await self._link_news_to_markets(task)
        elif task_type == "FIND_RELATED_MARKETS":
            return await self._find_related_markets(task)
        elif task_type == "ANALYZE_PRICE_IMPACT":
            return await self._analyze_price_impact(task)
        elif task_type == "DETECT_NEWS_DRIFT":
            return await self._detect_news_drift(task)
        else:
            logger.warning("Unknown task type", task_type=task_type)
            return {"error": f"Unknown task type: {task_type}", "success": False}

    async def _link_news_to_markets(self, task: Task) -> Dict[str, Any]:
        """
        Link news items to prediction markets based on entity matching.

        Logic:
        1. Get news item
        2. Extract entities (tickers, people, keywords)
        3. Search both providers for matching markets
        4. Score market relevance
        5. Return top N related markets
        """
        inputs = task.get("inputs", {})
        news_id = inputs.get("news_id")
        news_data = inputs.get("news_data")
        limit = inputs.get("limit", 10)

        logger.info("Linking news to markets", news_id=news_id)

        try:
            from polycli.news.tools import get_recent_news

            if not news_data:
                news_result = await get_recent_news(limit=100)
                if not news_result["success"]:
                    return {"success": False, "error": "Failed to get news"}

                news_data = next(
                    (
                        item
                        for item in news_result["items"]
                        if item.get("id") == news_id
                    ),
                    None,
                )

                if not news_data:
                    return {"success": False, "error": f"News item {news_id} not found"}

            tickers = news_data.get("tickers", [])
            people = news_data.get("people", [])
            keywords = news_data.get("tags", [])[:5]
            category = news_data.get("category")

            search_queries = []

            for ticker in tickers:
                search_queries.extend(
                    [
                        {"query": f"Will {ticker}", "weight": 3.0},
                        {"query": f"{ticker} price", "weight": 3.0},
                        {"query": ticker, "weight": 2.5},
                    ]
                )

            for person in people:
                search_queries.append({"query": person, "weight": 2.0})

            for keyword in keywords[:3]:
                search_queries.append({"query": keyword, "weight": 1.5})

            seen = set()
            unique_queries = []
            for sq in search_queries:
                if sq["query"] not in seen:
                    seen.add(sq["query"])
                    unique_queries.append(sq)

            search_tasks = []

            for sq in unique_queries[:10]:
                if self.poly:
                    search_tasks.append(
                        self._search_provider(self.poly, sq["query"], "polymarket")
                    )
                if self.kalshi:
                    search_tasks.append(
                        self._search_provider(self.kalshi, sq["query"], "kalshi")
                    )

            results = await asyncio.gather(*search_tasks, return_exceptions=True)

            scored_markets = []

            for result, sq in zip(results, unique_queries):
                if isinstance(result, Exception) or not result:
                    continue

                provider, markets = sq["provider"], result
                query_weight = sq["weight"]

                for market in markets:
                    score = query_weight

                    if category and self._category_matches_market(category, market):
                        score += 2.0

                    market_text = market.question.lower()
                    for ticker in tickers:
                        if ticker.lower() in market_text:
                            score += 1.5
                    for person in people:
                        if person.lower() in market_text:
                            score += 1.0
                    for keyword in keywords:
                        if keyword.lower() in market_text:
                            score += 0.5

                    scored_markets.append(
                        {
                            "market": market,
                            "score": score,
                            "provider": provider,
                            "matched_query": sq["query"],
                        }
                    )

            scored_markets.sort(key=lambda x: x["score"], reverse=True)
            top_markets = scored_markets[:limit]

            linked_market_ids = [m["market"].id for m in top_markets]
            self.news_market_links[news_id] = linked_market_ids

            self.correlation_cache[news_id] = {
                "data": {
                    "linked_markets": top_markets,
                    "entities": {
                        "tickers": tickers,
                        "people": people,
                        "keywords": keywords,
                    },
                },
                "timestamp": time.time(),
            }

            logger.info(
                "News linked to markets",
                news_id=news_id,
                markets_count=len(top_markets),
            )

            return {
                "success": True,
                "news_id": news_id,
                "linked_markets": [
                    {
                        "market_id": m["market"].id,
                        "question": m["market"].question,
                        "provider": m["provider"],
                        "score": m["score"],
                        "matched_query": m["matched_query"],
                    }
                    for m in top_markets
                ],
                "total_searched": len(scored_markets),
                "entities": {
                    "tickers": tickers,
                    "people": people,
                    "keywords": keywords,
                },
            }

        except Exception as e:
            logger.error("Link news to markets failed", news_id=news_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def _search_provider(
        self, provider, query: str, provider_name: str
    ) -> List[Any]:
        """Search a provider for markets"""
        try:
            markets = await provider.search(query, max_results=20)
            return markets
        except Exception as e:
            logger.warning(
                "Provider search failed",
                provider=provider_name,
                query=query,
                error=str(e),
            )
            return []

    def _category_matches_market(self, category: str, market: Any) -> bool:
        """Check if news category matches market topic"""
        category_lower = category.lower()
        market_text = market.question.lower()

        category_keywords = {
            "politics": ["election", "trump", "biden", "president", "congress", "vote"],
            "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain"],
            "economics": ["fed", "inflation", "rate", "economy", "gdp", "unemployment"],
            "sports": ["nfl", "nba", "mlb", "nhl", "championship", "season"],
        }

        keywords = category_keywords.get(category_lower, [])
        return any(kw in market_text for kw in keywords)

    async def _find_related_markets(self, task: Task) -> Dict[str, Any]:
        """
        Find markets related to a news entity (ticker, person, or keyword).

        Similar to link_news_to_markets but simpler - just search for entity.
        """
        inputs = task.get("inputs", {})
        entity = inputs.get("entity")
        entity_type = inputs.get("entity_type", "ticker")
        limit = inputs.get("limit", 10)

        logger.info("Finding related markets", entity=entity, entity_type=entity_type)

        try:
            if entity_type == "ticker":
                queries = [f"Will {entity}", f"{entity} price", entity]
            elif entity_type == "person":
                queries = [entity, f"{entity} win", f"{entity} election"]
            else:
                queries = [entity]

            search_tasks = []

            for query in queries[:3]:
                if self.poly:
                    search_tasks.append(
                        self._search_provider(self.poly, query, "polymarket")
                    )
                if self.kalshi:
                    search_tasks.append(
                        self._search_provider(self.kalshi, query, "kalshi")
                    )

            results = await asyncio.gather(*search_tasks, return_exceptions=True)

            all_markets = []
            seen_market_ids = set()

            for result in results:
                if isinstance(result, Exception) or not result:
                    continue

                for market in result:
                    if market.id not in seen_market_ids:
                        seen_market_ids.add(market.id)
                        all_markets.append(market)

            logger.info(
                "Related markets found", entity=entity, count=len(all_markets[:limit])
            )

            return {
                "success": True,
                "entity": entity,
                "entity_type": entity_type,
                "related_markets": [
                    {
                        "market_id": m.id,
                        "question": m.question,
                        "provider": m.provider,
                        "status": m.status.value,
                    }
                    for m in all_markets[:limit]
                ],
                "count": len(all_markets[:limit]),
            }

        except Exception as e:
            logger.error("Find related markets failed", entity=entity, error=str(e))
            return {"success": False, "error": str(e)}

    async def _analyze_price_impact(self, task: Task) -> Dict[str, Any]:
        """
        Analyze if news caused price movements in related markets.

        Logic:
        1. Get news timestamp
        2. Get orderbook snapshots before and after news
        3. Compare prices
        4. Calculate price change percentage
        """
        inputs = task.get("inputs", {})
        news_id = inputs.get("news_id")
        market_ids = inputs.get("market_ids", [])

        logger.info("Analyzing price impact", news_id=news_id, markets=market_ids)

        try:
            from polycli.news.tools import get_recent_news

            news_result = await get_recent_news(limit=100)
            if not news_result["success"]:
                return {"success": False, "error": "Failed to get news"}

            news_item = next(
                (item for item in news_result["items"] if item.get("id") == news_id),
                None,
            )

            if not news_item:
                return {"success": False, "error": f"News item {news_id} not found"}

            news_time = news_item.get("published_at", 0)

            price_impacts = []

            for market_id in market_ids:
                try:
                    provider = self.poly if market_id.startswith("0x") else self.kalshi
                    if not provider:
                        continue

                    current_ob = await provider.get_orderbook(market_id)

                    best_bid = None
                    best_ask = None

                    if current_ob.bids:
                        best_bid = current_ob.bids[0].price
                    if current_ob.asks:
                        best_ask = current_ob.asks[0].price

                    if best_bid and best_ask:
                        mid_price = (best_bid + best_ask) / 2
                        price_impacts.append(
                            {
                                "market_id": market_id,
                                "mid_price": mid_price,
                                "best_bid": best_bid,
                                "best_ask": best_ask,
                                "spread": best_ask - best_bid,
                                "news_time": news_time,
                            }
                        )

                except Exception as e:
                    logger.warning(
                        "Failed to analyze price impact for market",
                        market_id=market_id,
                        error=str(e),
                    )

            logger.info(
                "Price impact analysis complete",
                news_id=news_id,
                markets_analyzed=len(price_impacts),
            )

            return {
                "success": True,
                "news_id": news_id,
                "price_impacts": price_impacts,
                "analyzed_at": time.time(),
            }

        except Exception as e:
            logger.error("Price impact analysis failed", news_id=news_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def _detect_news_drift(self, task: Task) -> Dict[str, Any]:
        """
        Detect trending news for an entity (increasing mention frequency).

        Logic:
        1. Get recent news for entity
        2. Group by time windows (e.g., hourly)
        3. Calculate mention frequency per window
        4. Detect increasing trend
        """
        inputs = task.get("inputs", {})
        entity = inputs.get("entity")
        entity_type = inputs.get("entity_type", "ticker")
        time_windows = inputs.get("time_windows", 24)

        logger.info("Detecting news drift", entity=entity, entity_type=entity_type)

        try:
            from polycli.news.tools import get_news_by_entity

            if entity_type == "ticker":
                news_result = await get_news_by_entity(ticker=entity, limit=200)
            elif entity_type == "person":
                news_result = await get_news_by_entity(person=entity, limit=200)
            else:
                news_result = await get_news_by_entity(keyword=entity, limit=200)

            if not news_result["success"]:
                return {"success": False, "error": "Failed to get news"}

            news_items = news_result["items"]

            if not news_items:
                return {
                    "success": True,
                    "entity": entity,
                    "drift_detected": False,
                    "message": "No news found for this entity",
                }

            current_time = time.time()
            hour_windows = {}

            for item in news_items:
                published_at = item.get("published_at", 0)
                hours_ago = (current_time - published_at) / 3600
                window = int(hours_ago)

                if window < time_windows:
                    if window not in hour_windows:
                        hour_windows[window] = []
                    hour_windows[window].append(item)

            frequencies = [
                {"hour": h, "count": len(hour_windows[h])}
                for h in sorted(hour_windows.keys())
            ]

            drift_detected = False
            drift_type = "NONE"
            message = "No significant trend detected"

            if len(frequencies) >= 3:
                recent_freq = sum(f["count"] for f in frequencies[:3]) / 3
                earlier_freq = sum(f["count"] for f in frequencies[3:6]) / 3

                if recent_freq > earlier_freq * 1.5:
                    drift_detected = True
                    drift_type = "INCREASING"
                    message = f"News frequency for '{entity}' is increasing ({recent_freq:.1f}/hr vs {earlier_freq:.1f}/hr)"
                elif recent_freq < earlier_freq * 0.5:
                    drift_detected = True
                    drift_type = "DECREASING"
                    message = f"News frequency for '{entity}' is decreasing ({recent_freq:.1f}/hr vs {earlier_freq:.1f}/hr)"

            avg_impact = sum(item.get("impact_score", 0) for item in news_items) / len(
                news_items
            )

            logger.info(
                "News drift detection complete",
                entity=entity,
                drift_detected=drift_detected,
                drift_type=drift_type,
            )

            return {
                "success": True,
                "entity": entity,
                "drift_detected": drift_detected,
                "drift_type": drift_type,
                "message": message,
                "frequencies": frequencies,
                "total_items": len(news_items),
                "average_impact": avg_impact,
                "analyzed_at": time.time(),
            }

        except Exception as e:
            logger.error("News drift detection failed", entity=entity, error=str(e))
            return {"success": False, "error": str(e)}

    async def _cleanup_cache(self):
        """Clean up expired cache entries"""
        current_time = time.time()

        expired = [
            k
            for k, v in self.correlation_cache.items()
            if current_time - v["timestamp"] > self.cache_ttl
        ]
        for k in expired:
            del self.correlation_cache[k]

        if expired:
            logger.debug("Cache cleanup", items_removed=len(expired))
