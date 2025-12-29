import uuid
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from .state import AgentExecutionState, Task, AgentMetadata
from .tools.registry import ToolRegistry
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.providers.base import BaseProvider

logger = structlog.get_logger()


class BaseAgent(ABC):
    """Base class for all agents in the system"""
    
    def __init__(
        self,
        agent_id: str,
        model: str = "gemini-pro",
        redis_store: Optional[RedisStore] = None,
        sqlite_store: Optional[SQLiteStore] = None,
        provider: Optional[BaseProvider] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.agent_id = agent_id
        self.model = model
        self.config = config or {}
        self.redis = redis_store
        self.sqlite = sqlite_store
        self.provider = provider
        self.tool_registry = ToolRegistry()
        
        # Initialize LLM
        self._init_llm()
        
        # Register agent-specific tools
        self._register_tools()
        
        logger.info(
            "Agent initialized",
            agent_id=agent_id,
            model=model
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
            
            return {"error": str(e), "success": False}
    
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
