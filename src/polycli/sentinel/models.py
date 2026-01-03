"""
Sentinel Agent data models.

All models are immutable after creation to ensure proposal integrity.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class TriggerType(Enum):
    """Types of conditions that can trigger a proposal."""

    PRICE_BELOW = "price_below"
    PRICE_ABOVE = "price_above"
    SPREAD_ABOVE = "spread_above"
    SPREAD_BELOW = "spread_below"
    VOLUME_SPIKE = "volume_spike"
    IMBALANCE_BUY = "imbalance_buy"
    IMBALANCE_SELL = "imbalance_sell"
    MARKET_REOPEN = "market_reopen"
    NEWS_CORRELATION = "news_correlation"


class ProposalStatus(Enum):
    """Lifecycle states for a proposal."""

    PENDING = "pending"  # Awaiting user decision
    APPROVED = "approved"  # User approved
    REJECTED = "rejected"  # User explicitly rejected
    EXPIRED = "expired"  # Timed out
    INVALIDATED = "invalidated"  # Market state changed materially


class RiskStatus(Enum):
    """Risk traffic light status."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True)
class TriggerCondition:
    """A single condition that can fire a proposal.

    Attributes:
        trigger_type: The type of condition
        threshold: The threshold value (meaning depends on trigger_type)
        suggested_side: BUY or SELL when this trigger fires
        debounce_seconds: Minimum time between firings (anti-spam)
        time_window_seconds: For volume/correlation triggers
        baseline_window_seconds: For spike detection baseline
        hysteresis_pct: Price must move this % before re-triggering
    """

    trigger_type: TriggerType
    threshold: Decimal
    suggested_side: str  # "BUY" or "SELL"
    debounce_seconds: int = 60
    time_window_seconds: int = 0
    baseline_window_seconds: int = 3600
    hysteresis_pct: Decimal = Decimal("0.01")

    def describe(self, current_value: Optional[Decimal] = None) -> str:
        """Generate human-readable description of the trigger."""
        match self.trigger_type:
            case TriggerType.PRICE_BELOW:
                return f"Price dropped below ${self.threshold}"
            case TriggerType.PRICE_ABOVE:
                return f"Price rose above ${self.threshold}"
            case TriggerType.SPREAD_ABOVE:
                return f"Spread widened above ${self.threshold}"
            case TriggerType.SPREAD_BELOW:
                return f"Spread narrowed below ${self.threshold}"
            case TriggerType.VOLUME_SPIKE:
                return f"Volume spike detected (>{self.threshold}x baseline)"
            case TriggerType.IMBALANCE_BUY:
                return f"Strong buy pressure (imbalance >{self.threshold})"
            case TriggerType.IMBALANCE_SELL:
                return f"Strong sell pressure (imbalance <-{self.threshold})"
            case TriggerType.MARKET_REOPEN:
                return "Market reopened"
            case TriggerType.NEWS_CORRELATION:
                return f"News correlation: price moved >{self.threshold}%"
            case _:
                return f"Condition {self.trigger_type.value} met"


@dataclass(frozen=True)
class WatchedMarket:
    """A market being watched by the Sentinel.

    Attributes:
        market_id: Unique identifier for the market
        provider: Trading provider (polymarket, kalshi)
        triggers: List of conditions to watch for
        cooldown_seconds: Time to wait after any proposal before next
        expiry_seconds: How long proposals remain valid
    """

    market_id: str
    provider: str
    triggers: tuple  # Tuple[TriggerCondition, ...] for immutability
    cooldown_seconds: int = 300  # 5 minutes default
    expiry_seconds: int = 120  # 2 minutes default

    @classmethod
    def create(
        cls,
        market_id: str,
        provider: str,
        triggers: List[TriggerCondition],
        cooldown_seconds: int = 300,
        expiry_seconds: int = 120,
    ) -> "WatchedMarket":
        """Factory method to create from list of triggers."""
        return cls(
            market_id=market_id,
            provider=provider,
            triggers=tuple(triggers),
            cooldown_seconds=cooldown_seconds,
            expiry_seconds=expiry_seconds,
        )


@dataclass(frozen=True)
class SentinelConfig:
    """Global configuration for the Sentinel Agent.

    Attributes:
        watched_markets: Markets and their triggers
        global_cooldown_seconds: Min time between any proposals
        max_proposals_per_hour: Rate limit
        poll_interval_seconds: How often to check conditions
        enable_news_correlation: Whether to use news triggers
    """

    watched_markets: tuple  # Tuple[WatchedMarket, ...]
    global_cooldown_seconds: int = 60
    max_proposals_per_hour: int = 10
    poll_interval_seconds: float = 5.0
    enable_news_correlation: bool = False

    @classmethod
    def create(
        cls,
        watched_markets: List[WatchedMarket],
        **kwargs,
    ) -> "SentinelConfig":
        """Factory method to create from list of markets."""
        return cls(watched_markets=tuple(watched_markets), **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "watched_markets": [
                {
                    "market_id": m.market_id,
                    "provider": m.provider,
                    "triggers": [
                        {
                            "type": t.trigger_type.value,
                            "threshold": str(t.threshold),
                            "side": t.suggested_side,
                        }
                        for t in m.triggers
                    ],
                    "cooldown_seconds": m.cooldown_seconds,
                    "expiry_seconds": m.expiry_seconds,
                }
                for m in self.watched_markets
            ],
            "global_cooldown_seconds": self.global_cooldown_seconds,
            "max_proposals_per_hour": self.max_proposals_per_hour,
            "poll_interval_seconds": self.poll_interval_seconds,
            "enable_news_correlation": self.enable_news_correlation,
        }


@dataclass(frozen=True)
class MarketSnapshot:
    """Point-in-time market state when trigger fired.

    This is captured and frozen at proposal creation time.
    """

    market_id: str
    provider: str
    question: str
    best_bid: Decimal
    best_ask: Decimal
    spread: Decimal
    bid_depth_usd: Decimal
    ask_depth_usd: Decimal
    imbalance: float
    captured_at: datetime

    @property
    def mid_price(self) -> Decimal:
        """Calculate mid-price."""
        return (self.best_bid + self.best_ask) / 2


@dataclass(frozen=True)
class SentinelRiskSnapshot:
    """Minimal risk context for proposal generation.

    This is a read-only snapshot, never used to make trading decisions.
    """

    status: RiskStatus
    circuit_breaker_active: bool
    remaining_position_budget_usd: Decimal
    remaining_loss_budget_usd: Decimal
    risk_score: float
    total_portfolio_value: Decimal
    available_balance: Decimal

    def compute_summary(self, suggested_size: Optional[Decimal] = None) -> str:
        """Generate deterministic one-line risk summary."""
        if self.status == RiskStatus.RED:
            return "⛔ BLOCKED: Risk status is RED"

        if self.circuit_breaker_active:
            return "⛔ BLOCKED: Circuit breaker active"

        if suggested_size and suggested_size > self.remaining_position_budget_usd:
            return (
                f"⚠️ Size ${suggested_size:.2f} exceeds "
                f"budget ${self.remaining_position_budget_usd:.2f}"
            )

        if self.total_portfolio_value > 0:
            budget_used_pct = (
                1 - self.remaining_position_budget_usd / self.total_portfolio_value
            ) * 100
        else:
            budget_used_pct = 0

        return f"✓ Risk {self.status.value.upper()}: {budget_used_pct:.0f}% position budget used"

    def should_block_proposal(self) -> Optional[str]:
        """Returns blocking reason or None if OK to propose."""
        if self.status == RiskStatus.RED:
            return "Risk status RED"
        if self.circuit_breaker_active:
            return "Circuit breaker active"
        return None


@dataclass
class SentinelProposal:
    """Immutable trade proposal from Sentinel.

    This is the core output of the Sentinel Agent. It contains:
    - What triggered the proposal
    - Market state at trigger time
    - Risk context at trigger time
    - Suggested action (user decides sizing)

    The proposal is NOT an order and does NOT execute anything.
    """

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # What triggered this
    trigger_type: str = ""
    trigger_threshold: Decimal = Decimal("0")
    trigger_description: str = ""

    # Market state at trigger time
    market_snapshot: Optional[MarketSnapshot] = None

    # Risk context at trigger time
    risk_snapshot: Optional[SentinelRiskSnapshot] = None
    risk_summary: str = ""

    # Suggested action (user decides sizing)
    suggested_side: str = ""  # "BUY" or "SELL"
    indicative_size_usd: Optional[Decimal] = None  # Optional suggestion only

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=datetime.utcnow)

    # State
    status: ProposalStatus = ProposalStatus.PENDING
    user_decision_at: Optional[datetime] = None
    suppression_reason: Optional[str] = None  # If proposal was suppressed

    def is_valid(self) -> bool:
        """Check if proposal is still actionable."""
        if self.status != ProposalStatus.PENDING:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True

    def time_remaining(self) -> timedelta:
        """Time until expiry."""
        remaining = self.expires_at - datetime.utcnow()
        return max(remaining, timedelta(0))

    def mark_approved(self) -> None:
        """Mark proposal as approved by user."""
        self.status = ProposalStatus.APPROVED
        self.user_decision_at = datetime.utcnow()

    def mark_rejected(self) -> None:
        """Mark proposal as rejected by user."""
        self.status = ProposalStatus.REJECTED
        self.user_decision_at = datetime.utcnow()

    def mark_expired(self) -> None:
        """Mark proposal as expired."""
        self.status = ProposalStatus.EXPIRED

    def mark_invalidated(self, reason: str = "") -> None:
        """Mark proposal as invalidated due to market state change."""
        self.status = ProposalStatus.INVALIDATED
        self.suppression_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for telemetry/storage."""
        return {
            "id": self.id,
            "trigger_type": self.trigger_type,
            "trigger_threshold": str(self.trigger_threshold),
            "trigger_description": self.trigger_description,
            "market_id": self.market_snapshot.market_id
            if self.market_snapshot
            else None,
            "provider": self.market_snapshot.provider if self.market_snapshot else None,
            "suggested_side": self.suggested_side,
            "indicative_size_usd": str(self.indicative_size_usd)
            if self.indicative_size_usd
            else None,
            "risk_status": self.risk_snapshot.status.value
            if self.risk_snapshot
            else None,
            "risk_summary": self.risk_summary,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
        }

    def format_display(self) -> str:
        """Format proposal for TUI display."""
        if not self.market_snapshot or not self.risk_snapshot:
            return f"[Proposal {self.id}] Incomplete data"

        ms = self.market_snapshot
        remaining = self.time_remaining()
        mins, secs = divmod(int(remaining.total_seconds()), 60)

        lines = [
            "╭─────────────────────────────────────────────────────────────────╮",
            f"│  🔔 SENTINEL PROPOSAL #{self.id:<48}│",
            "├─────────────────────────────────────────────────────────────────┤",
            "│                                                                 │",
            "│  CONDITION FIRED:                                               │",
            f"│  {self.trigger_description:<61}│",
            "│                                                                 │",
            f"│  MARKET SNAPSHOT (captured {ms.captured_at.strftime('%Y-%m-%d %H:%M:%S')} UTC):           │",
            "│  ┌─────────────────────────────────────────────────────────┐   │",
            f"│  │ {ms.question[:55]:<55} │   │",
            f"│  │ Provider: {ms.provider:<46} │   │",
            f"│  │ Best Bid: ${ms.best_bid:<5}  │  Best Ask: ${ms.best_ask:<5}  │  Spread: ${ms.spread:<5} │   │",
            f"│  │ Bid Depth: ${ms.bid_depth_usd:,.0f}  │  Ask Depth: ${ms.ask_depth_usd:,.0f}{' ' * 15}│   │",
            "│  └─────────────────────────────────────────────────────────┘   │",
            "│                                                                 │",
            "│  RISK SUMMARY:                                                  │",
            f"│  {self.risk_summary:<61}│",
            "│                                                                 │",
            "│  RECOMMENDATION:                                                │",
            "│  ┌─────────────────────────────────────────────────────────┐   │",
            "│  │  If you agree, execute this trade now:                  │   │",
            "│  │                                                          │   │",
            f"│  │     {self.suggested_side} at market{' ' * 37}│   │",
            "│  │     (You decide the size)                                │   │",
            "│  └─────────────────────────────────────────────────────────┘   │",
            "│                                                                 │",
            f"│  ⏱️  Expires in {mins}m {secs:02d}s{' ' * 44}│",
            "│                                                                 │",
            "│  [A] Approve    [R] Reject    [D] Dismiss                      │",
            "╰─────────────────────────────────────────────────────────────────╯",
        ]
        return "\n".join(lines)
