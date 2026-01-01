import pytest
import os
import sqlite3
import json
from decimal import Decimal
from datetime import datetime, timedelta
from polycli.risk import RiskGuard, RiskConfig
from polycli.risk.models import RiskViolationType, TradeAuditLog
from polycli.risk.store import RiskAuditStore

@pytest.fixture
def risk_config():
    return RiskConfig(
        max_position_size_usd=Decimal("100"),
        max_position_size_pct=Decimal("0.10"),
        daily_loss_limit_usd=Decimal("50"),
        trading_enabled=True,
        circuit_breaker_enabled=True,
        circuit_breaker_cooldown_minutes=60
    )

@pytest.fixture
async def mock_balance():
    async def _get_balance(provider):
        return {"balance": 500.0, "total_value": 1000.0}
    return _get_balance

@pytest.fixture
async def mock_positions():
    async def _get_positions(provider):
        return []
    return _get_positions

@pytest.fixture
async def mock_price():
    async def _get_price(token_id, side):
        return 0.50
    return _get_price

class TestRiskGuard:
    
    @pytest.mark.asyncio
    async def test_rejects_oversized_position_absolute(self, risk_config, mock_balance, mock_positions, mock_price, tmp_path):
        # Use a temporary DB for tests
        store = RiskAuditStore(db_path=tmp_path / "test_risk.db")
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=mock_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        # Test absolute dollar limit
        result = await guard.check_trade(
            token_id="test_oversize_abs",
            side="BUY",
            amount=200.0,  # Exceeds max of 100
            provider="polymarket"
        )
        
        assert not result.approved
        assert any(v.violation_type == RiskViolationType.POSITION_SIZE_EXCEEDED for v in result.violations)
        assert "exceeds max $100.00" in result.violations[0].message

    @pytest.mark.asyncio
    async def test_rejects_oversized_position_pct(self, risk_config, mock_balance, mock_positions, mock_price, tmp_path):
        store = RiskAuditStore(db_path=tmp_path / "test_risk_pct.db")
        
        # Set a very low percentage limit for this test
        risk_config.max_position_size_pct = Decimal("0.05") # 5%
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=mock_balance, # Portfolio value is 1000
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        # 5% of 1000 is 50. Trying to buy 60.
        result = await guard.check_trade(
            token_id="test_oversize_pct",
            side="BUY",
            amount=60.0,
            provider="polymarket"
        )
        
        assert not result.approved
        assert any(v.violation_type == RiskViolationType.POSITION_SIZE_EXCEEDED for v in result.violations)

    @pytest.mark.asyncio
    async def test_approves_valid_trade(self, risk_config, mock_balance, mock_positions, mock_price, tmp_path):
        store = RiskAuditStore(db_path=tmp_path / "test_valid.db")
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=mock_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        result = await guard.check_trade(
            token_id="test_valid",
            side="BUY",
            amount=50.0,  # Within limits (under 100 and under 10% of 1000)
            provider="polymarket"
        )
        
        assert result.approved
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_trades(self, risk_config, mock_balance, mock_positions, mock_price, tmp_path):
        store = RiskAuditStore(db_path=tmp_path / "test_circuit.db")
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=mock_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        # Manually trigger breaker
        guard.trigger_circuit_breaker("Test Manual Trigger", 60)
        
        # Verify it's recorded
        assert store.is_circuit_breaker_active()
        
        # Attempt trade
        result = await guard.check_trade(
            token_id="test_breaker",
            side="BUY",
            amount=10.0,
            provider="polymarket"
        )
        
        assert not result.approved
        assert any(v.violation_type == RiskViolationType.CIRCUIT_BREAKER_ACTIVE for v in result.violations)

    @pytest.mark.asyncio
    async def test_insufficient_balance(self, risk_config, mock_positions, mock_price, tmp_path):
        # Custom balance for this test
        async def low_balance(provider):
            return {"balance": 20.0, "total_value": 1000.0}
            
        store = RiskAuditStore(db_path=tmp_path / "test_balance.db")
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=low_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        result = await guard.check_trade(
            token_id="test_balance",
            side="BUY",
            amount=50.0, # More than available 20
            provider="polymarket"
        )
        
        assert not result.approved
        assert any(v.violation_type == RiskViolationType.INSUFFICIENT_BALANCE for v in result.violations)

    @pytest.mark.asyncio
    async def test_audit_logging(self, risk_config, mock_balance, mock_positions, mock_price, tmp_path):
        db_path = tmp_path / "test_audit.db"
        store = RiskAuditStore(db_path=db_path)
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=mock_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        await guard.check_trade(
            token_id="test_audit",
            side="BUY",
            amount=50.0,
            provider="polymarket"
        )
        
        # Verify log exists
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT * FROM trade_audit_logs").fetchall()
            assert len(rows) == 1
            assert rows[0][2] == "test_audit" # token_id
            assert rows[0][8] == 1 # approved

    @pytest.mark.asyncio
    async def test_trading_disabled_global(self, risk_config, mock_balance, mock_positions, mock_price, tmp_path):
        store = RiskAuditStore(db_path=tmp_path / "test_disabled.db")
        risk_config.trading_enabled = False
        
        guard = RiskGuard(
            config=risk_config,
            store=store,
            get_balance_fn=mock_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price
        )
        
        result = await guard.check_trade(
            token_id="test_disabled",
            side="BUY",
            amount=10.0,
            provider="polymarket"
        )
        
        assert not result.approved
        assert "globally disabled" in result.violations[0].message
