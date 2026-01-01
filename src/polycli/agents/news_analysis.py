import time
import asyncio
from typing import Dict, Any, List, Optional
import structlog
import json

from .base import BaseAgent
from .state import Task, AgentExecutionState

logger = structlog.get_logger()


class NewsAnalysisAgent(BaseAgent):
    """
    News Analysis Agent

    Purpose: Analyze news impact on prediction markets, provide sentiment scores,
    summarize topics, and identify high-impact events.

    Capabilities:
    - Analyze impact of news on markets
    - Get sentiment for specific entities (rule-based)
    - Summarize news topics
    - Get related news items
    """

    def __init__(
        self,
        redis_store=None,
        sqlite_store=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            agent_id="news_analysis",
            model="gemini-2.0-flash",
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            config=config or {},
        )

        self.analysis_cache: Dict[str, Dict] = {}
        self.sentiment_cache: Dict[str, Dict] = {}
        self.cache_ttl = config.get("cache_ttl", 300)  # 5 minutes

        logger.info("News Analysis Agent initialized")

    def _register_tools(self):
        """Register news analysis tools"""
        logger.info("Registering news tools")
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

    async def process(self, state: AgentExecutionState) -> AgentExecutionState:
        """Process state and return updated state"""
        await self._cleanup_cache()
        return state

    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Process news analysis task logic"""
        task_type = task["task_type"]

        if task_type == "ANALYZE_NEWS_IMPACT":
            return await self._analyze_news_impact(task)
        elif task_type == "GET_MARKET_SENTIMENT":
            return await self._get_market_sentiment(task)
        elif task_type == "SUMMARIZE_NEWS":
            return await self._summarize_news(task)
        elif task_type == "GET_RELATED_NEWS":
            return await self._get_related_news(task)
        else:
            logger.warning("Unknown task type", task_type=task_type)
            return {"error": f"Unknown task type: {task_type}", "success": False}

    async def _analyze_news_impact(self, task: Task) -> Dict[str, Any]:
        """
        Analyze impact of a news item on markets.

        Logic:
        1. Get news item details
        2. Extract entities (tickers, people, keywords)
        3. Rule-based impact scoring (already from News API)
        4. Identify relevant prediction markets
        5. Provide actionable insights
        """
        inputs = task.get("inputs", {})
        news_id = inputs.get("news_id")
        market_id = inputs.get("market_id")

        logger.info("Analyzing news impact", news_id=news_id, market_id=market_id)

        try:
            from polycli.news.tools import get_recent_news

            news_result = await get_recent_news(limit=1)
            if not news_result["success"] or not news_result["items"]:
                return {"success": False, "error": "Failed to get news"}

            news_item = news_result["items"][0]

            entities = {
                "tickers": news_item.get("tickers", []),
                "people": news_item.get("people", []),
                "keywords": news_item.get("tags", []),
                "category": news_item.get("category"),
            }

            impact_score = news_item.get("impact_score", 0)

            if impact_score >= 80:
                impact_level = "HIGH"
                recommendation = "Strong signal - consider immediate position review"
            elif impact_score >= 60:
                impact_level = "MEDIUM"
                recommendation = "Moderate signal - monitor closely"
            else:
                impact_level = "LOW"
                recommendation = "Weak signal - informational only"

            related_markets = []
            if market_id:
                related_markets.append(market_id)

            analysis = {
                "news_id": news_id,
                "impact_level": impact_level,
                "impact_score": impact_score,
                "entities": entities,
                "recommendation": recommendation,
                "related_markets": related_markets,
                "analyzed_at": time.time(),
            }

            self.analysis_cache[news_id] = {"data": analysis, "timestamp": time.time()}

            if self.redis:
                await self.redis.publish(
                    "agent:news",
                    json.dumps(
                        {
                            "type": "news_analysis",
                            "agent": self.agent_id,
                            "data": {
                                "news_item": news_item,
                                "analysis": analysis,
                                "recommendation": recommendation,
                                "related_markets": related_markets,
                            },
                        }
                    ),
                )

            logger.info(
                "News analysis complete", news_id=news_id, impact_level=impact_level
            )

            return {"success": True, "analysis": analysis, "news_item": news_item}

        except Exception as e:
            logger.error("News analysis failed", news_id=news_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def _get_market_sentiment(self, task: Task) -> Dict[str, Any]:
        """
        Get sentiment score for a specific entity/market.

        Logic (rule-based, no ML):
        1. Get recent news for entity
        2. Count positive/negative indicators from keywords
        3. Calculate sentiment score (-100 to +100)
        4. Calculate trend (improving, declining, stable)
        """
        inputs = task.get("inputs", {})
        entity = inputs.get("entity")
        entity_type = inputs.get("entity_type", "ticker")
        time_range = inputs.get("time_range", "24h")

        logger.info("Getting market sentiment", entity=entity, entity_type=entity_type)

        try:
            from polycli.news.tools import get_news_by_entity

            cache_key = f"{entity_type}:{entity}:{time_range}"
            if cache_key in self.sentiment_cache:
                cached = self.sentiment_cache[cache_key]
                if time.time() - cached["timestamp"] < self.cache_ttl:
                    logger.debug("Sentiment cache hit", entity=entity)
                    return {"success": True, "sentiment": cached["data"], "cache": True}

            news_result = await get_news_by_entity(**{entity_type: entity}, limit=50)

            if not news_result["success"]:
                return {"success": False, "error": "Failed to get news"}

            news_items = news_result["items"]

            positive_keywords = [
                "positive",
                "up",
                "increase",
                "growth",
                "rise",
                "surge",
                "bull",
                "bullish",
                "breakthrough",
                "rally",
                "gain",
                "profit",
                "beat",
                "exceed",
                "outperform",
            ]
            negative_keywords = [
                "negative",
                "down",
                "decrease",
                "decline",
                "fall",
                "drop",
                "bear",
                "bearish",
                "crash",
                "loss",
                "miss",
                "fail",
                "underperform",
                "concern",
                "risk",
                "warning",
            ]

            positive_count = 0
            negative_count = 0
            neutral_count = 0

            for item in news_items:
                content = item.get("content", "").lower()
                title = (item.get("title") or "").lower()
                text = f"{title} {content}"

                pos_occurrences = sum(1 for kw in positive_keywords if kw in text)
                neg_occurrences = sum(1 for kw in negative_keywords if kw in text)

                if pos_occurrences > neg_occurrences:
                    positive_count += 1
                elif neg_occurrences > pos_occurrences:
                    negative_count += 1
                else:
                    neutral_count += 1

            total = len(news_items)
            if total > 0:
                sentiment_score = ((positive_count - negative_count) / total) * 100
            else:
                sentiment_score = 0.0

            if sentiment_score >= 30:
                sentiment_label = "BULLISH"
            elif sentiment_score >= 10:
                sentiment_label = "SLIGHTLY_BULLISH"
            elif sentiment_score <= -30:
                sentiment_label = "BEARISH"
            elif sentiment_score <= -10:
                sentiment_label = "SLIGHTLY_BEARISH"
            else:
                sentiment_label = "NEUTRAL"

            sentiment_data = {
                "entity": entity,
                "entity_type": entity_type,
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "total_items": total,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "neutral_count": neutral_count,
                "analyzed_at": time.time(),
            }

            self.sentiment_cache[cache_key] = {
                "data": sentiment_data,
                "timestamp": time.time(),
            }

            logger.info(
                "Sentiment analysis complete",
                entity=entity,
                sentiment=sentiment_label,
                score=sentiment_score,
            )

            return {"success": True, "sentiment": sentiment_data, "news_count": total}

        except Exception as e:
            logger.error("Sentiment analysis failed", entity=entity, error=str(e))
            return {"success": False, "error": str(e)}

    async def _summarize_news(self, task: Task) -> Dict[str, Any]:
        """
        Summarize news about a topic.

        Logic:
        1. Get news for topic
        2. Extract key points (entities, impact, timestamps)
        3. Generate summary text
        """
        inputs = task.get("inputs", {})
        topic = inputs.get("topic")
        time_range = inputs.get("time_range", "24h")

        logger.info("Summarizing news", topic=topic, time_range=time_range)

        try:
            from polycli.news.tools import search_news

            search_result = await search_news(query=topic, limit=50)

            if not search_result["success"]:
                return {"success": False, "error": "Failed to search news"}

            news_items = search_result["items"]

            if not news_items:
                return {
                    "success": True,
                    "topic": topic,
                    "summary": "No news found for this topic.",
                    "count": 0,
                }

            high_impact_items = [
                item for item in news_items if item.get("impact_score", 0) >= 70
            ]

            all_tickers = set()
            all_people = set()
            for item in news_items:
                all_tickers.update(item.get("tickers", []))
                all_people.update(item.get("people", []))

            summary_parts = [
                f"Found {len(news_items)} news items about '{topic}' in recent period.",
            ]

            if high_impact_items:
                summary_parts.append(
                    f"\n🔴 High-impact items: {len(high_impact_items)}"
                )
                for item in high_impact_items[:3]:
                    title = item.get("title", item.get("content", "")[:60])
                    summary_parts.append(
                        f"  • {title}... "
                        f"(Impact: {item.get('impact_score', 0):.0f})"
                    )

            if all_tickers:
                summary_parts.append(
                    f"\n📊 Tickers mentioned: {', '.join(list(all_tickers)[:10])}"
                )

            if all_people:
                summary_parts.append(
                    f"\n👥 People mentioned: {', '.join(list(all_people)[:10])}"
                )

            avg_impact = sum(item.get("impact_score", 0) for item in news_items) / len(
                news_items
            )
            summary_parts.append(f"\n📈 Average impact score: {avg_impact:.1f}/100")

            summary = "\n".join(summary_parts)

            logger.info("News summary complete", topic=topic, items=len(news_items))

            return {
                "success": True,
                "topic": topic,
                "summary": summary,
                "count": len(news_items),
                "high_impact_count": len(high_impact_items),
                "tickers": list(all_tickers),
                "people": list(all_people),
                "average_impact": avg_impact,
            }

        except Exception as e:
            logger.error("News summary failed", topic=topic, error=str(e))
            return {"success": False, "error": str(e)}

    async def _get_related_news(self, task: Task) -> Dict[str, Any]:
        """
        Get news related to a specific news item.

        Logic:
        1. Get entities from original item
        2. Find news with matching entities
        3. Sort by recency and impact
        """
        inputs = task.get("inputs", {})
        news_id = inputs.get("news_id")
        limit = inputs.get("limit", 10)

        logger.info("Getting related news", news_id=news_id)

        try:
            from polycli.news.tools import get_recent_news

            news_result = await get_recent_news(limit=100)

            if not news_result["success"]:
                return {"success": False, "error": "Failed to get news"}

            original_item = None
            for item in news_result["items"]:
                if item.get("id") == news_id:
                    original_item = item
                    break

            if not original_item:
                return {"success": False, "error": f"News item {news_id} not found"}

            tickers = original_item.get("tickers", [])
            people = original_item.get("people", [])
            keywords = original_item.get("tags", [])[:3]

            related_items = []
            for item in news_result["items"]:
                if item.get("id") == news_id:
                    continue

                overlap = 0

                item_tickers = set(item.get("tickers", []))
                item_people = set(item.get("people", []))
                item_tags = set(item.get("tags", []))

                overlap += len(set(tickers) & item_tickers) * 3
                overlap += len(set(people) & item_people) * 2
                overlap += len(set(keywords) & item_tags)

                if overlap > 0:
                    item["_similarity"] = overlap
                    related_items.append(item)

            related_items.sort(
                key=lambda x: (x.get("_similarity", 0), x.get("impact_score", 0)),
                reverse=True,
            )

            for item in related_items:
                item.pop("_similarity", None)

            logger.info(
                "Related news found", news_id=news_id, count=len(related_items[:limit])
            )

            return {
                "success": True,
                "original_item": original_item,
                "related_news": related_items[:limit],
                "count": len(related_items[:limit]),
            }

        except Exception as e:
            logger.error("Get related news failed", news_id=news_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def _cleanup_cache(self):
        """Clean up expired cache entries"""
        current_time = time.time()

        expired_analysis = [
            k
            for k, v in self.analysis_cache.items()
            if current_time - v["timestamp"] > self.cache_ttl
        ]
        for k in expired_analysis:
            del self.analysis_cache[k]

        expired_sentiment = [
            k
            for k, v in self.sentiment_cache.items()
            if current_time - v["timestamp"] > self.cache_ttl
        ]
        for k in expired_sentiment:
            del self.sentiment_cache[k]

        if expired_analysis or expired_sentiment:
            logger.debug(
                "Cache cleanup",
                analysis_removed=len(expired_analysis),
                sentiment_removed=len(expired_sentiment),
            )
