import time
import json
import structlog
from typing import Dict, Any, List, Optional

from polycli.agents.base import BaseAgent
from polycli.agents.state import SupervisorState, Task
from polycli.agents.executor import ExecutorAgent
from polycli.agents.trader import TraderAgent
from polycli.agents.creator import CreatorAgent

logger = structlog.get_logger()

class SupervisorAgent(BaseAgent):
    """
    Central coordinator for the Creator/Trader/Executor trio.
    Ported architecture logic to manage specialized agents.
    """

    def __init__(
        self,
        redis_store=None,
        sqlite_store=None,
        provider=None,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            agent_id="supervisor",
            model="gemini-2.0-flash",
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            provider=provider,
            config=config
        )
        
        # Initialize the specialized agents
        self.executor = ExecutorAgent(
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            provider=provider,
            config=config
        )
        self.trader = TraderAgent(
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            provider=provider,
            executor=self.executor,
            config=config
        )
        self.creator = CreatorAgent(
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            provider=provider,
            executor=self.executor,
            config=config
        )
        
        self.active_agents = ["executor", "trader", "creator"]
        logger.info("Supervisor Agent initialized with Creator/Trader/Executor trio")

    async def process(self, state: SupervisorState) -> SupervisorState:
        """Standard lifecycle method"""
        return state

    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Route tasks to appropriate specialist agent"""
        task_type = task["task_type"]
        
        if task_type in ["SUPERFORECAST", "FILTER_EVENTS", "FILTER_MARKETS", "GET_MARKET_LLM"]:
            return await self.executor.execute_task(task)
        elif task_type == "ONE_BEST_TRADE":
            return await self.trader.execute_task(task)
        elif task_type == "ONE_BEST_MARKET":
            return await self.creator.execute_task(task)
        else:
            return {"error": f"Unknown task type: {task_type}", "success": False}

    async def route_command(self, command: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle natural language or TUI commands.
        Routes to the correct specialist or provides direct info.
        """
        logger.info("Supervisor: Routing command", command=command, args=args)
        
        input_text = args.get("input", "").lower()
        
        # Logic for determining which agent to use
        if "trade" in input_text or "bet" in input_text:
            task = await self.create_task("ONE_BEST_TRADE", "Run one best trade strategy", {})
            result = await self.trader.execute_task(task)
            msg = result.get("result", {}).get("trade_plan", "No trade found")
        elif "create" in input_text or "new market" in input_text:
            task = await self.create_task("ONE_BEST_MARKET", "Run one best market strategy", {})
            result = await self.creator.execute_task(task)
            msg = result.get("result", {}).get("market_proposal", "No market idea found")
        else:
            # Fallback to general market LLM via Executor
            # This implements the reference get_polymarket_llm functionality
            res = await self.executor.get_market_llm(input_text)
            msg = res

        # Publish result for TUI
        if self.redis:
            await self.redis.publish("command:results", json.dumps({
                "command": command,
                "result": msg
            }))
        
        return {
            "success": True,
            "result": msg
        }