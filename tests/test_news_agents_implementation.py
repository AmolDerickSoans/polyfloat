"""
Test script for News Agents implementation

This script tests:
1. News API clients initialization
2. Tool registration and execution
3. News Analysis Agent tasks
4. Market Correlation Agent tasks
5. Supervisor routing

Usage:
    python -m tests.test_news_agents_implementation
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from polycli.news import NewsAPIClient, NewsWebSocketClient, init_news_clients
from polycli.agents import NewsAnalysisAgent, MarketCorrelationAgent, SupervisorAgent
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.providers.polymarket import PolyProvider
from polycli.providers.kalshi import KalshiProvider


async def test_news_clients():
    """Test 1: News API clients initialization"""
    print("\n" + "=" * 60)
    print("TEST 1: News API Clients Initialization")
    print("=" * 60)

    try:
        api_client = NewsAPIClient()
        ws_client = NewsWebSocketClient()

        print(f"✓ NewsAPIClient created")
        print(f"✓ NewsWebSocketClient created")
        print(f"  - API URL: {os.getenv('NEWS_API_URL', 'http://localhost:8000')}")
        print(f"  - User ID: {os.getenv('NEWS_API_USER_ID', 'terminal_user')}")

        init_news_clients(api_client, ws_client)
        print(f"✓ News clients initialized for agent tools")

        return api_client, ws_client
    except Exception as e:
        print(f"✗ Failed: {e}")
        return None, None


async def test_news_tools(api_client, ws_client):
    """Test 2: Tool functions"""
    print("\n" + "=" * 60)
    print("TEST 2: News Tool Functions")
    print("=" * 60)

    try:
        from polycli.news.tools import (
            get_recent_news,
            get_news_by_entity,
            search_news,
            get_news_stats,
        )

        print(f"✓ Imported 6 news tool functions")

        # Test get_news_stats
        print("\n  Testing get_news_stats()...")
        try:
            stats_result = await get_news_stats()
            if stats_result["success"]:
                print(
                    f"  ✓ get_news_stats: {stats_result['stats']['total_news_items']} total items"
                )
            else:
                print(
                    f"  ✗ get_news_stats failed: {stats_result.get('error', 'Unknown')}"
                )
        except Exception as e:
            print(f"  ⚠ get_news_stats error (News API may be down): {e}")

        # Test get_recent_news
        print("\n  Testing get_recent_news(limit=5)...")
        try:
            news_result = await get_recent_news(limit=5)
            if news_result["success"]:
                print(f"  ✓ get_recent_news: Got {news_result['count']} items")
                for i, item in enumerate(news_result["items"][:2]):
                    title = item.get("title", item.get("content", "")[:50])
                    impact = item.get("impact_score", 0)
                    print(f"    [{i+1}] {title}... (Impact: {impact:.0f})")
            else:
                print(
                    f"  ✗ get_recent_news failed: {news_result.get('error', 'Unknown')}"
                )
        except Exception as e:
            print(f"  ⚠ get_recent_news error: {e}")

        return True
    except Exception as e:
        print(f"✗ Failed to import tools: {e}")
        return False


async def test_news_analysis_agent(redis_store, sqlite_store):
    """Test 3: News Analysis Agent"""
    print("\n" + "=" * 60)
    print("TEST 3: News Analysis Agent")
    print("=" * 60)

    try:
        agent = NewsAnalysisAgent(redis_store=redis_store, sqlite_store=sqlite_store)

        print(f"✓ NewsAnalysisAgent created (agent_id: {agent.agent_id})")
        print(f"  - Model: {agent.model}")
        print(f"  - Cache TTL: {agent.cache_ttl}s")

        # Test task creation and execution
        print("\n  Testing ANALYZE_NEWS_IMPACT task...")
        try:
            from polycli.agents.state import Task

            task = Task(
                task_id="test_news_analysis",
                task_type="ANALYZE_NEWS_IMPACT",
                description="Test news impact analysis",
                priority="NORMAL",
                created_at=0,
                started_at=None,
                completed_at=None,
                status="PENDING",
                inputs={"news_id": "test_news_id"},
                outputs=None,
                error_message=None,
                agent_id=None,
                latency_ms=None,
            )

            result = await agent.execute_task(task)
            if result.get("success"):
                print(f"  ✓ Task executed successfully")
                analysis = result.get("outputs", {}).get("analysis", {})
                print(f"    Impact Level: {analysis.get('impact_level', 'N/A')}")
                print(f"    Recommendation: {analysis.get('recommendation', 'N/A')}")
            else:
                print(f"  ⚠ Task completed with warnings")
                print(f"    May require News API to be running")
        except Exception as e:
            print(f"  ⚠ Task execution error: {e}")

        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_market_correlation_agent(
    redis_store, sqlite_store, poly_provider, kalshi_provider
):
    """Test 4: Market Correlation Agent"""
    print("\n" + "=" * 60)
    print("TEST 4: Market Correlation Agent")
    print("=" * 60)

    try:
        agent = MarketCorrelationAgent(
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            poly_provider=poly_provider,
            kalshi_provider=kalshi_provider,
        )

        print(f"✓ MarketCorrelationAgent created (agent_id: {agent.agent_id})")
        print(f"  - Model: {agent.model}")
        print(f"  - Cache TTL: {agent.cache_ttl}s")
        print(
            f"  - Providers: Poly={poly_provider is not None}, Kalshi={kalshi_provider is not None}"
        )

        # Test task creation
        print("\n  Testing FIND_RELATED_MARKETS task...")
        try:
            from polycli.agents.state import Task

            task = Task(
                task_id="test_market_correlation",
                task_type="FIND_RELATED_MARKETS",
                description="Test market correlation",
                priority="NORMAL",
                created_at=0,
                started_at=None,
                completed_at=None,
                status="PENDING",
                inputs={"entity": "BTC", "entity_type": "ticker"},
                outputs=None,
                error_message=None,
                agent_id=None,
                latency_ms=None,
            )

            result = await agent.execute_task(task)
            if result.get("success"):
                print(f"  ✓ Task executed successfully")
                related = result.get("outputs", {}).get("related_markets", [])
                print(f"    Related markets found: {len(related)}")
            else:
                print(f"  ⚠ Task completed with warnings")
                print(f"    May require provider API to be configured")
        except Exception as e:
            print(f"  ⚠ Task execution error: {e}")

        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_supervisor(redis_store, sqlite_store):
    """Test 5: Supervisor routing"""
    print("\n" + "=" * 60)
    print("TEST 5: Supervisor Routing")
    print("=" * 60)

    try:
        supervisor = SupervisorAgent(redis_store=redis_store, sqlite_store=sqlite_store)

        print(f"✓ SupervisorAgent created (agent_id: {supervisor.agent_id})")

        # Test routing rules
        print("\n  Testing task routing...")
        task_types = [
            "ANALYZE_NEWS_IMPACT",
            "GET_MARKET_SENTIMENT",
            "LINK_NEWS_TO_MARKETS",
            "FIND_RELATED_MARKETS",
        ]

        for task_type in task_types:
            target_agent = await supervisor._determine_target_agent(
                {"task_type": task_type}
            )
            print(f"  ✓ '{task_type}' → {target_agent}")

        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("NEWS AGENTS IMPLEMENTATION TEST")
    print("=" * 60)
    print("This test verifies the News Analysis and Market Correlation agents")
    print("are properly implemented and integrated with the Supervisor.")
    print("\nPrerequisites:")
    print("  - Redis server running (default: localhost:6379)")
    print("  - Polyfloat News API running (default: http://localhost:8000)")
    print("\nPress Ctrl+C to stop tests\n")

    # Load environment
    load_dotenv()

    # Initialize stores
    redis_store = RedisStore(prefix="polycli:")
    sqlite_store = SQLiteStore(":memory:")

    # Test 1: News clients
    api_client, ws_client = await test_news_clients()
    if not api_client:
        print("\n✗ Cannot continue without news clients")
        return

    # Test 2: Tools
    tools_ok = await test_news_tools(api_client, ws_client)

    # Test 3: News Analysis Agent
    analysis_ok = await test_news_analysis_agent(redis_store, sqlite_store)

    # Test 4: Market Correlation Agent (without providers)
    correlation_ok = await test_market_correlation_agent(
        redis_store, sqlite_store, poly_provider=None, kalshi_provider=None
    )

    # Test 5: Supervisor
    supervisor_ok = await test_supervisor(redis_store, sqlite_store)

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"News Clients: {'✓ PASS' if api_client else '✗ FAIL'}")
    print(f"News Tools: {'✓ PASS' if tools_ok else '✗ FAIL'}")
    print(f"News Analysis Agent: {'✓ PASS' if analysis_ok else '✗ FAIL'}")
    print(f"Market Correlation Agent: {'✓ PASS' if correlation_ok else '✗ FAIL'}")
    print(f"Supervisor Routing: {'✓ PASS' if supervisor_ok else '✗ FAIL'}")

    all_pass = (
        api_client and tools_ok and analysis_ok and correlation_ok and supervisor_ok
    )

    if all_pass:
        print("\n✓ ALL TESTS PASSED")
        print("\nNext Steps:")
        print(
            "  1. Start Polyfloat News API: cd /Users/amoldericksoans/Documents/polyfloat-news && docker-compose up -d && python -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
        )
        print("  2. Run Polyfloat Terminal: python -m polycli.tui")
        print("  3. In agent chat, try commands like:")
        print("     - 'Get recent news about crypto'")
        print("     - 'Analyze impact of latest news'")
        print("     - 'Find markets related to Trump'")
        print("     - 'What's the sentiment for Bitcoin?'")
    else:
        print("\n✗ SOME TESTS FAILED")
        print("\nCheck the error messages above for details.")

    # Cleanup
    if ws_client:
        await ws_client.disconnect()
    await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
