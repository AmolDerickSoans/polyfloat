import shutil
import structlog
from typing import List, Dict, Any, Optional

from polycli.agents.base import BaseAgent
from polycli.agents.state import Task
from polycli.agents.executor import ExecutorAgent

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
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            agent_id=agent_id,
            model=model,
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            provider=provider,
            config=config
        )
        self.executor = executor
        logger.info("Trader Agent initialized")

    def _register_tools(self):
        """Register trader-specific tools"""
        pass

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
            except Exception as e:
                pass

    async def one_best_trade(self) -> Dict[str, Any]:
        """
        Implementation of the official 'one_best_trade' strategy.
        Evaluates events, uses RAG filtering, and finds the best trade.
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
            await self.publish_status(f"Mapping {len(filtered_events)} events to markets...")
            markets = []
            for e_doc in filtered_events:
                e_meta = e_doc[0].metadata
                e_id = e_meta.get("id")
                e_markets = await self.provider.get_markets(event_id=e_id)
                markets.extend(e_markets)
            
            if not markets:
                return {"error": "No markets found for filtered events", "success": False}

            # 4. Filter Markets with RAG
            await self.publish_status(f"RAG filtering {len(markets)} markets...")
            filtered_markets = await self.executor.filter_markets(markets)
            if not filtered_markets:
                return {"error": "No markets passed RAG filtering", "success": False}

            # 5. Source Best Trade
            await self.publish_status("Calculating best trade strategy...")
            market = filtered_markets[0]
            best_trade = await self.executor.source_best_trade(market)
            logger.info(f"Trader: calculated trade: {best_trade}")

            # 6. Format and propose/execute
            # In our TUI, we'll usually return this for user approval
            return {
                "success": True,
                "strategy": "one_best_trade",
                "trade_plan": best_trade,
                "market_id": market[0].metadata.get("id"),
                "question": market[0].metadata.get("question")
            }

        except Exception as e:
            logger.error("Error in one_best_trade", error=str(e))
            return {"error": str(e), "success": False}
