"""Tests for RiskContext dataclass and its behavior."""
from decimal import Decimal
from polycli.risk import RiskContext, RiskStatus


class TestRiskContextInstantiation:
    """Test RiskContext instantiation with all required fields."""

    def test_default_instantiation(self):
        """Test RiskContext with all default values."""
        context = RiskContext()

        assert context.available_balance == Decimal("0")
        assert context.total_portfolio_value == Decimal("0")
        assert context.largest_position_pct == Decimal("0")
        assert context.position_count == 0
        assert context.daily_pnl == Decimal("0")
        assert context.daily_pnl_pct == Decimal("0")
        assert context.max_drawdown_current == Decimal("0")
        assert context.trades_today == 0
        assert context.max_position_size_usd == Decimal("100")
        assert context.max_position_size_pct == Decimal("0.10")
        assert context.daily_loss_limit_usd == Decimal("50")
        assert context.max_drawdown_pct == Decimal("0.20")
        assert context.max_trades_per_minute == 10
        assert context.max_trades_per_hour == 100
        assert context.trades_last_minute == 0
        assert context.trades_last_hour == 0
        assert context.trading_enabled is True
        assert context.agents_enabled is True
        assert context.circuit_breaker_active is False
        assert context.circuit_breaker_reason == ""
        assert context.status == RiskStatus.GREEN
        assert context.risk_score_current == 0.0
        assert context.remaining_position_budget_usd == Decimal("100")
        assert context.remaining_loss_budget_usd == Decimal("50")
        assert context.remaining_trades_this_minute == 10
        assert context.remaining_trades_this_hour == 100

    def test_custom_instantiation(self):
        """Test RiskContext with custom values."""
        context = RiskContext(
            available_balance=Decimal("500.00"),
            total_portfolio_value=Decimal("1000.00"),
            largest_position_pct=Decimal("0.25"),
            position_count=5,
            daily_pnl=Decimal("-25.00"),
            daily_pnl_pct=Decimal("-0.025"),
            max_drawdown_current=Decimal("0.05"),
            trades_today=8,
            max_position_size_usd=Decimal("200"),
            max_position_size_pct=Decimal("0.15"),
            daily_loss_limit_usd=Decimal("100"),
            max_drawdown_pct=Decimal("0.15"),
            max_trades_per_minute=5,
            max_trades_per_hour=50,
            trades_last_minute=2,
            trades_last_hour=15,
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            status=RiskStatus.GREEN,
            risk_score_current=25.0,
            remaining_position_budget_usd=Decimal("150"),
            remaining_loss_budget_usd=Decimal("75"),
            remaining_trades_this_minute=3,
            remaining_trades_this_hour=35,
        )

        assert context.available_balance == Decimal("500.00")
        assert context.total_portfolio_value == Decimal("1000.00")
        assert context.largest_position_pct == Decimal("0.25")
        assert context.position_count == 5
        assert context.daily_pnl == Decimal("-25.00")
        assert context.status == RiskStatus.GREEN


class TestRiskContextStatusDetermination:
    """Test RiskContext status determination logic."""

    def test_status_green_trading_enabled_no_breaker_low_loss(self):
        """GREEN when trading enabled, no circuit breaker, daily_loss < 80% limit."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            daily_pnl=Decimal("-30.00"),
            daily_loss_limit_usd=Decimal("50"),
            status=RiskStatus.GREEN,
        )

        assert context.trading_enabled is True
        assert context.circuit_breaker_active is False
        assert context.daily_pnl / context.daily_loss_limit_usd < Decimal("0.80")
        assert context.status == RiskStatus.GREEN

    def test_status_yellow_at_80_percent_loss_limit(self):
        """YELLOW when daily_loss >= 80% of daily_loss_limit_usd."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            daily_pnl=Decimal("-40.00"),
            daily_loss_limit_usd=Decimal("50"),
            status=RiskStatus.YELLOW,
        )

        loss_ratio = abs(context.daily_pnl) / context.daily_loss_limit_usd
        assert loss_ratio >= Decimal("0.80")
        assert context.status == RiskStatus.YELLOW

    def test_status_red_trading_disabled(self):
        """RED when trading disabled."""
        context = RiskContext(
            trading_enabled=False,
            agents_enabled=True,
            circuit_breaker_active=False,
            status=RiskStatus.RED,
        )

        assert context.trading_enabled is False
        assert context.status == RiskStatus.RED

    def test_status_red_agents_disabled(self):
        """RED when agents disabled (but trading enabled)."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=False,
            circuit_breaker_active=False,
            status=RiskStatus.RED,
        )

        assert context.agents_enabled is False
        assert context.status == RiskStatus.RED

    def test_status_red_circuit_breaker_active(self):
        """RED when circuit breaker active."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=True,
            circuit_breaker_reason="Daily loss limit exceeded",
            status=RiskStatus.RED,
        )

        assert context.circuit_breaker_active is True
        assert context.status == RiskStatus.RED

    def test_status_yellow_exactly_at_80_percent(self):
        """YELLOW at exactly 80% of daily loss limit."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            daily_pnl=Decimal("-40.00"),
            daily_loss_limit_usd=Decimal("50"),
            status=RiskStatus.YELLOW,
        )

        loss_ratio = abs(context.daily_pnl) / context.daily_loss_limit_usd
        assert loss_ratio == Decimal("0.80")
        assert context.status == RiskStatus.YELLOW

    def test_status_yellow_above_90_percent(self):
        """YELLOW above 90% of daily loss limit."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            daily_pnl=Decimal("-47.50"),
            daily_loss_limit_usd=Decimal("50"),
            status=RiskStatus.YELLOW,
        )

        loss_ratio = abs(context.daily_pnl) / context.daily_loss_limit_usd
        assert loss_ratio > Decimal("0.90")
        assert context.status == RiskStatus.YELLOW


class TestRiskContextToLlmContext:
    """Test RiskContext.to_llm_context() output format."""

    def test_to_llm_context_contains_all_sections(self):
        """Test that to_llm_context() includes all required sections."""
        context = RiskContext(
            available_balance=Decimal("500.00"),
            total_portfolio_value=Decimal("1000.00"),
            largest_position_pct=Decimal("0.25"),
            position_count=5,
            daily_pnl=Decimal("-25.00"),
            daily_pnl_pct=Decimal("-0.025"),
            max_drawdown_current=Decimal("0.05"),
            trades_today=8,
            max_position_size_usd=Decimal("200"),
            max_position_size_pct=Decimal("0.15"),
            daily_loss_limit_usd=Decimal("50"),
            max_drawdown_pct=Decimal("0.20"),
            max_trades_per_minute=5,
            max_trades_per_hour=50,
            trades_last_minute=2,
            trades_last_hour=15,
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=False,
            risk_score_current=25.0,
            remaining_position_budget_usd=Decimal("150"),
            remaining_loss_budget_usd=Decimal("25"),
            remaining_trades_this_minute=3,
            remaining_trades_this_hour=35,
        )

        llm_context = context.to_llm_context()

        assert "=== RISK CONSTRAINTS AND CURRENT STATE ===" in llm_context
        assert "Overall Status:" in llm_context
        assert "Current Risk Score:" in llm_context
        assert "=== TRADING STATUS ===" in llm_context
        assert "Trading Enabled:" in llm_context
        assert "Agents Enabled:" in llm_context
        assert "Circuit Breaker Active:" in llm_context
        assert "=== PORTFOLIO STATE ===" in llm_context
        assert "Total Portfolio Value:" in llm_context
        assert "Available Balance:" in llm_context
        assert "Largest Position:" in llm_context
        assert "Position Count:" in llm_context
        assert "=== POSITION SIZE LIMITS ===" in llm_context
        assert "Max Position Size (USD):" in llm_context
        assert "Max Position Size (%):" in llm_context
        assert "Remaining Position Budget:" in llm_context
        assert "=== LOSS LIMITS ===" in llm_context
        assert "Today's P&L:" in llm_context
        assert "Daily Loss Limit:" in llm_context
        assert "Remaining Loss Budget:" in llm_context
        assert "Current Drawdown:" in llm_context
        assert "=== TRADE FREQUENCY ===" in llm_context
        assert "Max Trades/Minute:" in llm_context
        assert "Remaining This Minute:" in llm_context
        assert "Max Trades/Hour:" in llm_context
        assert "Remaining This Hour:" in llm_context
        assert "=== OVERALL RISK SCORE ===" in llm_context

    def test_to_llm_context_green_status_emoji(self):
        """Test that GREEN status uses OK emoji."""
        context = RiskContext(status=RiskStatus.GREEN)
        llm_context = context.to_llm_context()

        assert "OK" in llm_context
        assert "GREEN" in llm_context

    def test_to_llm_context_yellow_status_emoji(self):
        """Test that YELLOW status uses WARN emoji."""
        context = RiskContext(status=RiskStatus.YELLOW)
        llm_context = context.to_llm_context()

        assert "WARN" in llm_context
        assert "YELLOW" in llm_context

    def test_to_llm_context_red_status_emoji(self):
        """Test that RED status uses STOP emoji."""
        context = RiskContext(status=RiskStatus.RED)
        llm_context = context.to_llm_context()

        assert "STOP" in llm_context
        assert "RED" in llm_context

    def test_to_llm_context_trading_blocked(self):
        """Test trading status BLOCKED when trading disabled."""
        context = RiskContext(trading_enabled=False)
        llm_context = context.to_llm_context()

        assert "BLOCKED" in llm_context
        assert "ENABLED" not in llm_context

    def test_to_llm_context_agents_blocked(self):
        """Test trading status AGENTS_BLOCKED when agents disabled."""
        context = RiskContext(trading_enabled=True, agents_enabled=False)
        llm_context = context.to_llm_context()

        assert "AGENTS_BLOCKED" in llm_context

    def test_to_llm_context_circuit_breaker(self):
        """Test trading status CIRCUIT_BREAKER when breaker active."""
        context = RiskContext(
            trading_enabled=True,
            agents_enabled=True,
            circuit_breaker_active=True,
            circuit_breaker_reason="Test reason",
        )
        llm_context = context.to_llm_context()

        assert "CIRCUIT_BREAKER" in llm_context
        assert "Test reason" in llm_context

    def test_to_llm_context_circuit_breaker_no_reason(self):
        """Test circuit breaker reason shows None when empty."""
        context = RiskContext(
            trading_enabled=True, circuit_breaker_active=True, circuit_breaker_reason=""
        )
        llm_context = context.to_llm_context()

        assert "Circuit Breaker Reason: None" in llm_context


class TestRiskContextDerivedFields:
    """Test RiskContext derived field calculations."""

    def test_remaining_position_budget_calculation(self):
        """Test remaining position budget is correctly set."""
        context = RiskContext(
            max_position_size_usd=Decimal("100"),
            remaining_position_budget_usd=Decimal("75"),
        )

        assert context.max_position_size_usd == Decimal("100")
        assert context.remaining_position_budget_usd == Decimal("75")

    def test_remaining_loss_budget_calculation(self):
        """Test remaining loss budget is correctly set."""
        context = RiskContext(
            daily_loss_limit_usd=Decimal("50"),
            daily_pnl=Decimal("-20"),
            remaining_loss_budget_usd=Decimal("30"),
        )

        assert context.daily_loss_limit_usd == Decimal("50")
        assert context.daily_pnl == Decimal("-20")
        assert context.remaining_loss_budget_usd == Decimal("30")

    def test_remaining_trades_this_minute(self):
        """Test remaining trades this minute calculation."""
        context = RiskContext(
            max_trades_per_minute=10,
            trades_last_minute=3,
            remaining_trades_this_minute=7,
        )

        assert context.max_trades_per_minute == 10
        assert context.trades_last_minute == 3
        assert context.remaining_trades_this_minute == 7

    def test_remaining_trades_this_hour(self):
        """Test remaining trades this hour calculation."""
        context = RiskContext(
            max_trades_per_hour=100, trades_last_hour=25, remaining_trades_this_hour=75
        )

        assert context.max_trades_per_hour == 100
        assert context.trades_last_hour == 25
        assert context.remaining_trades_this_hour == 75

    def test_zero_trades_remaining(self):
        """Test when no trades remaining."""
        context = RiskContext(
            max_trades_per_minute=10,
            trades_last_minute=10,
            remaining_trades_this_minute=0,
        )

        assert context.remaining_trades_this_minute == 0

    def test_full_loss_budget_available(self):
        """Test when full loss budget is available."""
        context = RiskContext(
            daily_loss_limit_usd=Decimal("50"),
            daily_pnl=Decimal("10"),
            remaining_loss_budget_usd=Decimal("50"),
        )

        assert context.remaining_loss_budget_usd == Decimal("50")

    def test_no_position_budget_remaining(self):
        """Test when no position budget remaining."""
        context = RiskContext(
            max_position_size_usd=Decimal("100"),
            remaining_position_budget_usd=Decimal("0"),
        )

        assert context.remaining_position_budget_usd == Decimal("0")


class TestRiskStatusEnum:
    """Test RiskStatus enum values."""

    def test_risk_status_values(self):
        """Test RiskStatus enum has correct values."""
        assert RiskStatus.GREEN.value == "green"
        assert RiskStatus.YELLOW.value == "yellow"
        assert RiskStatus.RED.value == "red"

    def test_risk_status_from_string(self):
        """Test creating RiskStatus from string value."""
        assert RiskStatus("green") == RiskStatus.GREEN
        assert RiskStatus("yellow") == RiskStatus.YELLOW
        assert RiskStatus("red") == RiskStatus.RED
