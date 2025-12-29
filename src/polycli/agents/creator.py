import structlog
from typing import List, Dict, Any, Optional

from polycli.agents.base import BaseAgent
from polycli.agents.state import Task
from polycli.agents.executor import ExecutorAgent

logger = structlog.get_logger()

class CreatorAgent(BaseAgent):
    """
    Creator Agent ported from reference implementation.
    Identifies new market creation opportunities (Polymarket only).
    """
    
    def __init__(
        self,
        agent_id: str = "creator",
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
        logger.info("Creator Agent initialized")

    def _register_tools(self):
        """Register creator-specific tools"""
        pass

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """BaseAgent required method"""
        return state

    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Route internal task logic"""
        task_type = task["task_type"]
        
        if task_type == "ONE_BEST_MARKET":
            result = await self.one_best_market()
            return {"result": result}
        else:
            return {"error": f"Unknown task type: {task_type}", "success": False}

    async def one_best_market(self) -> Dict[str, Any]:
        """
        Implementation of the official 'one_best_market' strategy.
        Finds opportunities for new markets.
        """
        if not self.provider or not self.executor:
            return {"error": "Provider or Executor not available", "success": False}

        # Check for provider support
        # We assume for now 'kalshi' string in provider name or type
        prov_name = str(self.provider.__class__.__name__).lower()
        if "kalshi" in prov_name:
            logger.info("CreatorAgent: Disabling for Kalshi (not supported)")
            return {"error": "Market creation not supported for Kalshi", "success": False}

        try:
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

            # 5. Source Best Market Idea
            await self.publish_status("Sourcing new market ideas...")
            best_market_idea = await self.executor.source_best_market_to_create(filtered_markets)
            logger.info(f"Creator: sourced idea: {best_market_idea}")

            return {
                "success": True,
                "strategy": "one_best_market",
                "market_proposal": best_market_idea
            }

        except Exception as e:
            logger.error("Error in one_best_market", error=str(e))
            return {"error": str(e), "success": False}
