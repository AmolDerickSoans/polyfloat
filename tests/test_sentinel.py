"""
Sentinel Agent unit tests.

Tests the core trigger evaluation logic and proposal generation
without any external dependencies.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from polycli.sentinel.models import (
    TriggerType,
    TriggerCondition,
    WatchedMarket,
    SentinelConfig,
    MarketSnapshot,
    SentinelProposal,
    ProposalStatus,
    SentinelRiskSnapshot,
    RiskStatus,
)
from polycli.sentinel.triggers import (
    TriggerEvaluator,
    MarketState,
    PriceHistory,
)


class TestTriggerCondition:
    """Test TriggerCondition model."""
    
    def test_describe_price_below(self):
        trigger = TriggerCondition(
            trigger_type=TriggerType.PRICE_BELOW,
            threshold=Decimal("0.45"),
            suggested_side="BUY",
        )
        assert trigger.describe() == "Price dropped below $0.45"
    
    def test_describe_price_above(self):
        trigger = TriggerCondition(
            trigger_type=TriggerType.PRICE_ABOVE,
            threshold=Decimal("0.75"),
            suggested_side="SELL",
        )
        assert trigger.describe() == "Price rose above $0.75"
    
    def test_describe_spread_above(self):
        trigger = TriggerCondition(
            trigger_type=TriggerType.SPREAD_ABOVE,
            threshold=Decimal("0.05"),
            suggested_side="SELL",
        )
        assert trigger.describe() == "Spread widened above $0.05"


class TestWatchedMarket:
    """Test WatchedMarket model."""
    
    def test_create_watched_market(self):
        triggers = [
            TriggerCondition(
                trigger_type=TriggerType.PRICE_BELOW,
                threshold=Decimal("0.45"),
                suggested_side="BUY",
            ),
        ]
        watched = WatchedMarket.create(
            market_id="test-market-1",
            provider="polymarket",
            triggers=triggers,
            cooldown_seconds=300,
        )
        
        assert watched.market_id == "test-market-1"
        assert watched.provider == "polymarket"
        assert len(watched.triggers) == 1
        assert watched.cooldown_seconds == 300


class TestSentinelConfig:
    """Test SentinelConfig model."""
    
    def test_create_config(self):
        triggers = [
            TriggerCondition(
                trigger_type=TriggerType.PRICE_BELOW,
                threshold=Decimal("0.45"),
                suggested_side="BUY",
            ),
        ]
        watched = WatchedMarket.create(
            market_id="test-market-1",
            provider="polymarket",
            triggers=triggers,
        )
        config = SentinelConfig.create(
            watched_markets=[watched],
            max_proposals_per_hour=5,
        )
        
        assert len(config.watched_markets) == 1
        assert config.max_proposals_per_hour == 5
    
    def test_to_dict(self):
        triggers = [
            TriggerCondition(
                trigger_type=TriggerType.PRICE_BELOW,
                threshold=Decimal("0.45"),
                suggested_side="BUY",
            ),
        ]
        watched = WatchedMarket.create(
            market_id="test-market-1",
            provider="polymarket",
            triggers=triggers,
        )
        config = SentinelConfig.create(watched_markets=[watched])
        
        d = config.to_dict()
        assert "watched_markets" in d
        assert len(d["watched_markets"]) == 1


class TestSentinelRiskSnapshot:
    """Test SentinelRiskSnapshot model."""
    
    def test_compute_summary_green(self):
        risk = SentinelRiskSnapshot(
            status=RiskStatus.GREEN,
            circuit_breaker_active=False,
            remaining_position_budget_usd=Decimal("80"),
            remaining_loss_budget_usd=Decimal("40"),
            risk_score=20.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("50"),
        )
        summary = risk.compute_summary()
        assert "GREEN" in summary
        assert "20%" in summary  # 80 remaining of 100 = 20% used
    
    def test_compute_summary_red(self):
        risk = SentinelRiskSnapshot(
            status=RiskStatus.RED,
            circuit_breaker_active=False,
            remaining_position_budget_usd=Decimal("0"),
            remaining_loss_budget_usd=Decimal("0"),
            risk_score=100.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("0"),
        )
        summary = risk.compute_summary()
        assert "BLOCKED" in summary
        assert "RED" in summary
    
    def test_should_block_proposal(self):
        risk_red = SentinelRiskSnapshot(
            status=RiskStatus.RED,
            circuit_breaker_active=False,
            remaining_position_budget_usd=Decimal("0"),
            remaining_loss_budget_usd=Decimal("0"),
            risk_score=100.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("0"),
        )
        assert risk_red.should_block_proposal() == "Risk status RED"
        
        risk_breaker = SentinelRiskSnapshot(
            status=RiskStatus.GREEN,
            circuit_breaker_active=True,
            remaining_position_budget_usd=Decimal("100"),
            remaining_loss_budget_usd=Decimal("50"),
            risk_score=0.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("50"),
        )
        assert risk_breaker.should_block_proposal() == "Circuit breaker active"
        
        risk_ok = SentinelRiskSnapshot(
            status=RiskStatus.GREEN,
            circuit_breaker_active=False,
            remaining_position_budget_usd=Decimal("100"),
            remaining_loss_budget_usd=Decimal("50"),
            risk_score=0.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("50"),
        )
        assert risk_ok.should_block_proposal() is None


class TestSentinelProposal:
    """Test SentinelProposal model."""
    
    def test_is_valid(self):
        proposal = SentinelProposal(
            trigger_type="price_below",
            trigger_threshold=Decimal("0.45"),
            trigger_description="Price dropped below $0.45",
            suggested_side="BUY",
            expires_at=datetime.utcnow() + timedelta(minutes=2),
        )
        assert proposal.is_valid()
        
        proposal.mark_approved()
        assert not proposal.is_valid()
    
    def test_expired_not_valid(self):
        proposal = SentinelProposal(
            trigger_type="price_below",
            trigger_threshold=Decimal("0.45"),
            trigger_description="Price dropped below $0.45",
            suggested_side="BUY",
            expires_at=datetime.utcnow() - timedelta(seconds=1),  # Already expired
        )
        assert not proposal.is_valid()


class TestPriceHistory:
    """Test PriceHistory tracking."""
    
    def test_add_and_retrieve(self):
        history = PriceHistory()
        now = datetime.utcnow()
        
        history.add_price(now - timedelta(seconds=30), Decimal("0.50"))
        history.add_price(now - timedelta(seconds=20), Decimal("0.52"))
        history.add_price(now - timedelta(seconds=10), Decimal("0.55"))
        history.add_price(now, Decimal("0.58"))
        
        # Price change over last 60 seconds
        change = history.price_change_pct(60)
        expected = (Decimal("0.58") - Decimal("0.50")) / Decimal("0.50")
        assert abs(change - expected) < Decimal("0.01")
    
    def test_volume_since(self):
        history = PriceHistory()
        now = datetime.utcnow()
        
        history.add_volume(now - timedelta(seconds=30), Decimal("100"))
        history.add_volume(now - timedelta(seconds=20), Decimal("150"))
        history.add_volume(now - timedelta(seconds=10), Decimal("200"))
        
        total = history.volume_since(60)
        assert total == Decimal("450")


class TestTriggerEvaluator:
    """Test trigger evaluation logic."""
    
    def test_price_below_triggers(self):
        evaluator = TriggerEvaluator()
        
        trigger = TriggerCondition(
            trigger_type=TriggerType.PRICE_BELOW,
            threshold=Decimal("0.45"),
            suggested_side="BUY",
            debounce_seconds=60,
        )
        
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            best_bid=Decimal("0.42"),  # Below threshold
            best_ask=Decimal("0.44"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            timestamp=datetime.utcnow(),
        )
        
        fires, value = evaluator.evaluate(trigger, state)
        assert fires
        assert value == Decimal("0.42")
    
    def test_price_below_does_not_trigger_when_above(self):
        evaluator = TriggerEvaluator()
        
        trigger = TriggerCondition(
            trigger_type=TriggerType.PRICE_BELOW,
            threshold=Decimal("0.45"),
            suggested_side="BUY",
            debounce_seconds=60,
        )
        
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            best_bid=Decimal("0.50"),  # Above threshold
            best_ask=Decimal("0.52"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            timestamp=datetime.utcnow(),
        )
        
        fires, value = evaluator.evaluate(trigger, state)
        assert not fires
    
    def test_debounce_prevents_repeated_fires(self):
        evaluator = TriggerEvaluator()
        
        trigger = TriggerCondition(
            trigger_type=TriggerType.PRICE_BELOW,
            threshold=Decimal("0.45"),
            suggested_side="BUY",
            debounce_seconds=60,
        )
        
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            best_bid=Decimal("0.42"),
            best_ask=Decimal("0.44"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            timestamp=datetime.utcnow(),
        )
        
        # First evaluation should fire
        fires1, _ = evaluator.evaluate(trigger, state)
        assert fires1
        
        # Record the fire
        evaluator.record_fire("test-1", trigger, Decimal("0.42"))
        
        # Second evaluation should be debounced
        fires2, _ = evaluator.evaluate(trigger, state)
        assert not fires2
    
    def test_spread_above_triggers(self):
        evaluator = TriggerEvaluator()
        
        trigger = TriggerCondition(
            trigger_type=TriggerType.SPREAD_ABOVE,
            threshold=Decimal("0.03"),
            suggested_side="SELL",
            debounce_seconds=60,
        )
        
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.50"),
            spread=Decimal("0.05"),  # Above threshold
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            timestamp=datetime.utcnow(),
        )
        
        fires, value = evaluator.evaluate(trigger, state)
        assert fires
        assert value == Decimal("0.05")
    
    def test_market_reopen_triggers(self):
        evaluator = TriggerEvaluator()
        
        trigger = TriggerCondition(
            trigger_type=TriggerType.MARKET_REOPEN,
            threshold=Decimal("0"),  # Not used for this trigger
            suggested_side="BUY",
            debounce_seconds=600,
        )
        
        # Market was halted, now active
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            prev_status="halted",  # Was halted
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.47"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            timestamp=datetime.utcnow(),
        )
        
        fires, _ = evaluator.evaluate(trigger, state)
        assert fires
    
    def test_imbalance_buy_triggers(self):
        evaluator = TriggerEvaluator()
        
        trigger = TriggerCondition(
            trigger_type=TriggerType.IMBALANCE_BUY,
            threshold=Decimal("0.5"),
            suggested_side="BUY",
            debounce_seconds=60,
        )
        
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.47"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("15000"),
            ask_depth_usd=Decimal("5000"),
            imbalance=0.7,  # Strong buy pressure
            timestamp=datetime.utcnow(),
        )
        
        fires, value = evaluator.evaluate(trigger, state)
        assert fires
        assert value == Decimal("0.7")


class TestMarketState:
    """Test MarketState model."""
    
    def test_to_snapshot(self):
        state = MarketState(
            market_id="test-1",
            provider="polymarket",
            question="Test market?",
            status="active",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.47"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            timestamp=datetime.utcnow(),
        )
        
        snapshot = state.to_snapshot()
        assert isinstance(snapshot, MarketSnapshot)
        assert snapshot.market_id == "test-1"
        assert snapshot.best_bid == Decimal("0.45")


# =============================================================================
# Integration-style tests (still unit tests, no external deps)
# =============================================================================

class TestSentinelIntegration:
    """Test Sentinel components working together."""
    
    def test_full_proposal_lifecycle(self):
        """Test creating a proposal and going through its lifecycle."""
        # Create risk snapshot
        risk = SentinelRiskSnapshot(
            status=RiskStatus.GREEN,
            circuit_breaker_active=False,
            remaining_position_budget_usd=Decimal("80"),
            remaining_loss_budget_usd=Decimal("40"),
            risk_score=20.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("50"),
        )
        
        # Create market snapshot
        market = MarketSnapshot(
            market_id="test-1",
            provider="polymarket",
            question="Will X happen?",
            best_bid=Decimal("0.42"),
            best_ask=Decimal("0.44"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            captured_at=datetime.utcnow(),
        )
        
        # Create proposal
        proposal = SentinelProposal(
            trigger_type="price_below",
            trigger_threshold=Decimal("0.45"),
            trigger_description="Price dropped below $0.45",
            market_snapshot=market,
            risk_snapshot=risk,
            risk_summary=risk.compute_summary(),
            suggested_side="BUY",
            expires_at=datetime.utcnow() + timedelta(minutes=2),
        )
        
        # Check initial state
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.is_valid()
        
        # User approves
        proposal.mark_approved()
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.user_decision_at is not None
        assert not proposal.is_valid()  # No longer actionable
    
    def test_proposal_display_format(self):
        """Test that proposal display format is generated correctly."""
        risk = SentinelRiskSnapshot(
            status=RiskStatus.GREEN,
            circuit_breaker_active=False,
            remaining_position_budget_usd=Decimal("80"),
            remaining_loss_budget_usd=Decimal("40"),
            risk_score=20.0,
            total_portfolio_value=Decimal("100"),
            available_balance=Decimal("50"),
        )
        
        market = MarketSnapshot(
            market_id="test-1",
            provider="polymarket",
            question="Will candidate X win?",
            best_bid=Decimal("0.42"),
            best_ask=Decimal("0.44"),
            spread=Decimal("0.02"),
            bid_depth_usd=Decimal("10000"),
            ask_depth_usd=Decimal("8000"),
            imbalance=0.1,
            captured_at=datetime.utcnow(),
        )
        
        proposal = SentinelProposal(
            trigger_type="price_below",
            trigger_threshold=Decimal("0.45"),
            trigger_description="Price dropped below $0.45",
            market_snapshot=market,
            risk_snapshot=risk,
            risk_summary=risk.compute_summary(),
            suggested_side="BUY",
            expires_at=datetime.utcnow() + timedelta(minutes=2),
        )
        
        display = proposal.format_display()
        
        # Check key elements are present
        assert "SENTINEL PROPOSAL" in display
        assert "Price dropped below $0.45" in display
        assert "BUY" in display
        assert "If you agree" in display
        assert "You decide the size" in display


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
