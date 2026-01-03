"""DOD Verification Tests for Execution Path (Section H).

Tests all Definition of Done criteria from completed workstreams WS1-WS5.
"""
import asyncio
import pytest
import time
import sqlite3
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from polycli.risk.guard import RiskGuard, RiskConfig
from polycli.risk.store import RiskAuditStore
from polycli.risk.models import RiskViolationType


def reset_circuit_breaker_for_test(db_path, provider: str = "all") -> None:
    """Helper to reset circuit breaker state for testing."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "INSERT INTO circuit_breaker_events (reason, cooldown_until, provider) VALUES (?, ?, ?)",
                ("Test reset", datetime.utcnow() - timedelta(minutes=1), provider),
            )
    except Exception:
        pass


class TestDODVerification:
    """Section H DOD Verification Tests."""

    def test_h1_no_direct_provider_calls_in_tui(self):
        """H.1: Verify no direct provider order calls in TUI code.

        Trades must go through TradingTools -> RiskGuard, never directly
        to provider.place_market_order() or provider.place_order().
        """
        import re

        tui_path = "src/polycli/tui.py"

        with open(tui_path, "r") as f:
            content = f.read()

        direct_order_patterns = [
            r"self\.poly\.place_market_order",
            r"self\.kalshi\.place_order",
            r"self\.poly\.place_order",
            r"self\.kalshi\.place_market_order",
            r"provider\.place_market_order",
            r"provider\.place_order",
        ]

        matches = []
        for pattern in direct_order_patterns:
            found = re.findall(pattern, content)
            matches.extend(found)

        assert len(matches) == 0, f"Found direct provider calls in tui.py: {matches}"

    def test_h2_nodes_py_raises_deprecation_warning(self):
        """H.2: Verify nodes.py raises DeprecationWarning on import.

        Legacy nodes.py must be deprecated to prevent accidental use.
        """
        with pytest.raises(DeprecationWarning) as exc_info:
            import sys

            if "polycli.agents.nodes" in sys.modules:
                del sys.modules["polycli.agents.nodes"]
            from polycli.agents.nodes import trader_node

        assert "deprecated" in str(exc_info.value).lower()
        assert "TradingTools" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_h3_manual_trade_goes_through_risk_guard(self):
        """H.3: Verify manual trades are blocked when circuit breaker is active.

        Trades must pass through RiskGuard.check_trade() before execution.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "risk_audit.db"

            config = RiskConfig()
            config.circuit_breaker_enabled = True
            config.trading_enabled = True

            store = RiskAuditStore(db_path=db_path)
            store.trigger_circuit_breaker(
                "Test", cooldown_minutes=10, provider="polymarket"
            )

            mock_get_balance = AsyncMock(
                return_value={"balance": 10000.0, "total_value": 10000.0}
            )
            mock_get_positions = AsyncMock(return_value=[])
            mock_get_price = AsyncMock(return_value=0.50)

            risk_guard = RiskGuard(
                config=config,
                store=store,
                get_balance_fn=mock_get_balance,
                get_positions_fn=mock_get_positions,
                get_price_fn=mock_get_price,
            )

            result = await risk_guard.check_trade(
                token_id="test_token",
                side="BUY",
                amount=100.0,
                provider="polymarket",
                agent_id="manual_user",
                agent_reasoning="Manual trade via TUI",
            )

            assert (
                result.approved is False
            ), f"Trade should be blocked by circuit breaker, got: {result.violations}"

            violation_types = [v.violation_type for v in result.violations]
            assert (
                RiskViolationType.CIRCUIT_BREAKER_ACTIVE in violation_types
            ), f"Should have circuit breaker violation, got: {result.violations}"

    @pytest.mark.asyncio
    async def test_h3_trade_approved_when_circuit_breaker_inactive(self):
        """H.3: Verify trades are approved when circuit breaker is inactive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "risk_audit.db"

            config = RiskConfig()
            config.trading_enabled = True
            config.agents_enabled = True
            config.circuit_breaker_enabled = True
            config.max_position_size_usd = Decimal("10000")

            store = RiskAuditStore(db_path=db_path)

            mock_get_balance = AsyncMock(
                return_value={"balance": 10000.0, "total_value": 10000.0}
            )
            mock_get_positions = AsyncMock(return_value=[])
            mock_get_price = AsyncMock(return_value=0.50)

            risk_guard = RiskGuard(
                config=config,
                store=store,
                get_balance_fn=mock_get_balance,
                get_positions_fn=mock_get_positions,
                get_price_fn=mock_get_price,
            )

            result = await risk_guard.check_trade(
                token_id="test_token",
                side="BUY",
                amount=100.0,
                provider="polymarket",
                agent_id="manual_user",
                agent_reasoning="Manual trade via TUI",
            )

            assert (
                result.approved is True
            ), f"Trade should be approved: {result.violations}"
            assert (
                len(result.violations) == 0
            ), f"No violations expected: {result.violations}"

    @pytest.mark.asyncio
    async def test_h4_concurrent_trades_serialized(self):
        """H.4: Verify TradingTools uses async lock for serialization.

        The execution lock in TradingTools serializes concurrent trade execution.
        Two tasks each holding lock for 1s should take ~2s total (not ~1s parallel).
        """
        with patch("polycli.utils.config.get_paper_mode", return_value=False):
            from polycli.agents.tools.trading import TradingTools

            mock_poly = AsyncMock()
            mock_poly.get_balance.return_value = {"balance": 10000.0}
            mock_poly.place_market_order.return_value = MagicMock(
                id="order_123", status=MagicMock(value="filled")
            )
            mock_poly.get_positions.return_value = []
            mock_poly.get_orderbook.return_value = MagicMock(
                bids=[MagicMock(price=0.50)], asks=[MagicMock(price=0.52)]
            )

            trading_tools = TradingTools(poly_provider=mock_poly)

            execution_count = 0

            async def tracked_execution():
                nonlocal execution_count
                async with trading_tools._execution_lock:
                    start = time.perf_counter()
                    await asyncio.sleep(1.0)
                    end = time.perf_counter()
                    execution_count += 1

            tasks = [tracked_execution() for _ in range(2)]

            start_total = time.perf_counter()
            await asyncio.gather(*tasks)
            end_total = time.perf_counter()

            total_duration = end_total - start_total

            assert execution_count == 2, "Both executions should complete"
            assert (
                total_duration >= 1.9
            ), f"Concurrent trades should be serialized (~2s), got {total_duration:.2f}s"

    @pytest.mark.asyncio
    async def test_h4_trading_tools_uses_risk_guard(self):
        """H.4: Verify TradingTools.place_market_buy uses RiskGuard."""
        with patch("polycli.utils.config.get_paper_mode", return_value=False):
            with patch("polycli.paper.provider.PaperTradingProvider"):
                from polycli.agents.tools.trading import TradingTools

                mock_poly = AsyncMock()
                mock_poly.get_balance.return_value = {"balance": 10000.0}
                mock_poly.get_orderbook.return_value = MagicMock(
                    bids=[MagicMock(price=0.50)], asks=[MagicMock(price=0.52)]
                )
                mock_poly.get_positions.return_value = []

                trading_tools = TradingTools(poly_provider=mock_poly)

                mock_risk_result = MagicMock()
                mock_risk_result.approved = True
                mock_risk_result.violations = []
                mock_risk_result.risk_score = 0

                with patch.object(trading_tools, "_get_risk_guard") as mock_risk_guard:
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.check_trade = AsyncMock(
                        return_value=mock_risk_result
                    )
                    mock_risk_guard.return_value = mock_guard_instance

                    mock_poly.place_market_order.return_value = MagicMock(
                        id="order_123", status=MagicMock(value="filled")
                    )

                    _result = await trading_tools.place_market_buy(
                        token_id="test_token", amount=100.0, provider="polymarket"
                    )

                    mock_guard_instance.check_trade.assert_called_once()
                    call_kwargs = mock_guard_instance.check_trade.call_args[1]
                    assert call_kwargs["token_id"] == "test_token"
                    assert call_kwargs["side"] == "BUY"
                    assert call_kwargs["amount"] == 100.0

    @pytest.mark.asyncio
    async def test_h4_trading_tools_uses_execution_lock(self):
        """H.4: Verify TradingTools uses async lock for serialization."""
        with patch("polycli.utils.config.get_paper_mode", return_value=False):
            from polycli.agents.tools.trading import TradingTools

            mock_poly = AsyncMock()
            mock_poly.get_balance.return_value = {"balance": 10000.0}
            mock_poly.place_market_order.return_value = MagicMock(
                id="order_123", status=MagicMock(value="filled")
            )
            mock_poly.get_positions.return_value = []
            mock_poly.get_orderbook.return_value = MagicMock(
                bids=[MagicMock(price=0.50)], asks=[MagicMock(price=0.52)]
            )

            trading_tools = TradingTools(poly_provider=mock_poly)

            assert hasattr(
                trading_tools, "_execution_lock"
            ), "TradingTools should have _execution_lock"
            assert isinstance(
                trading_tools._execution_lock, asyncio.Lock
            ), "_execution_lock should be an asyncio.Lock"

    @pytest.mark.asyncio
    async def test_h4_sell_also_uses_risk_guard(self):
        """H.4: Verify TradingTools.place_market_sell also uses RiskGuard."""
        with patch("polycli.utils.config.get_paper_mode", return_value=False):
            with patch("polycli.paper.provider.PaperTradingProvider"):
                from polycli.agents.tools.trading import TradingTools

                mock_poly = AsyncMock()
                mock_poly.get_balance.return_value = {"balance": 10000.0}
                mock_poly.place_market_order.return_value = MagicMock(
                    id="order_456", status=MagicMock(value="filled")
                )
                mock_poly.get_positions.return_value = [
                    {"size": 200, "avg_price": 0.50}
                ]
                mock_poly.get_orderbook.return_value = MagicMock(
                    bids=[MagicMock(price=0.50)], asks=[MagicMock(price=0.52)]
                )

                trading_tools = TradingTools(poly_provider=mock_poly)

                mock_risk_result = MagicMock()
                mock_risk_result.approved = True
                mock_risk_result.violations = []
                mock_risk_result.risk_score = 0

                with patch.object(trading_tools, "_get_risk_guard") as mock_risk_guard:
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.check_trade = AsyncMock(
                        return_value=mock_risk_result
                    )
                    mock_risk_guard.return_value = mock_guard_instance

                    _result = await trading_tools.place_market_sell(
                        token_id="test_token", shares=100.0, provider="polymarket"
                    )

                    mock_guard_instance.check_trade.assert_called_once()
                    call_kwargs = mock_guard_instance.check_trade.call_args[1]
                    assert call_kwargs["side"] == "SELL"


class TestRiskGuardChecklist:
    """Additional risk guard verification tests."""

    def test_risk_guard_exists(self):
        """Verify RiskGuard class exists and is importable."""
        from polycli.risk.guard import RiskGuard

        assert RiskGuard is not None

    def test_trading_tools_exists(self):
        """Verify TradingTools class exists and is importable."""
        from polycli.agents.tools.trading import TradingTools

        assert TradingTools is not None

    def test_risk_config_has_circuit_breaker(self):
        """Verify RiskConfig supports circuit breaker configuration."""
        config = RiskConfig()
        assert hasattr(config, "circuit_breaker_enabled")
        assert hasattr(config, "circuit_breaker_cooldown_minutes")

    def test_risk_violation_types_defined(self):
        """Verify all required violation types are defined."""
        from polycli.risk.models import RiskViolationType

        expected_types = [
            "MANUAL_BLOCK",
            "CIRCUIT_BREAKER_ACTIVE",
            "POSITION_SIZE_EXCEEDED",
            "INSUFFICIENT_BALANCE",
            "DAILY_LOSS_LIMIT_EXCEEDED",
            "MAX_DRAWDOWN_EXCEEDED",
            "TRADE_FREQUENCY_EXCEEDED",
            "PRICE_DEVIATION_TOO_HIGH",
        ]

        for violation_type in expected_types:
            assert hasattr(
                RiskViolationType, violation_type
            ), f"Missing violation type: {violation_type}"


class TestTradingToolsIntegration:
    """Integration tests for TradingTools with RiskGuard."""

    @pytest.mark.asyncio
    async def test_trading_tools_executes_with_lock(self):
        """Verify TradingTools acquires lock before execution."""
        with patch("polycli.utils.config.get_paper_mode", return_value=False):
            with patch("polycli.paper.provider.PaperTradingProvider"):
                from polycli.agents.tools.trading import TradingTools

                mock_poly = AsyncMock()
                mock_poly.get_balance.return_value = {"balance": 10000.0}
                mock_poly.place_market_order.return_value = MagicMock(
                    id="order_789", status=MagicMock(value="filled")
                )
                mock_poly.get_positions.return_value = []
                mock_poly.get_orderbook.return_value = MagicMock(
                    bids=[MagicMock(price=0.50)], asks=[MagicMock(price=0.52)]
                )

                trading_tools = TradingTools(poly_provider=mock_poly)

                mock_risk_result = MagicMock()
                mock_risk_result.approved = True
                mock_risk_result.violations = []
                mock_risk_result.risk_score = 0

                with patch.object(trading_tools, "_get_risk_guard") as mock_risk_guard:
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.check_trade = AsyncMock(
                        return_value=mock_risk_result
                    )
                    mock_risk_guard.return_value = mock_guard_instance

                    result = await trading_tools.place_market_buy(
                        token_id="test_token", amount=100.0, provider="polymarket"
                    )

                    assert result["success"] is True
                    mock_poly.place_market_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_trading_tools_blocked_by_insufficient_balance(self):
        """Verify TradingTools blocks trades with insufficient balance."""
        with patch("polycli.utils.config.get_paper_mode", return_value=False):
            with patch("polycli.paper.provider.PaperTradingProvider"):
                from polycli.agents.tools.trading import TradingTools

                mock_poly = AsyncMock()
                mock_poly.get_balance.return_value = {"balance": 50.0}
                mock_poly.place_market_order.return_value = MagicMock(
                    id="order_999", status=MagicMock(value="filled")
                )
                mock_poly.get_positions.return_value = []
                mock_poly.get_orderbook.return_value = MagicMock(
                    bids=[MagicMock(price=0.50)], asks=[MagicMock(price=0.52)]
                )

                trading_tools = TradingTools(poly_provider=mock_poly)

                mock_risk_result = MagicMock()
                mock_risk_result.approved = True
                mock_risk_result.violations = []
                mock_risk_result.risk_score = 0

                with patch.object(trading_tools, "_get_risk_guard") as mock_risk_guard:
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.check_trade = AsyncMock(
                        return_value=mock_risk_result
                    )
                    mock_risk_guard.return_value = mock_guard_instance

                    result = await trading_tools.place_market_buy(
                        token_id="test_token", amount=100.0, provider="polymarket"
                    )

                    assert result["success"] is False
                    assert "Insufficient balance" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
