"""Integration tests for agent risk context integration."""
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from polycli.risk import RiskContext, RiskStatus, RiskGuard, RiskConfig
from polycli.risk.models import RiskViolation, RiskViolationType, RiskErrorCode
from polycli.agents.prompts import Prompter


class TestPromptRiskIntegration:
    """Test prompt integration with risk context."""

    def test_one_best_trade_includes_risk_context(self):
        """Test that one_best_trade prompt includes risk context when provided."""
        prompter = Prompter()
        risk_context = RiskContext(
            available_balance=Decimal("500.00"),
            total_portfolio_value=Decimal("1000.00"),
            status=RiskStatus.GREEN,
            risk_score_current=25.0,
            remaining_position_budget_usd=Decimal("100"),
            remaining_loss_budget_usd=Decimal("50"),
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
        )
        risk_context_str = risk_context.to_llm_context()

        prompt = prompter.one_best_trade(
            prediction="Trump approval rating will increase",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.55, "No": 0.45},
            risk_context=risk_context_str,
        )

        assert "=== CRITICAL RISK CONTEXT ===" in prompt
        assert risk_context_str in prompt
        assert "IMPORTANT CONSTRAINTS:" in prompt
        assert "Position size MUST NOT exceed the remaining position budget" in prompt

    def test_one_best_trade_without_risk_context(self):
        """Test that one_best_trade works without risk context."""
        prompter = Prompter()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
        )

        assert "=== CRITICAL RISK CONTEXT ===" not in prompt
        assert "IMPORTANT CONSTRAINTS:" not in prompt

    def test_one_best_trade_no_trade_response_format(self):
        """Test that NO_TRADE_AVAILABLE response format is documented."""
        prompter = Prompter()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
        )

        assert "NO_TRADE_AVAILABLE" in prompt
        assert "reason:" in prompt

    def test_one_best_trade_risk_acknowledgment_required(self):
        """Test that risk_acknowledgment field is required in response."""
        prompter = Prompter()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
        )

        assert "risk_acknowledgment:" in prompt

    def test_one_best_trade_response_format(self):
        """Test the complete response format example in prompt."""
        prompter = Prompter()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
        )

        assert "price:" in prompt
        assert "size:" in prompt
        assert "side: BUY or SELL" in prompt


class TestToolRejectionsWithErrorCodes:
    """Test that tool rejections return structured error codes."""

    @pytest.mark.asyncio
    async def test_violation_has_error_code(self):
        """Test that RiskViolation has error_code field."""
        violation = RiskViolation(
            violation_type=RiskViolationType.POSITION_SIZE_EXCEEDED,
            message="Trade size $150 exceeds max $100",
            current_value=150.0,
            limit_value=100.0,
            severity="high",
            error_code=RiskErrorCode.ERR_POS_SIZE_ABSOLUTE,
            suggested_value=100.0,
        )

        assert violation.error_code == RiskErrorCode.ERR_POS_SIZE_ABSOLUTE
        assert violation.error_code.value == "E001"

    @pytest.mark.asyncio
    async def test_violation_to_agent_feedback_with_code(self):
        """Test that to_agent_feedback() includes error code."""
        violation = RiskViolation(
            violation_type=RiskViolationType.POSITION_SIZE_EXCEEDED,
            message="Trade size $150 exceeds max $100",
            current_value=150.0,
            limit_value=100.0,
            error_code=RiskErrorCode.ERR_POS_SIZE_ABSOLUTE,
            suggested_value=100.0,
        )

        feedback = violation.to_agent_feedback()
        assert "[E001]" in feedback
        assert "Trade size $150 exceeds max $100" in feedback

    @pytest.mark.asyncio
    async def test_violation_to_agent_feedback_without_code(self):
        """Test that to_agent_feedback() works without error code."""
        violation = RiskViolation(
            violation_type=RiskViolationType.MARKET_CLOSED,
            message="Market is closed for trading",
            current_value=0.0,
            limit_value=1.0,
        )

        feedback = violation.to_agent_feedback()
        assert "Market is closed for trading" in feedback
        assert "[" not in feedback

    def test_all_error_codes_defined(self):
        """Test that all expected error codes are defined."""
        assert RiskErrorCode.ERR_POS_SIZE_ABSOLUTE.value == "E001"
        assert RiskErrorCode.ERR_POS_SIZE_PERCENT.value == "E002"
        assert RiskErrorCode.ERR_INSUFFICIENT_BALANCE.value == "E003"
        assert RiskErrorCode.ERR_DAILY_LOSS.value == "E004"
        assert RiskErrorCode.ERR_MAX_DRAWDOWN.value == "E005"
        assert RiskErrorCode.ERR_FREQ_MINUTE.value == "E006"
        assert RiskErrorCode.ERR_FREQ_HOUR.value == "E007"
        assert RiskErrorCode.ERR_TRADING_DISABLED.value == "E008"
        assert RiskErrorCode.ERR_AGENTS_DISABLED.value == "E009"
        assert RiskErrorCode.ERR_CIRCUIT_BREAKER.value == "E010"
        assert RiskErrorCode.ERR_PRICE_DEVIATION.value == "E011"

    def test_error_codes_map_to_violation_types(self):
        """Test that error codes correspond to expected violation types."""
        position_size_codes = [
            RiskErrorCode.ERR_POS_SIZE_ABSOLUTE,
            RiskErrorCode.ERR_POS_SIZE_PERCENT,
        ]
        for code in position_size_codes:
            assert "POSITION" in code.name or "SIZE" in code.name


class TestSuggestedFixes:
    """Test that suggested fixes are correctly provided."""

    @pytest.mark.asyncio
    async def test_position_size_suggested_fix(self):
        """Test suggested value for position size violations."""
        violation = RiskViolation(
            violation_type=RiskViolationType.POSITION_SIZE_EXCEEDED,
            message="Trade size $150 exceeds max $100",
            current_value=150.0,
            limit_value=100.0,
            error_code=RiskErrorCode.ERR_POS_SIZE_ABSOLUTE,
            suggested_value=100.0,
        )

        assert violation.suggested_value == 100.0

    @pytest.mark.asyncio
    async def test_frequency_suggested_fix(self):
        """Test suggested fix for frequency violations."""
        violation = RiskViolation(
            violation_type=RiskViolationType.TRADE_FREQUENCY_EXCEEDED,
            message="Too many trades this minute",
            current_value=11.0,
            limit_value=10.0,
            error_code=RiskErrorCode.ERR_FREQ_MINUTE,
            suggested_value=0.0,
        )

        assert violation.error_code == RiskErrorCode.ERR_FREQ_MINUTE
        assert violation.suggested_value == 0.0

    @pytest.mark.asyncio
    async def test_insufficient_balance_suggested_fix(self):
        """Test suggested fix for balance violations."""
        violation = RiskViolation(
            violation_type=RiskViolationType.INSUFFICIENT_BALANCE,
            message="Insufficient balance for trade",
            current_value=20.0,
            limit_value=50.0,
            error_code=RiskErrorCode.ERR_INSUFFICIENT_BALANCE,
            suggested_value=20.0,
        )

        assert violation.error_code == RiskErrorCode.ERR_INSUFFICIENT_BALANCE
        assert violation.suggested_value == 20.0


class TestNoTradeAvailableHandling:
    """Test NO_TRADE_AVAILABLE response handling."""

    def test_no_trade_available_format(self):
        """Test that NO_TRADE_AVAILABLE has correct format in prompt."""
        prompter = Prompter()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
        )

        assert "NO_TRADE_AVAILABLE" in prompt
        assert "reason:" in prompt

    def test_circuit_breaker_triggers_no_trade(self):
        """Test that circuit breaker in risk context triggers NO_TRADE_AVAILABLE."""
        prompter = Prompter()
        risk_context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=True,
            circuit_breaker_reason="Daily loss limit exceeded",
            status=RiskStatus.RED,
        )
        risk_context_str = risk_context.to_llm_context()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
            risk_context=risk_context_str,
        )

        assert "CIRCUIT_BREAKER" in prompt
        assert "NO_TRADE_AVAILABLE" in prompt

    def test_trading_disabled_triggers_no_trade(self):
        """Test that trading disabled in risk context triggers NO_TRADE_AVAILABLE."""
        prompter = Prompter()
        risk_context = RiskContext(
            trading_enabled=False,
            agents_enabled=True,
            circuit_breaker_active=False,
            status=RiskStatus.RED,
        )
        risk_context_str = risk_context.to_llm_context()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
            risk_context=risk_context_str,
        )

        assert "BLOCKED" in prompt
        assert "NO_TRADE_AVAILABLE" in prompt

    def test_near_zero_loss_budget_triggers_no_trade(self):
        """Test that near-zero loss budget suggests NO_TRADE_AVAILABLE."""
        prompter = Prompter()
        risk_context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            daily_pnl=Decimal("-48.00"),
            daily_loss_limit_usd=Decimal("50"),
            remaining_loss_budget_usd=Decimal("2"),
            status=RiskStatus.YELLOW,
        )
        risk_context_str = risk_context.to_llm_context()

        prompt = prompter.one_best_trade(
            prediction="Test prediction",
            outcomes=["Yes", "No"],
            outcome_prices={"Yes": 0.5, "No": 0.5},
            risk_context=risk_context_str,
        )

        assert "Remaining Loss Budget:" in prompt
        assert "reduce size or skip" in prompt


class TestAgentRiskContextFlow:
    """Test complete flow of agent using risk context."""

    def test_prompt_includes_all_risk_sections(self):
        """Test that risk context includes all required sections."""
        context = RiskContext(
            available_balance=Decimal("500.00"),
            total_portfolio_value=Decimal("1000.00"),
            largest_position_pct=Decimal("0.25"),
            position_count=5,
            daily_pnl=Decimal("-25.00"),
            daily_pnl_pct=Decimal("-0.025"),
            max_drawdown_current=Decimal("0.05"),
            trades_today=8,
            max_position_size_usd=Decimal("100"),
            max_position_size_pct=Decimal("0.10"),
            daily_loss_limit_usd=Decimal("50"),
            max_drawdown_pct=Decimal("0.20"),
            max_trades_per_minute=10,
            max_trades_per_hour=100,
            trades_last_minute=3,
            trades_last_hour=20,
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            risk_score_current=35.0,
            remaining_position_budget_usd=Decimal("100"),
            remaining_loss_budget_usd=Decimal("25"),
            remaining_trades_this_minute=7,
            remaining_trades_this_hour=80,
        )

        llm_context = context.to_llm_context()

        required_sections = [
            "RISK CONSTRAINTS AND CURRENT STATE",
            "TRADING STATUS",
            "PORTFOLIO STATE",
            "POSITION SIZE LIMITS",
            "LOSS LIMITS",
            "TRADE FREQUENCY",
            "OVERALL RISK SCORE",
        ]

        for section in required_sections:
            assert section in llm_context

    def test_risk_context_available_balance_format(self):
        """Test that available balance is properly formatted."""
        context = RiskContext(available_balance=Decimal("1234.56"))
        llm_context = context.to_llm_context()

        assert "Available Balance: $1234.56" in llm_context

    def test_risk_context_percentage_format(self):
        """Test that percentages are properly formatted."""
        context = RiskContext(
            largest_position_pct=Decimal("0.25"),
            daily_pnl_pct=Decimal("-0.025"),
            max_drawdown_current=Decimal("0.05"),
            max_drawdown_pct=Decimal("0.20"),
            max_position_size_pct=Decimal("0.10"),
        )
        llm_context = context.to_llm_context()

        assert "25.0%" in llm_context
        assert "-2.5%" in llm_context or "-2.50%" in llm_context
        assert "5.0%" in llm_context
        assert "20.0%" in llm_context
        assert "10.0%" in llm_context

    def test_risk_score_interpretation(self):
        """Test that risk score includes interpretation."""
        context_low = RiskContext(risk_score_current=25.0)
        context_moderate = RiskContext(risk_score_current=45.0)
        context_high = RiskContext(risk_score_current=75.0)

        low_context = context_low.to_llm_context()
        moderate_context = context_moderate.to_llm_context()
        high_context = context_high.to_llm_context()

        assert "Low risk" in low_context
        assert "Moderate risk" in moderate_context
        assert "High risk" in high_context


class TestRiskContextIntegrationWithTradingTools:
    """Test integration between risk context and trading tools."""

    @pytest.mark.asyncio
    async def test_trading_tools_error_response_format(self):
        """Test that trading tools return structured error responses."""
        from polycli.agents.tools.trading import TradingTools

        mock_provider = Mock()
        mock_provider.get_balance = AsyncMock(return_value={"balance": 100.0})
        mock_provider.place_market_order = AsyncMock()

        tools = TradingTools(poly_provider=mock_provider)

        with patch.object(tools, "_get_risk_guard") as mock_guard:
            mock_risk_result = Mock()
            mock_risk_result.approved = False
            mock_violation = Mock()
            mock_violation.message = "Trade size exceeds limit"
            mock_violation.to_agent_feedback.return_value = (
                "[E001] Trade size exceeds limit"
            )
            mock_violation.error_code = RiskErrorCode.ERR_POS_SIZE_ABSOLUTE
            mock_violation.suggested_value = 100.0
            mock_risk_result.violations = [mock_violation]
            mock_risk_result.risk_score = 45.0
            mock_guard.return_value.check_trade = AsyncMock(
                return_value=mock_risk_result
            )

            result = await tools.place_market_buy(
                token_id="test_token", amount=150.0, provider="polymarket"
            )

            assert result["success"] is False
            assert "error_codes" in result
            assert "E001" in result["error_codes"]
            assert "suggested_fixes" in result
            assert "E001" in result["suggested_fixes"]
            assert result["suggested_fixes"]["E001"] == 100.0

    @pytest.mark.asyncio
    async def test_risk_guard_rejects_oversized_trade(self, tmp_path):
        """Test that risk guard rejects oversized trades with correct error code."""
        from polycli.risk.store import RiskAuditStore

        async def mock_balance(provider):
            return {"balance": 500.0, "total_value": 1000.0}

        async def mock_positions(provider):
            return []

        async def mock_price(token_id, side):
            return 0.50

        config = RiskConfig(
            max_position_size_usd=Decimal("100"),
            max_position_size_pct=Decimal("0.10"),
            daily_loss_limit_usd=Decimal("50"),
            trading_enabled=True,
            circuit_breaker_enabled=False,
        )

        store = RiskAuditStore(db_path=tmp_path / "test_risk.db")

        guard = RiskGuard(
            config=config,
            store=store,
            get_balance_fn=mock_balance,
            get_positions_fn=mock_positions,
            get_price_fn=mock_price,
        )

        result = await guard.check_trade(
            token_id="test_token", side="BUY", amount=150.0, provider="polymarket"
        )

        assert result.approved is False
        assert len(result.violations) > 0

        position_violation = next(
            (
                v
                for v in result.violations
                if v.violation_type == RiskViolationType.POSITION_SIZE_EXCEEDED
            ),
            None,
        )
        assert position_violation is not None
        assert position_violation.error_code == RiskErrorCode.ERR_POS_SIZE_ABSOLUTE
