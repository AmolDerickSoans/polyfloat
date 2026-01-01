"""Tests for Phase 1: Agents (Supervisor, Market Observer, Alert Manager)"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from polycli.agents.base import BaseAgent
from polycli.agents import SupervisorAgent
from polycli.agents import MarketObserverAgent
from polycli.agents import AlertManagerAgent
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.agents.state import SupervisorState


@pytest.fixture
async def agent_stores():
    """Create storage instances for testing"""
    redis = RedisStore(prefix="test:agents:")
    sqlite = SQLiteStore(":memory:")
    yield redis, sqlite
    await redis.close()
    await sqlite.close()


class TestSupervisorAgent:
    """Test Supervisor Agent functionality"""
    
    @pytest.mark.asyncio
    async def test_supervisor_initialization(self, agent_stores):
        """Test supervisor agent initialization"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        assert supervisor.agent_id == "supervisor"
        assert len(supervisor.active_agents) == 0
        assert len(supervisor.pending_tasks) == 0
        assert len(supervisor.task_assignments) == 0
        assert len(supervisor.agent_health) == 0
    
    @pytest.mark.asyncio
    async def test_register_agent(self, agent_stores):
        """Test registering an agent"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await supervisor.create_task(
            task_type="REGISTER_AGENT",
            description="Register market_observer agent",
            inputs={
                "agent_id": "market_observer",
                "agent_type": "MarketObserverAgent"
            }
        )
        
        result = await supervisor.execute_task(task)
        
        assert result["success"] == True
        assert "market_observer" in supervisor.active_agents
        assert "market_observer" in supervisor.agent_health
        assert supervisor.agent_health["market_observer"]["status"] == "RUNNING"
    
    @pytest.mark.asyncio
    async def test_unregister_agent(self, agent_stores):
        """Test unregistering an agent"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # First register
        register_task = await supervisor.create_task(
            task_type="REGISTER_AGENT",
            description="Register agent",
            inputs={"agent_id": "test_agent", "agent_type": "Test"}
        )
        await supervisor.execute_task(register_task)
        
        assert "test_agent" in supervisor.active_agents
        
        # Then unregister
        unregister_task = await supervisor.create_task(
            task_type="UNREGISTER_AGENT",
            description="Unregister agent",
            inputs={"agent_id": "test_agent"}
        )
        result = await supervisor.execute_task(unregister_task)
        
        assert result["success"] == True
        assert "test_agent" not in supervisor.active_agents
        assert "test_agent" not in supervisor.agent_health
    
    @pytest.mark.asyncio
    async def test_check_agent_health(self, agent_stores):
        """Test checking agent health"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await supervisor.create_task(
            task_type="CHECK_HEALTH",
            description="Check agent health",
            inputs={"agent_id": "market_observer"}
        )
        
        result = await supervisor.execute_task(task)
        
        assert result["success"] == False  # Agent not registered
        assert "not registered" in result["error"]
    
    @pytest.mark.asyncio
    async def test_restart_agent(self, agent_stores):
        """Test restarting an agent"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await supervisor.create_task(
            task_type="RESTART_AGENT",
            description="Restart agent",
            inputs={"agent_id": "test_agent"}
        )
        
        result = await supervisor.execute_task(task)
        
        assert result["success"] == True
        assert result["agent_id"] == "test_agent"
    
    @pytest.mark.asyncio
    async def test_determine_target_agent(self, agent_stores):
        """Test task routing logic"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Register some agents
        supervisor.active_agents = ["market_observer", "alert_manager", "arb_scout"]
        supervisor.agent_health = {
            "market_observer": {"status": "RUNNING"},
            "alert_manager": {"status": "RUNNING"},
            "arb_scout": {"status": "RUNNING"}
        }
        
        # Test routing
        task1 = await supervisor.create_task(
            task_type="SCAN_MARKETS",
            description="Scan markets",
            inputs={}
        )
        target1 = await supervisor._determine_target_agent(task1)
        assert target1 == "market_observer"
        
        task2 = await supervisor.create_task(
            task_type="DETECT_ARB",
            description="Detect arbitrage",
            inputs={}
        )
        target2 = await supervisor._determine_target_agent(task2)
        assert target2 == "arb_scout"
        
        task3 = await supervisor.create_task(
            task_type="CHECK_ALERTS",
            description="Check alerts",
            inputs={}
        )
        target3 = await supervisor._determine_target_agent(task3)
        assert target3 == "alert_manager"
    
    @pytest.mark.asyncio
    async def test_send_heartbeat(self, agent_stores):
        """Test sending supervisor heartbeat"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        supervisor.active_agents = ["agent1", "agent2"]
        supervisor.pending_tasks = [
            await supervisor.create_task("TEST", "Task 1", {}),
            await supervisor.create_task("TEST", "Task 2", {})
        ]
        
        await supervisor.send_heartbeat()
        
        health = await redis.hgetall("agent:health:supervisor")
        assert health is not None
        assert health["status"] == "RUNNING"
        assert health["active_agents"] == 2
        assert health["pending_tasks"] == 2
    
    @pytest.mark.asyncio
    async def test_get_summary(self, agent_stores):
        """Test getting supervisor summary"""
        redis, sqlite = agent_stores
        supervisor = SupervisorAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        supervisor.active_agents = ["agent1", "agent2"]
        supervisor.task_assignments = {
            "agent1": ["task1", "task2"],
            "agent2": ["task3"]
        }
        
        summary = await supervisor.get_summary()
        
        assert summary["agent_id"] == "supervisor"
        assert summary["status"] == "RUNNING"
        assert len(summary["active_agents"]) == 2
        assert summary["pending_tasks"] == 0


class TestAlertManagerAgent:
    """Test Alert Manager Agent functionality"""
    
    @pytest.mark.asyncio
    async def test_alert_manager_initialization(self, agent_stores):
        """Test alert manager initialization"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        assert alert_mgr.agent_id == "alert_manager"
        assert len(alert_mgr.alerts) == 0
        assert len(alert_mgr.notification_channels) > 0
        assert "price_change" in alert_mgr.alert_rules
        assert "volume_spike" in alert_mgr.alert_rules
    
    @pytest.mark.asyncio
    async def test_create_alert(self, agent_stores):
        """Test creating an alert"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await alert_mgr.create_task(
            task_type="CREATE_ALERT",
            description="Create test alert",
            inputs={
                "severity": "HIGH",
                "category": "test",
                "message": "Test alert",
                "source": "test_suite"
            }
        )
        
        result = await alert_mgr.execute_task(task)
        
        assert result["success"] == True
        assert "alert_id" in result
        assert len(alert_mgr.alerts) == 1
        assert alert_mgr.alerts[0]["severity"] == "HIGH"
        assert alert_mgr.alerts[0]["message"] == "Test alert"
    
    @pytest.mark.asyncio
    async def test_check_thresholds(self, agent_stores):
        """Test threshold checking"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Test price change threshold
        task = await alert_mgr.create_task(
            task_type="CHECK_THRESHOLDS",
            description="Check thresholds",
            inputs={
                "metrics": {
                    "price_change": 0.15,  # Above default 0.10 threshold
                    "volume_change": 1.0,
                    "arb_edge": 0.01,
                    "risk_used": 0.8
                }
            }
        )
        
        result = await alert_mgr.execute_task(task)
        
        assert result["success"] == True
        assert result["count"] >= 1  # At least one alert triggered
        assert len(alert_mgr.alerts) >= 1
    
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, agent_stores):
        """Test acknowledging an alert"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Create an alert first
        create_task = await alert_mgr.create_task(
            task_type="CREATE_ALERT",
            description="Create alert",
            inputs={
                "severity": "MEDIUM",
                "category": "test",
                "message": "Test alert"
            }
        )
        create_result = await alert_mgr.execute_task(create_task)
        alert_id = create_result["alert_id"]
        
        # Now acknowledge it
        ack_task = await alert_mgr.create_task(
            task_type="ACKNOWLEDGE_ALERT",
            description="Acknowledge alert",
            inputs={"alert_id": alert_id}
        )
        result = await alert_mgr.execute_task(ack_task)
        
        assert result["success"] == True
        # Find the alert
        alert = next((a for a in alert_mgr.alerts if a["alert_id"] == alert_id), None)
        assert alert is not None
        assert alert["acknowledged"] == True
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self, agent_stores):
        """Test resolving an alert"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Create an alert
        create_task = await alert_mgr.create_task(
            task_type="CREATE_ALERT",
            description="Create alert",
            inputs={
                "severity": "MEDIUM",
                "category": "test",
                "message": "Test alert"
            }
        )
        create_result = await alert_mgr.execute_task(create_task)
        alert_id = create_result["alert_id"]
        
        # Resolve it
        resolve_task = await alert_mgr.create_task(
            task_type="RESOLVE_ALERT",
            description="Resolve alert",
            inputs={"alert_id": alert_id}
        )
        result = await alert_mgr.execute_task(resolve_task)
        
        assert result["success"] == True
        alert = next((a for a in alert_mgr.alerts if a["alert_id"] == alert_id), None)
        assert alert is not None
        assert alert["resolved"] == True
        assert alert["acknowledged"] == True
    
    @pytest.mark.asyncio
    async def test_update_alert_rule(self, agent_stores):
        """Test updating an alert rule"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await alert_mgr.create_task(
            task_type="UPDATE_RULE",
            description="Update alert rule",
            inputs={
                "rule_name": "price_change",
                "threshold": 0.20,
                "enabled": True
            }
        )
        
        result = await alert_mgr.execute_task(task)
        
        assert result["success"] == True
        assert alert_mgr.alert_rules["price_change"]["threshold"] == 0.20
    
    @pytest.mark.asyncio
    async def test_get_alerts(self, agent_stores):
        """Test retrieving alerts with filters"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Create some alerts
        for i in range(3):
            task = await alert_mgr.create_task(
                task_type="CREATE_ALERT",
                description=f"Create alert {i}",
                inputs={
                    "severity": "HIGH" if i % 2 == 0 else "LOW",
                    "category": "test",
                    "message": f"Alert {i}"
                }
            )
            await alert_mgr.execute_task(task)
        
        # Get all alerts
        get_all_task = await alert_mgr.create_task(
            task_type="GET_ALERTS",
            description="Get all alerts",
            inputs={}
        )
        result = await alert_mgr.execute_task(get_all_task)
        
        assert result["success"] == True
        assert result["count"] == 3
        
        # Get only HIGH severity alerts
        get_high_task = await alert_mgr.create_task(
            task_type="GET_ALERTS",
            description="Get HIGH alerts",
            inputs={"severity": "HIGH"}
        )
        result_high = await alert_mgr.execute_task(get_high_task)
        
        assert result_high["success"] == True
        assert result_high["count"] == 2
    
    @pytest.mark.asyncio
    async def test_add_notification_channel(self, agent_stores):
        """Test adding notification channel"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        task = await alert_mgr.create_task(
            task_type="ADD_CHANNEL",
            description="Add notification channel",
            inputs={"channel": "test_channel"}
        )
        
        result = await alert_mgr.execute_task(task)
        
        assert result["success"] == True
        assert "test_channel" in alert_mgr.notification_channels
    
    @pytest.mark.asyncio
    async def test_get_summary(self, agent_stores):
        """Test getting alert manager summary"""
        redis, sqlite = agent_stores
        alert_mgr = AlertManagerAgent(
            redis_store=redis,
            sqlite_store=sqlite
        )
        
        # Create some alerts
        for _ in range(5):
            task = await alert_mgr.create_task(
                task_type="CREATE_ALERT",
                description="Create alert",
                inputs={
                    "severity": "MEDIUM",
                    "category": "test",
                    "message": "Test alert"
                }
            )
            await alert_mgr.execute_task(task)
        
        summary = await alert_mgr.get_summary()
        
        assert summary["agent_id"] == "alert_manager"
        assert summary["total_alerts"] == 5
        assert summary["unresolved_count"] == 5
        assert summary["unacknowledged_count"] == 5
        assert summary["status"] == "RUNNING"


class TestMarketObserverAgent:
    """Test Market Observer Agent functionality"""
    
    @pytest.mark.asyncio
    async def test_market_observer_initialization(self, agent_stores):
        """Test market observer initialization"""
        redis, sqlite = agent_stores
        
        # Create mock providers
        poly_provider = Mock()
        kalshi_provider = Mock()
        
        observer = MarketObserverAgent(
            redis_store=redis,
            sqlite_store=sqlite,
            poly_provider=poly_provider,
            kalshi_provider=kalshi_provider
        )
        
        assert observer.agent_id == "market_observer"
        assert observer.poly == poly_provider
        assert observer.kalshi == kalshi_provider
        assert len(observer.watchlist) == 0
        assert len(observer.subscribed_markets) == 0
    
    @pytest.mark.asyncio
    async def test_add_to_watchlist(self, agent_stores):
        """Test adding market to watchlist"""
        redis, sqlite = agent_stores
        poly_provider = Mock()
        kalshi_provider = Mock()
        
        observer = MarketObserverAgent(
            redis_store=redis,
            sqlite_store=sqlite,
            poly_provider=poly_provider,
            kalshi_provider=kalshi_provider
        )
        
        task = await observer.create_task(
            task_type="ADD_WATCHLIST",
            description="Add market to watchlist",
            inputs={"market_id": "market_123"}
        )
        
        result = await observer.execute_task(task)
        
        assert result["success"] == True
        assert "market_123" in observer.watchlist
    
    @pytest.mark.asyncio
    async def test_remove_from_watchlist(self, agent_stores):
        """Test removing market from watchlist"""
        redis, sqlite = agent_stores
        poly_provider = Mock()
        kalshi_provider = Mock()
        
        observer = MarketObserverAgent(
            redis_store=redis,
            sqlite_store=sqlite,
            poly_provider=poly_provider,
            kalshi_provider=kalshi_provider
        )
        
        # Add first
        add_task = await observer.create_task(
            task_type="ADD_WATCHLIST",
            description="Add market",
            inputs={"market_id": "market_456"}
        )
        await observer.execute_task(add_task)
        
        # Then remove
        remove_task = await observer.create_task(
            task_type="REMOVE_WATCHLIST",
            description="Remove market",
            inputs={"market_id": "market_456"}
        )
        result = await observer.execute_task(remove_task)
        
        assert result["success"] == True
        assert "market_456" not in observer.watchlist
    
    @pytest.mark.asyncio
    async def test_subscribe_to_market(self, agent_stores):
        """Test subscribing to market"""
        redis, sqlite = agent_stores
        poly_provider = Mock()
        kalshi_provider = Mock()
        
        observer = MarketObserverAgent(
            redis_store=redis,
            sqlite_store=sqlite,
            poly_provider=poly_provider,
            kalshi_provider=kalshi_provider
        )
        
        task = await observer.create_task(
            task_type="SUBSCRIBE_MARKET",
            description="Subscribe to market",
            inputs={
                "market_id": "market_789",
                "provider": "polymarket"
            }
        )
        
        result = await observer.execute_task(task)
        
        assert result["success"] == True
        assert result["subscribed"] == True
        assert "market_789" in observer.subscribed_markets
