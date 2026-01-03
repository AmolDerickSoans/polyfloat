import shutil
import structlog
import time
from typing import Dict, Any, Optional

from polycli.agents.base import BaseAgent
from polycli.agents.state import Task
from polycli.agents.executor import ExecutorAgent
from polycli.agents.tools.trading import TradingTools

logger = structlog.get_logger()


class TraderAgent(BaseAgent):
    """
    Trader Agent ported from reference implementation.
    Responsible for executing the 'one_best_trade' strategy.
    """

    def __init__(
        self,
        agent_id: str = "trader",
        model: str = "gemini-2.0-flash",
        redis_store: Optional[Any] = None,
        sqlite_store: Optional[Any] = None,
        provider: Optional[Any] = None,
        executor: Optional[ExecutorAgent] = None,
        config: Optional[Dict[str, Any]] = None,
        news_api_client: Optional[Any] = None,
    ):
        super().__init__(
            agent_id=agent_id,
            model=model,
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            provider=provider,
            config=config,
            news_api_client=news_api_client,
        )
        self.executor = executor
        self._trading_tools: Optional[TradingTools] = None
        logger.info("Trader Agent initialized", news_available=self.news_available)

    def _register_tools(self):
        """Register trader-specific tools"""
        from polycli.agents.tools.trading import register_trading_tools

        self._trading_tools = TradingTools(poly_provider=self.provider)

        register_trading_tools(
            self.tool_registry,
            self.provider,
            None,
        )

        logger.info("Trading tools registered", agent=self.agent_id)

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """BaseAgent required method"""
        return state

    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Route internal task logic"""
        task_type = task["task_type"]

        if task_type == "ONE_BEST_TRADE":
            result = await self.one_best_trade()
            return {"result": result}
        else:
            return {"error": f"Unknown task type: {task_type}", "success": False}

    def pre_trade_logic(self) -> None:
        """Clear local vector databases before a new run"""
        self.clear_local_dbs()

    def clear_local_dbs(self) -> None:
        """Helper to remove RAG temporary directories"""
        for db_dir in ["local_db_events", "local_db_markets"]:
            try:
                shutil.rmtree(db_dir)
                logger.debug(f"Cleared {db_dir}")
            except Exception:
                pass

    async def one_best_trade(self) -> Dict[str, Any]:
        """
        Implementation of the official 'one_best_trade' strategy.
        Evaluates events, uses RAG filtering, and finds the best trade.
        Now includes news context for enhanced decision-making.
        """
        if not self.provider or not self.executor:
            return {"error": "Provider or Executor not available", "success": False}

        try:
            self.pre_trade_logic()

            # 1. Fetch Events
            await self.publish_status("Fetching events...")
            events = await self.provider.get_events()
            if not events:
                return {"error": "No events found", "success": False}

            # 2. Filter Events with RAG
            await self.publish_status(f"RAG filtering {len(events)} events...")
            filtered_events = await self.executor.filter_events_with_rag(events)
            if not filtered_events:
                return {"error": "No events passed RAG filtering", "success": False}

            # 3. Map events to markets
            await self.publish_status(
                f"Mapping {len(filtered_events)} events to markets..."
            )
            markets = []
            for e_doc in filtered_events:
                e_meta = e_doc[0].metadata
                e_id = e_meta.get("id")
                e_markets = await self.provider.get_markets(event_id=e_id)
                markets.extend(e_markets)

            if not markets:
                return {
                    "error": "No markets found for filtered events",
                    "success": False,
                }

            # 4. Filter Markets with RAG
            await self.publish_status(f"RAG filtering {len(markets)} markets...")
            filtered_markets = await self.executor.filter_markets(markets)
            if not filtered_markets:
                return {"error": "No markets passed RAG filtering", "success": False}

            # 5. Fetch news context for the selected market (Phase 5: News Integration)
            market = filtered_markets[0]
            market_question = market[0].metadata.get("question", "")
            news_context = ""
            risk_context_str = ""

            if self.news_available:
                await self.publish_status("Fetching relevant news...")
                try:
                    market_news = await self.news_interface.get_market_news(
                        market_question, limit=3
                    )

                    high_impact_news = await self.news_interface.get_high_impact_news(
                        min_impact=70, limit=2
                    )

                    all_news = market_news + [
                        n for n in high_impact_news if n not in market_news
                    ]
                    news_context = self.news_interface.format_news_context(all_news[:5])

                    logger.info(
                        "Trader: News context fetched",
                        market_news_count=len(market_news),
                        high_impact_count=len(high_impact_news),
                    )
                except Exception as e:
                    logger.warning("Failed to fetch news context", error=str(e))
                    news_context = ""

            # 5b. Fetch risk context for proactive risk awareness
            try:
                if self._trading_tools:
                    risk_guard = self._trading_tools._get_risk_guard()
                    risk_context = await risk_guard.get_risk_context(
                        getattr(self.provider, "provider_name", "polymarket")
                    )
                    risk_context_str = risk_context.to_llm_context()
                    logger.info(
                        "Trader: Risk context fetched",
                        trading_enabled=risk_context.trading_enabled,
                        circuit_breaker_active=risk_context.circuit_breaker_active,
                        remaining_budget=str(
                            risk_context.remaining_position_budget_usd
                        ),
                    )
            except Exception as e:
                logger.warning("Failed to fetch risk context", error=str(e))
                risk_context_str = ""

            # 6. Source Best Trade (with news context and risk context)
            await self.publish_status("Calculating best trade strategy...")
            best_trade = await self.executor.source_best_trade(
                market, news_context=news_context, risk_context=risk_context_str
            )
            logger.info(f"Trader: calculated trade: {best_trade}")

            # 7. Format and propose/execute
            # In our TUI, we'll usually return this for user approval
            execution_data = self._extract_execution_data(best_trade, market)
            return {
                "success": True,
                "strategy": "one_best_trade",
                "trade_plan": best_trade,
                "market_id": market[0].metadata.get("id"),
                "question": market_question,
                "news_context_used": bool(news_context),
                "execution": execution_data,
            }

        except Exception as e:
            logger.error("Error in one_best_trade", error=str(e))
            return {"error": str(e), "success": False}

    def _extract_execution_data(self, trade_plan: str, market: tuple) -> Dict[str, Any]:
        """Extract execution fields from trade plan and market for proposal execution."""
        import re

        metadata = market[0].metadata if market else {}
        extra = metadata or {}

        token_id = None
        if hasattr(self.provider, "client") or getattr(self.provider, "client", None):
            ctids = extra.get("clobTokenIds", [])
            if isinstance(ctids, str):
                try:
                    import json

                    ctids = json.loads(ctids)
                except Exception:
                    ctids = []
            token_id = ctids[0] if ctids else metadata.get("id")

        side = "BUY"
        amount = 50.0

        side_match = re.search(r"\b(BUY|SELL)\b", trade_plan.upper())
        if side_match:
            side = side_match.group(1)

        amount_match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", trade_plan)
        if amount_match:
            amount = float(amount_match.group(1))

        return {
            "token_id": token_id or metadata.get("id", ""),
            "side": side,
            "amount": amount,
            "provider": "polymarket",
            "generated_at": time.time(),
        }
