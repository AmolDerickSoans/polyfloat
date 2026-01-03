"""Risk management data models."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid


class RiskViolationType(Enum):
    """Types of risk violations."""

    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    PORTFOLIO_CONCENTRATION_EXCEEDED = "portfolio_concentration_exceeded"
    DAILY_LOSS_LIMIT_EXCEEDED = "daily_loss_limit_exceeded"
    MAX_DRAWDOWN_EXCEEDED = "max_drawdown_exceeded"
    CIRCUIT_BREAKER_ACTIVE = "circuit_breaker_active"
    PRICE_DEVIATION_TOO_HIGH = "price_deviation_too_high"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    MARKET_CLOSED = "market_closed"
    TRADE_FREQUENCY_EXCEEDED = "trade_frequency_exceeded"
    MANUAL_BLOCK = "manual_block"


class RiskErrorCode(Enum):
    """Structured error codes for risk violations."""

    ERR_POS_SIZE_ABSOLUTE = "E001"
    ERR_POS_SIZE_PERCENT = "E002"
    ERR_INSUFFICIENT_BALANCE = "E003"
    ERR_DAILY_LOSS = "E004"
    ERR_MAX_DRAWDOWN = "E005"
    ERR_FREQ_MINUTE = "E006"
    ERR_FREQ_HOUR = "E007"
    ERR_TRADING_DISABLED = "E008"
    ERR_AGENTS_DISABLED = "E009"
    ERR_CIRCUIT_BREAKER = "E010"
    ERR_PRICE_DEVIATION = "E011"


@dataclass
class RiskViolation:
    """Represents a single risk violation."""

    violation_type: RiskViolationType
    message: str
    current_value: float
    limit_value: float
    severity: str = "high"
    error_code: Optional[RiskErrorCode] = None
    suggested_value: Optional[float] = None

    def to_agent_feedback(self) -> str:
        """Generate structured feedback string for agent learning."""
        if self.error_code:
            return f"[{self.error_code.value}] {self.message}"
        return self.message


@dataclass
class RiskCheckResult:
    """Result of a risk check."""

    approved: bool
    violations: List[RiskViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    risk_score: float = 0.0  # 0-100, higher = riskier
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "violations": [
                {
                    "type": v.violation_type.value,
                    "message": v.message,
                    "current": v.current_value,
                    "limit": v.limit_value,
                    "severity": v.severity,
                }
                for v in self.violations
            ],
            "warnings": self.warnings,
            "risk_score": self.risk_score,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class RiskMetrics:
    """Current risk metrics snapshot."""

    total_portfolio_value: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    total_exposure: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    max_drawdown_current: Decimal = Decimal("0")
    position_count: int = 0
    largest_position_pct: Decimal = Decimal("0")
    trades_today: int = 0
    last_trade_time: Optional[datetime] = None


@dataclass
class TradeAuditLog:
    """Audit log entry for trade attempts."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Trade details
    token_id: str = ""
    market_id: str = ""
    side: str = ""  # "BUY" or "SELL"
    amount: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    provider: str = ""

    # Risk check results
    approved: bool = False
    violations: str = ""  # JSON string of violations
    warnings: str = ""  # JSON string of warnings
    risk_score: float = 0.0

    # Context
    agent_id: Optional[str] = None
    agent_reasoning: Optional[str] = None  # LLM explanation if agent-initiated

    # Execution result (if approved)
    executed: bool = False
    execution_result: str = ""  # JSON string of result

    # Risk metrics at time of check
    metrics_snapshot: str = ""  # JSON string of RiskMetrics
