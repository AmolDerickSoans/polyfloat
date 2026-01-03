"""Risk context infrastructure for proactive risk awareness."""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class RiskStatus(Enum):
    """Overall risk status indicator."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class RiskContext:
    """Comprehensive snapshot of current risk state for LLM consumption.

    This dataclass aggregates all risk-relevant information including
    portfolio state, limits, current metrics, and computed capacity fields.
    """

    available_balance: Decimal = Decimal("0")
    total_portfolio_value: Decimal = Decimal("0")
    largest_position_pct: Decimal = Decimal("0")
    position_count: int = 0

    daily_pnl: Decimal = Decimal("0")
    daily_pnl_pct: Decimal = Decimal("0")
    max_drawdown_current: Decimal = Decimal("0")
    trades_today: int = 0

    max_position_size_usd: Decimal = Decimal("100")
    max_position_size_pct: Decimal = Decimal("0.10")
    daily_loss_limit_usd: Decimal = Decimal("50")
    max_drawdown_pct: Decimal = Decimal("0.20")

    max_trades_per_minute: int = 10
    max_trades_per_hour: int = 100
    trades_last_minute: int = 0
    trades_last_hour: int = 0

    trading_enabled: bool = True
    agents_enabled: bool = True
    circuit_breaker_active: bool = False
    circuit_breaker_reason: str = ""

    status: RiskStatus = RiskStatus.GREEN
    risk_score_current: float = 0.0

    remaining_position_budget_usd: Decimal = Decimal("100")
    remaining_loss_budget_usd: Decimal = Decimal("50")
    remaining_trades_this_minute: int = 10
    remaining_trades_this_hour: int = 100

    def to_llm_context(self) -> str:
        """Generate structured text representation for LLM consumption."""
        status_emoji = {
            RiskStatus.GREEN: "OK",
            RiskStatus.YELLOW: "WARN",
            RiskStatus.RED: "STOP",
        }[self.status]

        trading_status = (
            "BLOCKED"
            if not self.trading_enabled
            else (
                "AGENTS_BLOCKED"
                if not self.agents_enabled
                else ("CIRCUIT_BREAKER" if self.circuit_breaker_active else "ENABLED")
            )
        )

        sections = [
            "=== RISK CONSTRAINTS AND CURRENT STATE ===",
            f"Overall Status: {status_emoji} ({self.status.value.upper()})",
            f"Current Risk Score: {self.risk_score_current:.0f}/100",
            "",
            "=== TRADING STATUS ===",
            f"Trading Enabled: {self.trading_enabled}",
            f"Agents Enabled: {self.agents_enabled}",
            f"Circuit Breaker Active: {self.circuit_breaker_active}",
            f"Circuit Breaker Reason: {self.circuit_breaker_reason or 'None'}",
            f"Trading Status: {trading_status}",
            "",
            "=== PORTFOLIO STATE ===",
            f"Total Portfolio Value: ${self.total_portfolio_value:.2f}",
            f"Available Balance: ${self.available_balance:.2f}",
            f"Largest Position: {self.largest_position_pct:.1%} of portfolio",
            f"Position Count: {self.position_count}",
            f"Today's Trades: {self.trades_today}",
            "",
            "=== POSITION SIZE LIMITS ===",
            f"Max Position Size (USD): ${self.max_position_size_usd:.2f}",
            f"Max Position Size (%): {self.max_position_size_pct:.1%}",
            f"Remaining Position Budget: ${self.remaining_position_budget_usd:.2f}",
            "",
            "=== LOSS LIMITS ===",
            f"Today's P&L: ${self.daily_pnl:.2f} ({self.daily_pnl_pct:.2%})",
            f"Daily Loss Limit: ${self.daily_loss_limit_usd:.2f}",
            f"Remaining Loss Budget: ${self.remaining_loss_budget_usd:.2f}",
            f"Current Drawdown: {self.max_drawdown_current:.1%} (max: {self.max_drawdown_pct:.1%})",
            "",
            "=== TRADE FREQUENCY ===",
            f"Max Trades/Minute: {self.max_trades_per_minute}",
            f"Trades Last Minute: {self.trades_last_minute}",
            f"Remaining This Minute: {self.remaining_trades_this_minute}",
            f"Max Trades/Hour: {self.max_trades_per_hour}",
            f"Trades Last Hour: {self.trades_last_hour}",
            f"Remaining This Hour: {self.remaining_trades_this_hour}",
            "",
            "=== OVERALL RISK SCORE ===",
            f"Current Risk Score: {self.risk_score_current:.0f}/100",
            f"Interpretation: {'Low risk' if self.risk_score_current < 30 else 'Moderate risk' if self.risk_score_current < 60 else 'High risk'}",
        ]

        return "\n".join(sections)
