"""
Sentinel trigger evaluation engine.

Pure, deterministic logic for evaluating market conditions.
No LLM, no fuzzy logic - just predicate evaluation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import structlog

from polycli.sentinel.models import (
    TriggerCondition,
    TriggerType,
    MarketSnapshot,
)

logger = structlog.get_logger(__name__)


@dataclass
class MarketState:
    """Current state of a market for trigger evaluation."""

    market_id: str
    provider: str
    question: str
    status: str  # "active", "halted", etc.
    best_bid: Decimal
    best_ask: Decimal
    spread: Decimal
    bid_depth_usd: Decimal
    ask_depth_usd: Decimal
    imbalance: float
    timestamp: datetime

    # For state transition detection
    prev_status: Optional[str] = None

    def to_snapshot(self) -> MarketSnapshot:
        """Convert to immutable snapshot."""
        return MarketSnapshot(
            market_id=self.market_id,
            provider=self.provider,
            question=self.question,
            best_bid=self.best_bid,
            best_ask=self.best_ask,
            spread=self.spread,
            bid_depth_usd=self.bid_depth_usd,
            ask_depth_usd=self.ask_depth_usd,
            imbalance=self.imbalance,
            captured_at=self.timestamp,
        )


@dataclass
class PriceHistory:
    """Recent price/volume history for a market."""

    prices: List[Tuple[datetime, Decimal]] = field(default_factory=list)
    volumes: List[Tuple[datetime, Decimal]] = field(default_factory=list)
    max_history_seconds: int = 7200  # 2 hours

    def add_price(self, timestamp: datetime, price: Decimal) -> None:
        """Add a price point."""
        self.prices.append((timestamp, price))
        self._cleanup()

    def add_volume(self, timestamp: datetime, volume: Decimal) -> None:
        """Add a volume point."""
        self.volumes.append((timestamp, volume))
        self._cleanup()

    def _cleanup(self) -> None:
        """Remove old data points."""
        cutoff = datetime.utcnow() - timedelta(seconds=self.max_history_seconds)
        self.prices = [(t, p) for t, p in self.prices if t > cutoff]
        self.volumes = [(t, v) for t, v in self.volumes if t > cutoff]

    def volume_since(self, seconds: int) -> Decimal:
        """Get total volume in the last N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        return sum(v for t, v in self.volumes if t > cutoff)

    def avg_volume(self, seconds: int) -> Decimal:
        """Get average volume per second over N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        volumes = [v for t, v in self.volumes if t > cutoff]
        if not volumes:
            return Decimal("0")
        return sum(volumes) / len(volumes)

    def price_change_pct(self, seconds: int) -> Decimal:
        """Get price change percentage over last N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        recent = [(t, p) for t, p in self.prices if t > cutoff]
        if len(recent) < 2:
            return Decimal("0")
        oldest_price = recent[0][1]
        newest_price = recent[-1][1]
        if oldest_price == 0:
            return Decimal("0")
        return (newest_price - oldest_price) / oldest_price


@dataclass
class TriggerState:
    """Mutable state for tracking trigger firing and debounce."""

    last_fired_at: Optional[datetime] = None
    last_value_when_fired: Optional[Decimal] = None
    crossed_hysteresis: bool = True
    fire_count: int = 0

    def record_fire(self, value: Decimal) -> None:
        """Record that the trigger fired."""
        self.last_fired_at = datetime.utcnow()
        self.last_value_when_fired = value
        self.crossed_hysteresis = False
        self.fire_count += 1

    def check_hysteresis(
        self,
        current_value: Decimal,
        threshold: Decimal,
        hysteresis_pct: Decimal,
        is_above_trigger: bool,
    ) -> None:
        """Update hysteresis state based on current value.

        For 'above' triggers: must drop below threshold - hysteresis before re-trigger
        For 'below' triggers: must rise above threshold + hysteresis before re-trigger
        """
        if self.crossed_hysteresis:
            return  # Already crossed, no need to check

        hysteresis_margin = threshold * hysteresis_pct

        if is_above_trigger:
            # For PRICE_ABOVE: must drop below (threshold - margin) to reset
            if current_value < threshold - hysteresis_margin:
                self.crossed_hysteresis = True
        else:
            # For PRICE_BELOW: must rise above (threshold + margin) to reset
            if current_value > threshold + hysteresis_margin:
                self.crossed_hysteresis = True


class TriggerEvaluator:
    """Evaluates trigger conditions against market state.

    This is a pure evaluation engine with no side effects.
    """

    def __init__(self):
        # Track state per (market_id, trigger) pair
        self._trigger_states: Dict[str, TriggerState] = {}
        self._histories: Dict[str, PriceHistory] = {}

    def _get_trigger_key(self, market_id: str, trigger: TriggerCondition) -> str:
        """Generate unique key for a market+trigger pair."""
        return f"{market_id}:{trigger.trigger_type.value}:{trigger.threshold}"

    def _get_state(self, market_id: str, trigger: TriggerCondition) -> TriggerState:
        """Get or create trigger state."""
        key = self._get_trigger_key(market_id, trigger)
        if key not in self._trigger_states:
            self._trigger_states[key] = TriggerState()
        return self._trigger_states[key]

    def _get_history(self, market_id: str) -> PriceHistory:
        """Get or create price history."""
        if market_id not in self._histories:
            self._histories[market_id] = PriceHistory()
        return self._histories[market_id]

    def update_history(
        self,
        market_id: str,
        price: Optional[Decimal] = None,
        volume: Optional[Decimal] = None,
    ) -> None:
        """Update price/volume history for a market."""
        history = self._get_history(market_id)
        now = datetime.utcnow()
        if price is not None:
            history.add_price(now, price)
        if volume is not None:
            history.add_volume(now, volume)

    def evaluate(
        self,
        trigger: TriggerCondition,
        state: MarketState,
    ) -> Tuple[bool, Optional[Decimal]]:
        """Evaluate if a trigger condition is met.

        Returns:
            (should_fire, current_value) tuple
        """
        history = self._get_history(state.market_id)
        trigger_state = self._get_state(state.market_id, trigger)
        now = datetime.utcnow()

        # Check debounce
        if trigger_state.last_fired_at:
            elapsed = (now - trigger_state.last_fired_at).total_seconds()
            if elapsed < trigger.debounce_seconds:
                return (False, None)

        # Evaluate based on trigger type
        match trigger.trigger_type:
            case TriggerType.PRICE_BELOW:
                current = state.best_bid
                trigger_state.check_hysteresis(
                    current,
                    trigger.threshold,
                    trigger.hysteresis_pct,
                    is_above_trigger=False,
                )
                if not trigger_state.crossed_hysteresis:
                    return (False, current)
                fires = current <= trigger.threshold
                return (fires, current)

            case TriggerType.PRICE_ABOVE:
                current = state.best_ask
                trigger_state.check_hysteresis(
                    current,
                    trigger.threshold,
                    trigger.hysteresis_pct,
                    is_above_trigger=True,
                )
                if not trigger_state.crossed_hysteresis:
                    return (False, current)
                fires = current >= trigger.threshold
                return (fires, current)

            case TriggerType.SPREAD_ABOVE:
                current = state.spread
                fires = current >= trigger.threshold
                return (fires, current)

            case TriggerType.SPREAD_BELOW:
                current = state.spread
                fires = current <= trigger.threshold
                return (fires, current)

            case TriggerType.VOLUME_SPIKE:
                recent = history.volume_since(trigger.time_window_seconds)
                baseline = history.avg_volume(trigger.baseline_window_seconds)
                if baseline == 0:
                    return (False, Decimal("0"))
                ratio = recent / baseline
                fires = ratio > trigger.threshold
                return (fires, ratio)

            case TriggerType.IMBALANCE_BUY:
                current = Decimal(str(state.imbalance))
                fires = current >= trigger.threshold
                return (fires, current)

            case TriggerType.IMBALANCE_SELL:
                current = Decimal(str(state.imbalance))
                fires = current <= -trigger.threshold
                return (fires, current)

            case TriggerType.MARKET_REOPEN:
                fires = (
                    state.prev_status is not None
                    and state.prev_status != "active"
                    and state.status == "active"
                )
                return (fires, None)

            case TriggerType.NEWS_CORRELATION:
                # This requires external news data - for now just check price move
                price_change = history.price_change_pct(trigger.time_window_seconds)
                fires = abs(price_change) >= trigger.threshold
                return (fires, price_change)

            case _:
                logger.warning(
                    "Unknown trigger type", trigger_type=trigger.trigger_type
                )
                return (False, None)

    def record_fire(
        self,
        market_id: str,
        trigger: TriggerCondition,
        value: Decimal,
    ) -> None:
        """Record that a trigger fired (for debounce tracking)."""
        state = self._get_state(market_id, trigger)
        state.record_fire(value)
        logger.info(
            "Trigger fired",
            market_id=market_id,
            trigger_type=trigger.trigger_type.value,
            threshold=str(trigger.threshold),
            value=str(value),
            fire_count=state.fire_count,
        )

    def can_fire(self, market_id: str, trigger: TriggerCondition) -> bool:
        """Check if trigger can fire (debounce check only)."""
        state = self._get_state(market_id, trigger)
        if state.last_fired_at is None:
            return True
        elapsed = (datetime.utcnow() - state.last_fired_at).total_seconds()
        return elapsed >= trigger.debounce_seconds

    def get_stats(self) -> Dict[str, int]:
        """Get trigger firing statistics."""
        return {key: state.fire_count for key, state in self._trigger_states.items()}

    def reset(self) -> None:
        """Reset all trigger states (for testing)."""
        self._trigger_states.clear()
        self._histories.clear()
