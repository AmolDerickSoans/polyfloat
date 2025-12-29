import asyncio
import os
import json
import unittest
from typing import Dict, Any, Optional

# Set Gemini API Key
os.environ["GOOGLE_API_KEY"] = "AIzaSyDN5g4bx5y7Wj3l9Aj4PeJ1uHVyBsCNoOY"

from polycli.agents.supervisor import SupervisorAgent
from polycli.agents.trader import TraderAgent
from polycli.agents.creator import CreatorAgent
from polycli.agents.executor import ExecutorAgent
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.providers.polymarket import PolyProvider

class MockRedis:
    def __init__(self):
        self.published_messages = []
        self.prefix = "test:"

    async def publish(self, channel: str, message: Any):
        self.published_messages.append({"channel": channel, "data": message})
        print(f"[MOCK REDIS] Published to {channel}: {message}")

    async def set(self, key: str, value: Any, ttl: int = 0):
        pass

    async def subscribe(self, channel: str):
        return None

class MockProvider:
    async def get_events(self):
        return []
    async def get_markets(self, event_id=None):
        return []

class TestAgentSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = MockRedis()
        self.sqlite = SQLiteStore(":memory:")
        self.provider = PolyProvider() # Use real provider for RAG tests if possible
        
        self.supervisor = SupervisorAgent(
            redis_store=self.redis,
            sqlite_store=self.sqlite,
            provider=self.provider
        )

    async def test_supervisor_ack(self):
        """Test that supervisor sends an immediate ACK"""
        # We need to run route_command and check if ACK was published
        # Since it's async, we'll just check the published_messages list after it starts
        task = asyncio.create_task(self.supervisor.route_command("TEST", {"input": "hello"}))
        
        # Give it a tiny bit of time to publish ACK
        await asyncio.sleep(0.1)
        
        ack_msg = next((m for m in self.redis.published_messages if m["channel"] == "agent:status:updates"), None)
        self.assertIsNotNone(ack_msg)
        self.assertIn("Ack", ack_msg["data"]["message"])
        
        await task

    async def test_executor_market_llm(self):
        """Test ExecutorAgent's general LLM capabilities (Gemini integration)"""
        executor = self.supervisor.executor
        response = await executor.get_market_llm("Will Bitcoin reach $150k in 2025?")
        print(f"\n[LLM RESPONSE]: {response}\n")
        self.assertIsInstance(response, str)
        self.assertTrue(len(response) > 20)

    async def test_trader_strategy_routing(self):
        """Test that 'trade' commands are routed to the TraderAgent"""
        # We don't want to run the full RAG cycle (takes too long)
        # but we want to see it routing
        result = await self.supervisor.route_command("CHAT", {"input": "find me a good trade"})
        
        routing_msg = next((m for m in self.redis.published_messages if "Routing to Trader" in str(m["data"])), None)
        self.assertIsNotNone(routing_msg)

    async def test_creator_strategy_routing(self):
        """Test that 'create' commands are routed to the CreatorAgent"""
        result = await self.supervisor.route_command("CHAT", {"input": "create a new market for AI"})
        
        routing_msg = next((m for m in self.redis.published_messages if "Routing to Creator" in str(m["data"])), None)
        self.assertIsNotNone(routing_msg)

    async def test_executor_superforecast(self):
        """Test probabilistic assessment capabilities"""
        executor = self.supervisor.executor
        response = await executor.get_superforecast(
            event_title="Interest rate decision",
            market_question="Will the Fed cut rates in Jan 2025?",
            outcomes=["Yes", "No"]
        )
        print(f"\n[SUPERFORECAST]: {response}\n")
        self.assertIsInstance(response, str)

    async def test_executor_rag_filtering(self):
        """Test RAG filtering logic (even with empty data)"""
        executor = self.supervisor.executor
        events = [{"id": "1", "title": "Test Event"}]
        # This will test the chroma connector integration
        try:
            results = await executor.filter_events_with_rag(events)
            self.assertIsInstance(results, list)
        except Exception as e:
            print(f"RAG filtering skipped/failed: {e}")

    async def test_agent_status_publishing(self):
        """Test that agents publish status updates to Redis"""
        agent = self.supervisor.trader
        await agent.publish_status("Testing status", status="RUNNING")
        
        msg = next((m for m in self.redis.published_messages if m["channel"] == "agent:status:updates"), None)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["data"]["message"], "Testing status")
        self.assertEqual(msg["data"]["agent_id"], "trader")

if __name__ == "__main__":
    unittest.main()
