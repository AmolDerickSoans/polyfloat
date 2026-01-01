import uuid
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import structlog
import asyncio
import json
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from .state import AgentExecutionState, Task, AgentMetadata
from .tools.registry import ToolRegistry
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.providers.base import BaseProvider
from polycli.emergency import EmergencyStopController, EmergencyStopError

logger = structlog.get_logger()


class AgentNewsInterface:
    """
    News interface for agents to access news context for trading decisions.
    Extracts relevant entities from market questions and fetches related news.
    """
    
    # Known entities for extraction
    CRYPTO_TICKERS = ["BTC", "ETH", "SOL", "ADA", "DOGE", "MATIC", "AVAX", "XRP", "BNB", "DOT", "LINK"]
    PEOPLE_NAMES = [
        "Trump", "Biden", "Harris", "Obama", "Powell", "Yellen", "Gensler",
        "Musk", "Vitalik", "Buterin", "Zuckerberg", "Altman", "SBF", "CZ"
    ]
    CATEGORY_KEYWORDS = {
        "politics": ["election", "vote", "congress", "senate", "president", "governor", "campaign"],
        "crypto": ["bitcoin", "ethereum", "crypto", "blockchain", "defi", "nft", "token"],
        "economics": ["fed", "rate", "inflation", "gdp", "employment", "treasury", "recession"],
        "sports": ["nba", "nfl", "mlb", "championship", "playoff", "game", "match", "tournament"]
    }
    
    def __init__(self, api_client=None):
        self.api_client = api_client
    
    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract tickers, people, and keywords from market question text"""
        if not text:
            return {"tickers": [], "people": [], "category": None, "keywords": []}
        
        text_upper = text.upper()
        text_lower = text.lower()
        
        # Extract tickers
        tickers = [t for t in self.CRYPTO_TICKERS if t.upper() in text_upper]
        
        # Extract people
        people = [p for p in self.PEOPLE_NAMES if p.lower() in text_lower]
        
        # Detect category
        category = None
        keywords = []
        for cat, cat_keywords in self.CATEGORY_KEYWORDS.items():
            for kw in cat_keywords:
                if kw.lower() in text_lower:
                    category = cat
                    keywords.append(kw)
        
        return {
            "tickers": tickers,
            "people": people,
            "category": category,
            "keywords": keywords
        }
    
    async def get_market_news(self, market_question: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get news related to a specific market question"""
        if not self.api_client:
            return []
        
        try:
            entities = self.extract_entities(market_question)
            news_items = []
            
            # Fetch by ticker first (most specific)
            if entities["tickers"]:
                items = await self.api_client.get_news(
                    ticker=entities["tickers"][0],
                    limit=limit
                )
                news_items.extend([item.model_dump() for item in items])
            
            # Fetch by person if not enough ticker news
            if len(news_items) < limit and entities["people"]:
                items = await self.api_client.get_news(
                    person=entities["people"][0],
                    limit=limit - len(news_items)
                )
                news_items.extend([item.model_dump() for item in items])
            
            # Fetch by category if still not enough
            if len(news_items) < limit and entities["category"]:
                items = await self.api_client.get_news(
                    category=entities["category"],
                    limit=limit - len(news_items)
                )
                news_items.extend([item.model_dump() for item in items])
            
            # Deduplicate by ID
            seen_ids = set()
            unique_items = []
            for item in news_items:
                item_id = item.get("id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    unique_items.append(item)
            
            return unique_items[:limit]
            
        except Exception as e:
            logger.warning("Failed to fetch market news", error=str(e))
            return []
    
    async def get_high_impact_news(self, min_impact: int = 70, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent high-impact news for general market awareness"""
        if not self.api_client:
            return []
        
        try:
            items = await self.api_client.get_news(min_impact=min_impact, limit=limit)
            return [item.model_dump() for item in items]
        except Exception as e:
            logger.warning("Failed to fetch high impact news", error=str(e))
            return []
    
    def format_news_context(self, news_items: List[Dict[str, Any]], max_items: int = 5) -> str:
        """Format news items as context string for LLM prompts"""
        if not news_items:
            return "No recent news available."
        
        lines = []
        for i, item in enumerate(news_items[:max_items], 1):
            impact = item.get("impact_score", 0)
            impact_label = "HIGH" if impact >= 70 else "MEDIUM" if impact >= 40 else "LOW"
            
            title = item.get("title") or item.get("content", "")[:80]
            source = item.get("source", "unknown")
            tickers = item.get("tickers", [])
            people = item.get("people", [])
            
            ticker_str = f" [${', $'.join(tickers[:3])}]" if tickers else ""
            people_str = f" [{', '.join(people[:2])}]" if people else ""
            
            lines.append(f"{i}. [{impact_label}] {title}{ticker_str}{people_str} (via {source})")
        
        return "\n".join(lines)


class BaseAgent(ABC):
    """Base class for all agents in the system"""
    
    def __init__(
        self,
        agent_id: str,
        model: str = "gemini-2.0-flash",
        redis_store: Optional[RedisStore] = None,
        sqlite_store: Optional[SQLiteStore] = None,
        provider: Optional[BaseProvider] = None,
        config: Optional[Dict[str, Any]] = None,
        news_api_client: Optional[Any] = None
    ):
        self.agent_id = agent_id
        self.model = model
        self.config = config or {}
        self.redis = redis_store
        self.sqlite = sqlite_store
        self.provider = provider
        self.tool_registry = ToolRegistry()
        
        # Initialize news interface for market context
        self.news_interface = AgentNewsInterface(api_client=news_api_client)
        self.news_available = news_api_client is not None
        
        # Initialize emergency controller
        self._emergency_controller = EmergencyStopController()
        
        # Initialize LLM
        self._init_llm()
        
        # Register agent-specific tools
        self._register_tools()
        
        logger.info(
            "Agent initialized",
            agent_id=agent_id,
            model=model,
            news_available=self.news_available
        )
    
    def _init_llm(self):
        """Initialize LLM for the agent"""
        try:
            self.llm = ChatGoogleGenerativeAI(model=self.model)
            logger.debug("LLM initialized", model=self.model)
        except Exception as e:
            logger.error("LLM initialization failed", error=str(e))
            self.llm = None
    
    def _register_tools(self):
        """Register tools for this agent. Override in subclasses."""
        pass
    
    @abstractmethod
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process state and return updated state"""
        pass
    
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task and return results"""
        import time
        start_time = time.time()
        
        try:
            # Update task status
            task["started_at"] = start_time
            task["status"] = "RUNNING"
            task["agent_id"] = self.agent_id
            
            logger.info(
                "Task started",
                task_id=task["task_id"],
                agent_id=self.agent_id
            )
            
            # Process the task
            result = await self._process_task_logic(task)
            
            # Update task on completion
            end_time = time.time()
            task["completed_at"] = end_time
            task["status"] = "SUCCESS"
            task["outputs"] = result
            task["latency_ms"] = (end_time - start_time) * 1000
            
            await self.publish_status(f"Task {task['task_id']} completed", status="IDLE")
            
            # Store task result
            if self.redis:
                await self.redis.set(
                    f"task:{task['task_id']}",
                    task,
                    ttl=86400  # 24 hours
                )
            
            if self.sqlite:
                await self.sqlite.set(
                    f"task:{task['task_id']}",
                    task
                )
            
            logger.info(
                "Task completed",
                task_id=task["task_id"],
                latency_ms=task["latency_ms"]
            )
            
            return result
            
        except Exception as e:
            # Update task on error
            end_time = time.time()
            task["completed_at"] = end_time
            task["status"] = "FAILED"
            task["error_message"] = str(e)
            task["latency_ms"] = (end_time - start_time) * 1000
            
            logger.error(
                "Task failed",
                task_id=task["task_id"],
                error=str(e)
            )
            
            await self.publish_status(f"Error: {str(e)}", status="ERROR")
            
            return {"error": str(e), "success": False}
    
    async def publish_status(self, message: str, status: str = "RUNNING"):
        """Publish status message to Redis for TUI visibility"""
        if self.redis:
            payload = {
                "agent_id": self.agent_id,
                "status": status,
                "message": message,
                "timestamp": time.time()
            }
            await self.redis.publish("agent:status:updates", payload)
            
            # Also update health for the panel
            health_payload = {
                "agent_id": self.agent_id,
                "status": status,
                "current_task": message[:20],  # Keep it short for the table
                "timestamp": time.time()
            }
            await self.redis.publish("agent:health", health_payload)
    
    @abstractmethod
    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Process task logic - implement in subclasses"""
        pass
    
    async def create_task(
        self,
        task_type: str,
        description: str,
        inputs: Dict[str, Any],
        priority: str = "NORMAL"
    ) -> Task:
        """Create a new task"""
        import time
        return {
            "task_id": str(uuid.uuid4()),
            "task_type": task_type,
            "description": description,
            "priority": priority,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "status": "PENDING",
            "inputs": inputs,
            "outputs": None,
            "error_message": None,
            "agent_id": None,
            "latency_ms": None
        }
    
    async def call_llm(
        self,
        prompt: str,
        system_message: Optional[str] = None
    ) -> str:
        """Call LLM with prompt and optional system message"""
        if not self.llm:
            raise RuntimeError("LLM not initialized")
        
        messages = []
        if system_message:
            messages.append(SystemMessage(content=system_message))
        messages.append(HumanMessage(content=prompt))
        
        try:
            response = await self.llm.ainvoke(messages)
            content = response.content
            # Handle case where content might be a list or other type
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # If it's a list of text blocks, join them
                return " ".join(str(item) for item in content)
            else:
                return str(content)
        except Exception as e:
            logger.error("LLM call failed", error=str(e))
            raise
    
    def _should_continue(self) -> bool:
        """Check if agent should continue processing."""
        return not self._emergency_controller.is_stopped

    async def get_health_status(self) -> Dict[str, Any]:
        """Get agent health status"""
        import time
        return {
            "agent_id": self.agent_id,
            "model": self.model,
            "status": "RUNNING",
            "tools_registered": len(self.tool_registry._tools),
            "timestamp": time.time()
        }
    
    async def get_task_history(
        self,
        limit: int = 100
    ) -> List[Task]:
        """Get task history for this agent"""
        if not self.sqlite:
            return []
        
        # This would need to be implemented in SQLiteStore
        # For now, return empty list
        return []
