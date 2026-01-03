"""
Sentinel Agent - The watchful, conservative market monitor.

Identity: Watchful, conservative, boringly predictable.

The Sentinel:
- Continuously watches user-defined markets
- Detects when pre-agreed conditions are met
- Produces single, risk-aware trade proposals

It does NOT:
- Execute trades
- Autonomously size positions
- Optimize for PnL or ROI
"""

import asyncio
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Deque, Dict, List, Optional
import structlog

from polycli.sentinel.models import (
    ProposalStatus,
    RiskStatus,
    SentinelConfig,
    SentinelProposal,
    SentinelRiskSnapshot,
    TriggerCondition,
    WatchedMarket,
)
from polycli.sentinel.triggers import MarketState, TriggerEvaluator

logger = structlog.get_logger(__name__)


class ProposalQueue:
    """Thread-safe queue for pending proposals with expiry management."""

    def __init__(self, max_size: int = 50):
        self._proposals: Deque[SentinelProposal] = deque(maxlen=max_size)
        self._by_id: Dict[str, SentinelProposal] = {}

    def add(self, proposal: SentinelProposal) -> None:
        """Add a proposal to the queue."""
        self._proposals.append(proposal)
        self._by_id[proposal.id] = proposal

    def get_pending(self) -> List[SentinelProposal]:
        """Get all pending (valid) proposals."""
        self._expire_old()
        return [p for p in self._proposals if p.status == ProposalStatus.PENDING]

    def get_by_id(self, proposal_id: str) -> Optional[SentinelProposal]:
        """Get a proposal by ID."""
        return self._by_id.get(proposal_id)

    def approve(self, proposal_id: str) -> Optional[SentinelProposal]:
        """Mark a proposal as approved."""
        proposal = self._by_id.get(proposal_id)
        if proposal and proposal.is_valid():
            proposal.mark_approved()
            return proposal
        return None

    def reject(self, proposal_id: str) -> Optional[SentinelProposal]:
        """Mark a proposal as rejected."""
        proposal = self._by_id.get(proposal_id)
        if proposal:
            proposal.mark_rejected()
            return proposal
        return None

    def _expire_old(self) -> None:
        """Mark expired proposals."""
        now = datetime.utcnow()
        for proposal in self._proposals:
            if proposal.status == ProposalStatus.PENDING and now > proposal.expires_at:
                proposal.mark_expired()

    def stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        self._expire_old()
        return {
            "total": len(self._proposals),
            "pending": sum(
                1 for p in self._proposals if p.status == ProposalStatus.PENDING
            ),
            "approved": sum(
                1 for p in self._proposals if p.status == ProposalStatus.APPROVED
            ),
            "rejected": sum(
                1 for p in self._proposals if p.status == ProposalStatus.REJECTED
            ),
            "expired": sum(
                1 for p in self._proposals if p.status == ProposalStatus.EXPIRED
            ),
        }


class SentinelAgent:
    """The Sentinel Agent - watchful, conservative, boringly predictable.

    Lifecycle:
    1. Configure with watched markets and triggers
    2. Start monitoring loop
    3. When conditions fire, generate proposals
    4. Surface proposals to user for approval
    5. User decides to execute or not

    The Sentinel NEVER executes trades.
    """

    def __init__(
        self,
        config: SentinelConfig,
        risk_guard: Any,  # Type hint as Any to avoid circular import
        get_market_state: Optional[Callable[[str, str], MarketState]] = None,
        on_proposal: Optional[Callable[[SentinelProposal], None]] = None,
        emit_event: Optional[Callable[[str, Dict], None]] = None,
    ):
        """Initialize the Sentinel Agent.

        Args:
            config: Sentinel configuration
            risk_guard: RiskGuard instance for risk context (read-only)
            get_market_state: Callback to fetch current market state
            on_proposal: Callback when a new proposal is generated
            emit_event: Callback for telemetry events
        """
        self.config = config
        self._risk_guard = risk_guard
        self._get_market_state = get_market_state
        self._on_proposal = on_proposal
        self._emit_event = emit_event or (lambda *args: None)

        # Core components
        self._evaluator = TriggerEvaluator()
        self._proposals = ProposalQueue()

        # Rate limiting
        self._proposals_this_hour: List[datetime] = []
        self._last_global_proposal: Optional[datetime] = None
        self._market_cooldowns: Dict[str, datetime] = {}

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            "Sentinel Agent initialized",
            watched_markets=len(config.watched_markets),
            poll_interval=config.poll_interval_seconds,
        )

    # =========================================================================
    # Public API
    # =========================================================================

    async def start(self) -> None:
        """Start the monitoring loop."""
        if self._running:
            logger.warning("Sentinel already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("Sentinel monitoring started")
        self._emit_event("sentinel.started", {"config": self.config.to_dict()})

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sentinel monitoring stopped")
        self._emit_event("sentinel.stopped", {})

    def get_pending_proposals(self) -> List[SentinelProposal]:
        """Get all pending proposals awaiting user decision."""
        return self._proposals.get_pending()

    def approve_proposal(self, proposal_id: str) -> Optional[SentinelProposal]:
        """Approve a proposal (user chose to act)."""
        proposal = self._proposals.approve(proposal_id)
        if proposal:
            self._emit_event(
                "sentinel.proposal.decided",
                {
                    "proposal_id": proposal_id,
                    "decision": "approved",
                    "latency_seconds": (
                        proposal.user_decision_at - proposal.created_at
                    ).total_seconds()
                    if proposal.user_decision_at
                    else 0,
                },
            )
            logger.info("Proposal approved", proposal_id=proposal_id)
        return proposal

    def reject_proposal(self, proposal_id: str) -> Optional[SentinelProposal]:
        """Reject a proposal (user chose not to act)."""
        proposal = self._proposals.reject(proposal_id)
        if proposal:
            self._emit_event(
                "sentinel.proposal.decided",
                {
                    "proposal_id": proposal_id,
                    "decision": "rejected",
                    "latency_seconds": (
                        proposal.user_decision_at - proposal.created_at
                    ).total_seconds()
                    if proposal.user_decision_at
                    else 0,
                },
            )
            logger.info("Proposal rejected", proposal_id=proposal_id)
        return proposal

    def get_stats(self) -> Dict[str, Any]:
        """Get Sentinel statistics."""
        return {
            "running": self._running,
            "proposals": self._proposals.stats(),
            "triggers": self._evaluator.get_stats(),
            "watched_markets": len(self.config.watched_markets),
            "proposals_this_hour": len(self._proposals_this_hour),
        }

    # =========================================================================
    # Monitoring Loop
    # =========================================================================

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop - runs continuously while active."""
        logger.info("Monitoring loop started")

        while self._running:
            try:
                await self._check_all_markets()
                await asyncio.sleep(self.config.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in monitoring loop", error=str(e))
                await asyncio.sleep(self.config.poll_interval_seconds)

        logger.info("Monitoring loop ended")

    async def _check_all_markets(self) -> None:
        """Check all watched markets for trigger conditions."""
        for watched in self.config.watched_markets:
            try:
                await self._check_market(watched)
            except Exception as e:
                logger.exception(
                    "Error checking market",
                    market_id=watched.market_id,
                    error=str(e),
                )

    async def _check_market(self, watched: WatchedMarket) -> None:
        """Check a single market for trigger conditions."""
        # Get current market state
        if not self._get_market_state:
            return

        state = self._get_market_state(watched.market_id, watched.provider)
        if not state:
            return

        # Update history
        self._evaluator.update_history(
            watched.market_id,
            price=(state.best_bid + state.best_ask) / 2,
        )

        # Check each trigger
        for trigger in watched.triggers:
            await self._check_trigger(watched, trigger, state)

    async def _check_trigger(
        self,
        watched: WatchedMarket,
        trigger: TriggerCondition,
        state: MarketState,
    ) -> None:
        """Check if a trigger condition is met and generate proposal if so."""
        # Evaluate the trigger
        fires, current_value = self._evaluator.evaluate(trigger, state)

        if not fires:
            return

        # Check rate limits
        if not self._can_generate_proposal(watched.market_id):
            logger.debug(
                "Proposal suppressed by rate limit",
                market_id=watched.market_id,
                trigger_type=trigger.trigger_type.value,
            )
            return

        # Fetch risk context
        risk_snapshot = await self._fetch_risk_snapshot(watched.provider)

        # Check if risk blocks proposal
        block_reason = risk_snapshot.should_block_proposal()
        if block_reason:
            logger.info(
                "Proposal suppressed by risk guard",
                market_id=watched.market_id,
                trigger_type=trigger.trigger_type.value,
                reason=block_reason,
            )
            self._emit_event(
                "sentinel.proposal.suppressed",
                {
                    "market_id": watched.market_id,
                    "trigger_type": trigger.trigger_type.value,
                    "reason": block_reason,
                },
            )
            return

        # Generate proposal
        proposal = self._create_proposal(
            watched=watched,
            trigger=trigger,
            state=state,
            risk_snapshot=risk_snapshot,
            current_value=current_value,
        )

        # Record the trigger fire
        if current_value is not None:
            self._evaluator.record_fire(watched.market_id, trigger, current_value)

        # Update rate limiting
        self._record_proposal(watched.market_id)

        # Add to queue and notify
        self._proposals.add(proposal)

        if self._on_proposal:
            self._on_proposal(proposal)

        self._emit_event("sentinel.proposal.created", proposal.to_dict())

        logger.info(
            "Proposal generated",
            proposal_id=proposal.id,
            market_id=watched.market_id,
            trigger_type=trigger.trigger_type.value,
            side=trigger.suggested_side,
        )

    # =========================================================================
    # Proposal Generation
    # =========================================================================

    def _create_proposal(
        self,
        watched: WatchedMarket,
        trigger: TriggerCondition,
        state: MarketState,
        risk_snapshot: SentinelRiskSnapshot,
        current_value: Optional[Decimal],
    ) -> SentinelProposal:
        """Create an immutable proposal from trigger fire."""
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=watched.expiry_seconds)

        market_snapshot = state.to_snapshot()
        risk_summary = risk_snapshot.compute_summary()

        return SentinelProposal(
            trigger_type=trigger.trigger_type.value,
            trigger_threshold=trigger.threshold,
            trigger_description=trigger.describe(current_value),
            market_snapshot=market_snapshot,
            risk_snapshot=risk_snapshot,
            risk_summary=risk_summary,
            suggested_side=trigger.suggested_side,
            indicative_size_usd=None,  # User decides sizing
            created_at=now,
            expires_at=expires_at,
        )

    # =========================================================================
    # Risk Integration (Read-Only)
    # =========================================================================

    async def _fetch_risk_snapshot(self, provider: str) -> SentinelRiskSnapshot:
        """Fetch current risk context (read-only)."""
        if not self._risk_guard:
            # Return permissive defaults if no risk guard
            return SentinelRiskSnapshot(
                status=RiskStatus.GREEN,
                circuit_breaker_active=False,
                remaining_position_budget_usd=Decimal("1000"),
                remaining_loss_budget_usd=Decimal("100"),
                risk_score=0.0,
                total_portfolio_value=Decimal("10000"),
                available_balance=Decimal("5000"),
            )

        try:
            ctx = await self._risk_guard.get_risk_context(provider)

            # Map RiskStatus from context
            status = RiskStatus.GREEN
            if hasattr(ctx, "status"):
                status_map = {
                    "green": RiskStatus.GREEN,
                    "yellow": RiskStatus.YELLOW,
                    "red": RiskStatus.RED,
                }
                status = status_map.get(ctx.status.value.lower(), RiskStatus.GREEN)

            return SentinelRiskSnapshot(
                status=status,
                circuit_breaker_active=ctx.circuit_breaker_active,
                remaining_position_budget_usd=ctx.remaining_position_budget_usd,
                remaining_loss_budget_usd=ctx.remaining_loss_budget_usd,
                risk_score=ctx.risk_score_current,
                total_portfolio_value=ctx.total_portfolio_value,
                available_balance=ctx.available_balance,
            )
        except Exception as e:
            logger.exception("Error fetching risk context", error=str(e))
            # Return conservative defaults on error
            return SentinelRiskSnapshot(
                status=RiskStatus.YELLOW,
                circuit_breaker_active=False,
                remaining_position_budget_usd=Decimal("0"),
                remaining_loss_budget_usd=Decimal("0"),
                risk_score=50.0,
                total_portfolio_value=Decimal("0"),
                available_balance=Decimal("0"),
            )

    # =========================================================================
    # Rate Limiting & Guardrails
    # =========================================================================

    def _can_generate_proposal(self, market_id: str) -> bool:
        """Check if we can generate a proposal (rate limit checks)."""
        now = datetime.utcnow()

        # Check global cooldown
        if self._last_global_proposal:
            elapsed = (now - self._last_global_proposal).total_seconds()
            if elapsed < self.config.global_cooldown_seconds:
                return False

        # Check per-market cooldown
        if market_id in self._market_cooldowns:
            elapsed = (now - self._market_cooldowns[market_id]).total_seconds()
            # Find the market config for cooldown
            for watched in self.config.watched_markets:
                if watched.market_id == market_id:
                    if elapsed < watched.cooldown_seconds:
                        return False
                    break

        # Check hourly rate limit
        cutoff = now - timedelta(hours=1)
        self._proposals_this_hour = [t for t in self._proposals_this_hour if t > cutoff]
        if len(self._proposals_this_hour) >= self.config.max_proposals_per_hour:
            return False

        return True

    def _record_proposal(self, market_id: str) -> None:
        """Record that a proposal was generated (for rate limiting)."""
        now = datetime.utcnow()
        self._last_global_proposal = now
        self._market_cooldowns[market_id] = now
        self._proposals_this_hour.append(now)


# =============================================================================
# Factory Functions
# =============================================================================


def create_sentinel_from_config(
    config_dict: Dict[str, Any],
    risk_guard: Any,
    get_market_state: Optional[Callable] = None,
    on_proposal: Optional[Callable] = None,
) -> SentinelAgent:
    """Create a Sentinel Agent from a configuration dictionary.

    Example config:
    {
        "watched_markets": [
            {
                "market_id": "0x123...",
                "provider": "polymarket",
                "triggers": [
                    {"type": "price_below", "threshold": "0.45", "side": "BUY"},
                    {"type": "spread_above", "threshold": "0.05", "side": "SELL"}
                ],
                "cooldown_seconds": 300,
                "expiry_seconds": 120
            }
        ],
        "global_cooldown_seconds": 60,
        "max_proposals_per_hour": 10
    }
    """
    from polycli.sentinel.models import TriggerCondition, TriggerType, WatchedMarket

    watched_markets = []
    for market_cfg in config_dict.get("watched_markets", []):
        triggers = []
        for trig_cfg in market_cfg.get("triggers", []):
            trigger = TriggerCondition(
                trigger_type=TriggerType(trig_cfg["type"]),
                threshold=Decimal(str(trig_cfg["threshold"])),
                suggested_side=trig_cfg["side"],
                debounce_seconds=trig_cfg.get("debounce_seconds", 60),
            )
            triggers.append(trigger)

        watched = WatchedMarket.create(
            market_id=market_cfg["market_id"],
            provider=market_cfg["provider"],
            triggers=triggers,
            cooldown_seconds=market_cfg.get("cooldown_seconds", 300),
            expiry_seconds=market_cfg.get("expiry_seconds", 120),
        )
        watched_markets.append(watched)

    config = SentinelConfig.create(
        watched_markets=watched_markets,
        global_cooldown_seconds=config_dict.get("global_cooldown_seconds", 60),
        max_proposals_per_hour=config_dict.get("max_proposals_per_hour", 10),
        poll_interval_seconds=config_dict.get("poll_interval_seconds", 5.0),
        enable_news_correlation=config_dict.get("enable_news_correlation", False),
    )

    return SentinelAgent(
        config=config,
        risk_guard=risk_guard,
        get_market_state=get_market_state,
        on_proposal=on_proposal,
    )
