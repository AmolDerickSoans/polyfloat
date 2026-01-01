import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from polycli.agents.trader import TraderAgent
from polycli.agents.creator import CreatorAgent

@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.filter_events_with_rag = AsyncMock(return_value=[(MagicMock(metadata={"id": "e1"}), 0.9)])
    executor.filter_markets = AsyncMock(return_value=[(MagicMock(metadata={"id": "m1", "question": "test?"}), 0.9)])
    executor.source_best_trade = AsyncMock(return_value="price:0.5, side:BUY")
    executor.source_best_market_to_create = AsyncMock(return_value="New Market Idea")
    return executor

@pytest.fixture
def trader(mock_executor):
    with patch("polycli.agents.trader.TraderAgent._init_llm"):
        agent = TraderAgent(executor=mock_executor)
        agent.provider = MagicMock()
        return agent

@pytest.fixture
def creator(mock_executor):
    with patch("polycli.agents.creator.CreatorAgent._init_llm"):
        agent = CreatorAgent(executor=mock_executor)
        agent.provider = MagicMock()
        return agent

@pytest.mark.asyncio
async def test_trader_one_best_trade(trader):
    trader.provider.get_events = AsyncMock(return_value=[MagicMock()])
    trader.provider.get_markets = AsyncMock(return_value=[MagicMock()])
    
    result = await trader.one_best_trade()
    assert result["success"] == True
    assert "price:0.5" in result["trade_plan"]

@pytest.mark.asyncio
async def test_creator_one_best_market(creator):
    # Mock provider name to be Polymarket
    creator.provider.__class__.__name__ = "PolyProvider"
    creator.provider.get_events = AsyncMock(return_value=[MagicMock()])
    creator.provider.get_markets = AsyncMock(return_value=[MagicMock()])
    
    result = await creator.one_best_market()
    assert result["success"] == True
    assert "New Market Idea" in result["market_proposal"]

@pytest.mark.asyncio
async def test_creator_disabled_for_kalshi(creator):
    # Mock provider name to be Kalshi
    creator.provider.__class__.__name__ = "KalshiProvider"
    
    result = await creator.one_best_market()
    assert result["success"] == False
    assert "not supported" in result["error"]
