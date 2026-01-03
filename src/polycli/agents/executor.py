import ast
import math
import structlog
from typing import List, Dict, Any, Optional, Tuple

from polycli.agents.base import BaseAgent
from polycli.agents.state import Task
from polycli.agents.tools.chroma import ChromaConnector
from polycli.agents.tools.search import SearchConnector
from .prompts import Prompter

logger = structlog.get_logger()


def retain_keys(data, keys_to_retain):
    if isinstance(data, dict):
        return {
            key: retain_keys(value, keys_to_retain)
            for key, value in data.items()
            if key in keys_to_retain
        }
    elif isinstance(data, list):
        return [retain_keys(item, keys_to_retain) for item in data]
    else:
        return data


class ExecutorAgent(BaseAgent):
    """
    Executor Agent ported from reference implementation.
    Acts as the central orchestrator for RAG, filtering, and analysis.
    """

    def __init__(
        self,
        agent_id: str = "executor",
        model: str = "gemini-2.0-flash",
        redis_store: Optional[Any] = None,
        sqlite_store: Optional[Any] = None,
        provider: Optional[Any] = None,
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

        # Token limits for Gemini are much higher than GPT-3.5,
        # but we'll keep the logic for chunking if needed.
        self.token_limit = self.config.get("token_limit", 100000)

        # Connectors
        self.chroma = ChromaConnector()
        self.search = SearchConnector()
        self.prompter = Prompter()

        logger.info("Executor Agent initialized", news_available=self.news_available)

    def _register_tools(self):
        """Register executor-specific tools"""
        # Registering tools that specialist agents can use via Supervisor
        pass

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """BaseAgent required method"""
        return state

    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Route internal task logic"""
        task_type = task["task_type"]
        inputs = task.get("inputs", {})

        if task_type == "SUPERFORECAST":
            result = await self.get_superforecast(
                inputs.get("event_title", ""),
                inputs.get("market_question", ""),
                inputs.get("outcome", ""),
            )
            return {"result": result}
        elif task_type == "FILTER_EVENTS":
            result = await self.filter_events(inputs.get("events", []))
            return {"result": result}
        elif task_type == "FILTER_MARKETS":
            result = await self.filter_markets(inputs.get("markets", []))
            return {"result": result}
        else:
            return {"error": f"Unknown task type: {task_type}", "success": False}

    async def get_superforecast(
        self, event_title: str, market_question: str, outcomes: List[str]
    ) -> str:
        """Ported from reference: Get a probabilistic assessment of an event"""
        if not self.prompter:
            return "Prompter not initialized"

        prompt = self.prompter.superforecaster(
            description=event_title, question=market_question, outcomes=outcomes
        )
        # Use BaseAgent's call_llm
        return await self.call_llm(prompt)

    def estimate_tokens(self, text: str) -> int:
        """Rough estimate of tokens"""
        return len(text) // 4

    def divide_list(self, original_list: List, i: int) -> List[List]:
        """Split list into i roughly equal parts"""
        if i <= 0:
            return [original_list]
        sublist_size = math.ceil(len(original_list) / i)
        return [
            original_list[j : j + sublist_size]
            for j in range(0, len(original_list), sublist_size)
        ]

    async def filter_events(self, events: List[Any]) -> str:
        """Ported from reference: Use LLM to filter relevant events"""
        if not self.prompter:
            return "Prompter not initialized"
        prompt = self.prompter.filter_events(events)
        return await self.call_llm(prompt)

    async def filter_events_with_rag(
        self, events: List[Any]
    ) -> List[Tuple[Any, float]]:
        """Ported from reference: Use RAG to filter events"""
        if not self.prompter:
            return []
        prompt = self.prompter.filter_events()
        logger.info("Executor: filtering events with RAG", prompt=prompt)
        return self.chroma.events(events, prompt)

    async def filter_markets(self, markets: List[Any]) -> List[Tuple[Any, float]]:
        """Ported from reference: Use RAG to filter markets"""
        if not self.prompter:
            return []
        prompt = self.prompter.filter_markets()
        logger.info("Executor: filtering markets with RAG", prompt=prompt)
        return self.chroma.markets(markets, prompt)

    async def source_best_trade(
        self,
        market_object: Any,
        news_context: str = "",
        risk_context: Optional[str] = None,
    ) -> str:
        """Determine optimal trade parameters with optional news and risk context."""
        if not self.prompter:
            return "Prompter not initialized"

        market_document = market_object[0].dict()
        market_meta = market_document["metadata"]

        outcome_prices = market_meta.get("outcome_prices")
        if isinstance(outcome_prices, str):
            outcome_prices = ast.literal_eval(outcome_prices)

        outcomes = market_meta.get("outcomes")
        if isinstance(outcomes, str):
            outcomes = ast.literal_eval(outcomes)

        question = market_meta.get("question", "")
        description = market_document.get("page_content", "")

        enhanced_description = description
        if news_context:
            enhanced_description = f"""{description}

RECENT RELEVANT NEWS:
{news_context}

Consider the above news when making your forecast. Recent developments may significantly impact probabilities."""

        sf_prompt = self.prompter.superforecaster(
            question, enhanced_description, outcomes
        )
        sf_result = await self.call_llm(sf_prompt)
        logger.info(
            "Executor: Superforecast complete",
            result=sf_result,
            has_news_context=bool(news_context),
        )

        bt_prompt = self.prompter.one_best_trade(
            sf_result, outcomes, outcome_prices, risk_context=risk_context
        )
        bt_result = await self.call_llm(bt_prompt)
        logger.info("Executor: Best trade identified", result=bt_result)

        return bt_result

    async def source_best_market_to_create(self, filtered_markets: List[Any]) -> str:
        """Ported from reference: Invent a new information market"""
        if not self.prompter:
            return "Prompter not initialized"
        prompt = self.prompter.create_new_market(filtered_markets)
        return await self.call_llm(prompt)

    async def get_market_llm(self, user_input: str) -> str:
        """Ported from reference: Answer user query using all current market data with chunking"""
        if not self.provider:
            return "No provider available"

        await self.publish_status("Fetching current market data...")
        events = await self.provider.get_events()
        markets = await self.provider.get_markets()

        await self.publish_status(
            f"Processing {len(events)} events and {len(markets)} markets..."
        )
        combined_data_str = str(
            self.prompter.prompts_market(data1=events, data2=markets)
        )
        total_tokens = self.estimate_tokens(combined_data_str)

        if total_tokens <= self.token_limit:
            await self.publish_status("Generating response (single chunk)...")
            prompt = self.prompter.prompts_market(data1=events, data2=markets)
            return await self.call_llm(prompt, system_message=user_input)
        else:
            # Chunking logic
            group_size = (total_tokens // self.token_limit) + 1
            useful_keys = [
                "id",
                "description",
                "liquidity",
                "outcomes",
                "outcomePrices",
                "volume",
                "startDate",
                "endDate",
                "question",
                "events",
            ]

            # Simplified chunking for now
            data1_clean = retain_keys(events, useful_keys)
            cut_1 = self.divide_list(data1_clean, group_size)
            cut_2 = self.divide_list(markets, group_size)

            results = []
            for i, (sub_events, sub_markets) in enumerate(zip(cut_1, cut_2)):
                await self.publish_status(
                    f"Generating response (chunk {i+1}/{group_size})..."
                )
                prompt = self.prompter.prompts_market(
                    data1=sub_events, data2=sub_markets
                )
                res = await self.call_llm(prompt, system_message=user_input)
                results.append(res)

            return " ".join(results)
