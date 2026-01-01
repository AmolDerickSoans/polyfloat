"""Simple test for agent panel and chat interface components"""
import sys
import asyncio

sys.path.insert(0, 'src')

from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.tui_agent_panel import AgentStatusPanel
from polycli.tui_agent_chat import AgentChatInterface


class MockSupervisor:
    """Mock supervisor for testing"""
    
    async def route_command(self, command: str, args: dict):
        return {
            "success": True,
            "result": f"Test response to: {command}"
        }


async def test_agent_panel():
    """Test agent panel functionality"""
    redis = RedisStore(prefix="test:")
    sqlite = SQLiteStore(":memory:")
    supervisor = MockSupervisor()
    
    panel = AgentStatusPanel(redis_store=redis)
    
    # Simulate some agent data
    panel.agent_data = {
        "market_observer": {
            "status": "RUNNING",
            "current_task": "SCAN_MARKETS",
            "queue_depth": 2
        },
        "alert_manager": {
            "status": "IDLE",
            "current_task": "MONITOR",
            "queue_depth": 0
        },
    }
    
    panel._render_agent_table()
    print("Agent Panel Test: PASS")


async def test_chat_interface():
    """Test chat interface functionality"""
    redis = RedisStore(prefix="test:")
    sqlite = SQLiteStore(":memory:")
    supervisor = MockSupervisor()
    
    chat = AgentChatInterface(redis_store=redis, supervisor=supervisor)
    
    # Test message formatting
    chat._add_conversation_message("user", "Test message")
    chat._add_conversation_message("agent", "Test response")
    
    content = chat._format_conversation()
    print("Chat Interface Test: PASS")
    print("Content:")
    print(content)


if __name__ == "__main__":
    print("Testing TUI Components...")
    asyncio.run(test_agent_panel())
    asyncio.run(test_chat_interface())
    print("All tests passed!")
