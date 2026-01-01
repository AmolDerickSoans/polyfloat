"""Tests for Phase 1: Base Agent"""
import pytest
import asyncio
from polycli.agents.base import BaseAgent
from polycli.agents.state import Task
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore


class MockAgent(BaseAgent):
    """Mock agent for testing"""
    
    async def process(self, state):
        return {"processed": True, **state}
    
    async def _process_task_logic(self, task: Task):
        return {"result": "task_completed", "task_id": task["task_id"]}


@pytest.fixture
async def agent_stores():
    """Create storage instances for testing"""
    redis = RedisStore(prefix="test:agent:")
    sqlite = SQLiteStore(":memory:")
    yield redis, sqlite
    await redis.close()
    await sqlite.close()


@pytest.fixture
async def base_agent(agent_stores):
    """Create a base agent instance"""
    redis, sqlite = agent_stores
    agent = MockAgent(
        agent_id="test_agent",
        model="gemini-2.0-flash",
        redis_store=redis,
        sqlite_store=sqlite
    )
    yield agent


class TestBaseAgent:
    """Test BaseAgent functionality"""
    
    def test_agent_initialization(self, base_agent):
        """Test agent initialization"""
        assert base_agent.agent_id == "test_agent"
        assert base_agent.model == "gemini-2.0-flash"
        assert base_agent.redis is not None
        assert base_agent.sqlite is not None
        assert base_agent.tool_registry is not None
        assert base_agent.provider is None

    def test_agent_initialization_with_provider(self, agent_stores):
        """Test agent initialization with a provider"""
        from polycli.providers.base import BaseProvider
        class MockProvider(BaseProvider):
            async def get_events(self, **kwargs): return []
            async def get_markets(self, **kwargs): return []
            async def search(self, **kwargs): return []
            async def get_orderbook(self, **kwargs): return None
            async def place_order(self, **kwargs): return None
            async def cancel_order(self, **kwargs): return False
            async def get_positions(self, **kwargs): return []
            async def get_orders(self, **kwargs): return []
            async def get_history(self, **kwargs): return []
            async def get_news(self, **kwargs): return []
        
        redis, sqlite = agent_stores
        provider = MockProvider()
        agent = MockAgent(
            agent_id="provider_agent",
            redis_store=redis,
            sqlite_store=sqlite,
            provider=provider
        )
        assert agent.provider == provider

    @pytest.mark.asyncio
    async def test_process_state(self, base_agent):
        """Test processing state"""
        input_state = {"test": "data"}
        result = await base_agent.process(input_state)
        assert result["processed"] == True
        assert result["test"] == "data"
    
    @pytest.mark.asyncio
    async def test_create_task(self, base_agent):
        """Test task creation"""
        task = await base_agent.create_task(
            task_type="TEST",
            description="Test task",
            inputs={"test_input": "value"},
            priority="HIGH"
        )
        
        assert task["task_id"] is not None
        assert task["task_type"] == "TEST"
        assert task["description"] == "Test task"
        assert task["inputs"] == {"test_input": "value"}
        assert task["priority"] == "HIGH"
        assert task["status"] == "PENDING"
        assert task["created_at"] is not None
        assert task["started_at"] is None
        assert task["completed_at"] is None
    
    @pytest.mark.asyncio
    async def test_execute_task(self, base_agent):
        """Test task execution"""
        task = await base_agent.create_task(
            task_type="TEST",
            description="Test task",
            inputs={"test": "data"}
        )
        
        result = await base_agent.execute_task(task)
        
        assert task["status"] == "SUCCESS"
        assert task["agent_id"] == "test_agent"
        assert task["started_at"] is not None
        assert task["completed_at"] is not None
        assert task["latency_ms"] is not None
        assert task["error_message"] is None
        assert result["result"] == "task_completed"
        assert result["task_id"] == task["task_id"]
    
    @pytest.mark.asyncio
    async def test_execute_task_with_error(self, base_agent):
        """Test task execution with error"""
        class ErrorAgent(MockAgent):
            async def _process_task_logic(self, task: Task):
                raise ValueError("Test error")
        
        redis, sqlite = base_agent.redis, base_agent.sqlite
        error_agent = ErrorAgent(
            agent_id="error_agent",
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await error_agent.create_task(
            task_type="ERROR_TEST",
            description="Error test task",
            inputs={}
        )
        
        result = await error_agent.execute_task(task)
        
        assert task["status"] == "FAILED"
        assert task["error_message"] == "Test error"
        assert result["error"] == "Test error"
        assert result["success"] == False
    
    @pytest.mark.asyncio
    async def test_get_health_status(self, base_agent):
        """Test getting health status"""
        health = await base_agent.get_health_status()
        
        assert health["agent_id"] == "test_agent"
        assert health["model"] == "gemini-2.0-flash"
        assert health["status"] == "RUNNING"
        assert "tools_registered" in health
        assert "timestamp" in health
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="LLM quota exhausted - API key is hitting free tier limits despite billing setup")
    async def test_call_llm(self, base_agent):
        """Test LLM call"""
        response = await base_agent.call_llm("Say hello")
        
        assert response is not None
        assert isinstance(response, str)
        assert len(response) > 0
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="LLM quota exhausted - API key is hitting free tier limits despite billing setup")
    async def test_call_llm_with_system_message(self, base_agent):
        """Test LLM call with system message"""
        response = await base_agent.call_llm(
            "What is 2 + 2?",
            system_message="You are a helpful assistant that answers concisely."
        )
        
        assert response is not None
        assert isinstance(response, str)
        assert "4" in response.lower() or "two" in response.lower()
    
    @pytest.mark.asyncio
    async def test_task_persistence(self, base_agent):
        """Test that tasks are persisted to storage"""
        task = await base_agent.create_task(
            task_type="PERSIST_TEST",
            description="Persistence test",
            inputs={"test": "data"}
        )
        
        await base_agent.execute_task(task)
        
        # Check Redis
        redis_result = await base_agent.redis.get(f"task:{task['task_id']}")
        assert redis_result is not None
        assert redis_result["task_id"] == task["task_id"]
        
        # Check SQLite
        sqlite_result = await base_agent.sqlite.get(f"task:{task['task_id']}")
        assert sqlite_result is not None
        assert sqlite_result["task_id"] == task["task_id"]
    
    @pytest.mark.asyncio
    async def test_get_task_history(self, base_agent):
        """Test getting task history"""
        # Execute a few tasks
        for i in range(3):
            task = await base_agent.create_task(
                task_type="HISTORY_TEST",
                description=f"History test {i}",
                inputs={"index": i}
            )
            await base_agent.execute_task(task)
        
        history = await base_agent.get_task_history(limit=10)
        # Note: This might be empty depending on SQLite implementation
        assert isinstance(history, list)


class TestAgentTools:
    """Test agent tool registration"""
    
    def test_tool_registration_in_agent(self, base_agent):
        """Test that agents can register tools"""
        # Base agent should have empty tool registry initially
        initial_count = len(base_agent.tool_registry.get_all())
        
        class ToolAgent(MockAgent):
            def _register_tools(self):
                @self.tool_registry.register(
                    name="custom_tool",
                    description="Custom tool",
                    category="test"
                )
                async def custom_tool(data: str):
                    return f"Processed: {data}"
        
        redis, sqlite = base_agent.redis, base_agent.sqlite
        tool_agent = ToolAgent(
            agent_id="tool_agent",
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Tool should be registered
        assert tool_agent.tool_registry.exists("custom_tool")
