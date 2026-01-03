"""Main risk guard implementation."""
import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Dict, List, Optional
import structlog

from .config import RiskConfig
from .context import RiskContext, RiskStatus
from .models import (
    RiskCheckResult,
    RiskViolation,
    RiskViolationType,
    RiskErrorCode,
    RiskMetrics,
    TradeAuditLog,
)
from .store import RiskAuditStore

logger = structlog.get_logger()


class RiskGuard:
    """
    Pre-trade risk validation middleware.

    All trading operations must pass through this guard before execution.
    """

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        store: Optional[RiskAuditStore] = None,
        get_balance_fn: Optional[Callable] = None,
        get_positions_fn: Optional[Callable] = None,
        get_price_fn: Optional[Callable] = None,
    ):
        self.config = config or RiskConfig.load()
        self.store = store or RiskAuditStore()
        self._get_balance = get_balance_fn
        self._get_positions = get_positions_fn
        self._get_price = get_price_fn
        self._peak_balance: Dict[str, Decimal] = {}  # Track peak for drawdown

    async def check_trade(
        self,
        token_id: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        provider: str = "polymarket",
        agent_id: Optional[str] = None,
        agent_reasoning: Optional[str] = None,
    ) -> RiskCheckResult:
        """
        Validate a trade against all risk parameters.

        Args:
            token_id: The token/market to trade
            side: "BUY" or "SELL"
            amount: Dollar amount (for buys) or shares (for sells)
            price: Optional limit price
            provider: Trading provider
            agent_id: ID of agent if agent-initiated
            agent_reasoning: LLM reasoning if agent-initiated

        Returns:
            RiskCheckResult with approval status and any violations
        """
        violations: List[RiskViolation] = []
        warnings: List[str] = []
        risk_score = 0.0

        config = self.config.get_for_provider(provider)
        amount_decimal = Decimal(str(amount))
        price_decimal = Decimal(str(price)) if price else None

        # Get current state
        metrics = await self._get_current_metrics(provider)

        # 1. Check master trading switch
        if not config.trading_enabled:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.MANUAL_BLOCK,
                    message="Trading is globally disabled",
                    current_value=0,
                    limit_value=0,
                    severity="critical",
                    error_code=RiskErrorCode.ERR_TRADING_DISABLED,
                )
            )

        # 2. Check agent permission
        if agent_id and not config.agents_enabled:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.MANUAL_BLOCK,
                    message="Autonomous agent trading is disabled",
                    current_value=0,
                    limit_value=0,
                    severity="critical",
                    error_code=RiskErrorCode.ERR_AGENTS_DISABLED,
                )
            )

        # 3. Check circuit breaker
        if config.circuit_breaker_enabled and self.store.is_circuit_breaker_active(
            provider
        ):
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.CIRCUIT_BREAKER_ACTIVE,
                    message="Circuit breaker is active - trading paused",
                    current_value=0,
                    limit_value=0,
                    severity="critical",
                    error_code=RiskErrorCode.ERR_CIRCUIT_BREAKER,
                )
            )

        # 4. Check position size limits (for buys)
        if side.upper() == "BUY":
            # Absolute limit
            if amount_decimal > config.max_position_size_usd:
                violations.append(
                    RiskViolation(
                        violation_type=RiskViolationType.POSITION_SIZE_EXCEEDED,
                        message=f"Trade size ${amount_decimal:.2f} exceeds max ${config.max_position_size_usd:.2f}",
                        current_value=float(amount_decimal),
                        limit_value=float(config.max_position_size_usd),
                        severity="high",
                        error_code=RiskErrorCode.ERR_POS_SIZE_ABSOLUTE,
                        suggested_value=float(config.max_position_size_usd),
                    )
                )
                risk_score += 30

            # Percentage limit
            if metrics.total_portfolio_value > 0:
                position_pct = amount_decimal / metrics.total_portfolio_value
                if position_pct > config.max_position_size_pct:
                    violations.append(
                        RiskViolation(
                            violation_type=RiskViolationType.POSITION_SIZE_EXCEEDED,
                            message=f"Trade is {position_pct:.1%} of portfolio, max is {config.max_position_size_pct:.1%}",
                            current_value=float(position_pct),
                            limit_value=float(config.max_position_size_pct),
                            severity="high",
                            error_code=RiskErrorCode.ERR_POS_SIZE_PERCENT,
                            suggested_value=float(config.max_position_size_pct),
                        )
                    )
                    risk_score += 25

        # 5. Check balance
        if side.upper() == "BUY" and amount_decimal > metrics.available_balance:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.INSUFFICIENT_BALANCE,
                    message=f"Insufficient balance: have ${metrics.available_balance:.2f}, need ${amount_decimal:.2f}",
                    current_value=float(metrics.available_balance),
                    limit_value=float(amount_decimal),
                    severity="high",
                    error_code=RiskErrorCode.ERR_INSUFFICIENT_BALANCE,
                    suggested_value=float(metrics.available_balance),
                )
            )

        # 6. Check daily loss limit
        daily_loss = abs(min(Decimal("0"), metrics.daily_pnl))
        remaining_loss_budget = config.daily_loss_limit_usd - daily_loss
        if daily_loss >= config.daily_loss_limit_usd:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.DAILY_LOSS_LIMIT_EXCEEDED,
                    message=f"Daily loss ${daily_loss:.2f} exceeds limit ${config.daily_loss_limit_usd:.2f}",
                    current_value=float(daily_loss),
                    limit_value=float(config.daily_loss_limit_usd),
                    severity="critical",
                    error_code=RiskErrorCode.ERR_DAILY_LOSS,
                    suggested_value=float(max(Decimal("0"), remaining_loss_budget)),
                )
            )
            risk_score += 40

            # Trigger circuit breaker
            if config.circuit_breaker_enabled:
                self.store.trigger_circuit_breaker(
                    reason=f"Daily loss limit exceeded: ${daily_loss:.2f}",
                    cooldown_minutes=config.circuit_breaker_cooldown_minutes,
                    provider=provider,
                )

        # 7. Check drawdown
        if metrics.max_drawdown_current > config.max_drawdown_pct:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.MAX_DRAWDOWN_EXCEEDED,
                    message=f"Drawdown {metrics.max_drawdown_current:.1%} exceeds max {config.max_drawdown_pct:.1%}",
                    current_value=float(metrics.max_drawdown_current),
                    limit_value=float(config.max_drawdown_pct),
                    severity="critical",
                    error_code=RiskErrorCode.ERR_MAX_DRAWDOWN,
                    suggested_value=float(config.max_drawdown_pct),
                )
            )
            risk_score += 35

        # 8. Check trade frequency
        now = datetime.utcnow()
        trades_last_minute = self.store.get_trades_count_since(
            now - timedelta(minutes=1), provider
        )
        remaining_minute = config.max_trades_per_minute - trades_last_minute
        if trades_last_minute >= config.max_trades_per_minute:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.TRADE_FREQUENCY_EXCEEDED,
                    message=f"Trade frequency exceeded: {trades_last_minute}/min (max {config.max_trades_per_minute})",
                    current_value=trades_last_minute,
                    limit_value=config.max_trades_per_minute,
                    severity="medium",
                    error_code=RiskErrorCode.ERR_FREQ_MINUTE,
                    suggested_value=float(max(0, remaining_minute)),
                )
            )
            risk_score += 15

        trades_last_hour = self.store.get_trades_count_since(
            now - timedelta(hours=1), provider
        )
        remaining_hour = config.max_trades_per_hour - trades_last_hour
        if trades_last_hour >= config.max_trades_per_hour:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.TRADE_FREQUENCY_EXCEEDED,
                    message=f"Hourly trade limit exceeded: {trades_last_hour}/hr (max {config.max_trades_per_hour})",
                    current_value=trades_last_hour,
                    limit_value=config.max_trades_per_hour,
                    severity="medium",
                    error_code=RiskErrorCode.ERR_FREQ_HOUR,
                    suggested_value=float(max(0, remaining_hour)),
                )
            )
            risk_score += 15

        # 9. Check price sanity (if we have a price and can get market price)
        if price_decimal and self._get_price:
            try:
                market_price = await self._get_price(token_id, side)
                if market_price:
                    deviation = abs(price_decimal - market_price) / market_price
                    if deviation > config.max_price_deviation_pct:
                        violations.append(
                            RiskViolation(
                                violation_type=RiskViolationType.PRICE_DEVIATION_TOO_HIGH,
                                message=f"Price {price_decimal} deviates {deviation:.1%} from market {market_price}",
                                current_value=float(deviation),
                                limit_value=float(config.max_price_deviation_pct),
                                severity="medium",
                                error_code=RiskErrorCode.ERR_PRICE_DEVIATION,
                                suggested_value=float(config.max_price_deviation_pct),
                            )
                        )
                        risk_score += 20
            except Exception as e:
                warnings.append(f"Could not verify price against market: {e}")

        # 10. Add warnings for elevated risk (but not blocking)
        if metrics.largest_position_pct > Decimal("0.15"):
            warnings.append(
                f"Largest position is {metrics.largest_position_pct:.1%} of portfolio"
            )

        if metrics.trades_today > 20:
            warnings.append(
                f"High trading activity today: {metrics.trades_today} trades"
            )

        # Calculate final result
        approved = len(violations) == 0
        risk_score = min(100, risk_score)  # Cap at 100

        result = RiskCheckResult(
            approved=approved,
            violations=violations,
            warnings=warnings,
            risk_score=risk_score,
        )

        # Log the attempt
        audit_log = TradeAuditLog(
            token_id=token_id,
            market_id="",  # Could be enriched
            side=side,
            amount=amount_decimal,
            price=price_decimal,
            provider=provider,
            approved=approved,
            violations=json.dumps([v.message for v in violations]),
            warnings=json.dumps(warnings),
            risk_score=risk_score,
            agent_id=agent_id,
            agent_reasoning=agent_reasoning,
            metrics_snapshot=json.dumps(
                {
                    "total_portfolio_value": float(metrics.total_portfolio_value),
                    "available_balance": float(metrics.available_balance),
                    "daily_pnl": float(metrics.daily_pnl),
                    "drawdown": float(metrics.max_drawdown_current),
                }
            ),
        )
        self.store.log_trade_attempt(audit_log)

        if not approved:
            logger.warning(
                "Trade rejected by risk guard",
                token_id=token_id,
                side=side,
                amount=amount,
                violations=[v.message for v in violations],
            )
        else:
            logger.info(
                "Trade approved by risk guard",
                token_id=token_id,
                side=side,
                amount=amount,
                risk_score=risk_score,
                warnings=warnings,
            )

        return result

    async def _get_current_metrics(self, provider: str) -> RiskMetrics:
        """Get current risk metrics."""
        metrics = RiskMetrics()

        try:
            if self._get_balance:
                balance_info = await self._get_balance(provider)
                metrics.available_balance = Decimal(str(balance_info.get("balance", 0)))
                metrics.total_portfolio_value = Decimal(
                    str(balance_info.get("total_value", balance_info.get("balance", 0)))
                )

            if self._get_positions:
                positions = await self._get_positions(provider)
                metrics.position_count = len(positions)

                if positions and metrics.total_portfolio_value > 0:
                    largest = (
                        max(
                            (
                                Decimal(str(p.get("size", 0)))
                                * Decimal(str(p.get("current_price", 0)))
                            )
                            for p in positions
                        )
                        if positions
                        else Decimal("0")
                    )
                    metrics.largest_position_pct = (
                        largest / metrics.total_portfolio_value
                    )

            # Track peak for drawdown
            if provider not in self._peak_balance:
                self._peak_balance[provider] = metrics.total_portfolio_value
            elif metrics.total_portfolio_value > self._peak_balance[provider]:
                self._peak_balance[provider] = metrics.total_portfolio_value

            if self._peak_balance[provider] > 0:
                metrics.max_drawdown_current = (
                    self._peak_balance[provider] - metrics.total_portfolio_value
                ) / self._peak_balance[provider]

            # Get trade count for today
            today_start = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            metrics.trades_today = self.store.get_trades_count_since(
                today_start, provider
            )

        except Exception as e:
            logger.error("Failed to get risk metrics", error=str(e))

        return metrics

    def update_config(self, **kwargs) -> None:
        """Update risk configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.config.save()
        logger.info("Risk config updated", updates=kwargs)

    def trigger_circuit_breaker(
        self, reason: str, cooldown_minutes: Optional[int] = None
    ) -> None:
        """Manually trigger circuit breaker."""
        cooldown = cooldown_minutes or self.config.circuit_breaker_cooldown_minutes
        self.store.trigger_circuit_breaker(reason, cooldown, "all")
        logger.warning(
            "Circuit breaker manually triggered",
            reason=reason,
            cooldown_minutes=cooldown,
        )

    def reset_circuit_breaker(self, provider: str = "all") -> None:
        """Reset circuit breaker (clear cooldown)."""
        # Insert a record with past cooldown to effectively reset
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                "INSERT INTO circuit_breaker_events (reason, cooldown_until, provider) VALUES (?, ?, ?)",
                ("Manual reset", datetime.utcnow() - timedelta(minutes=1), provider),
            )
        logger.info("Circuit breaker reset", provider=provider)

    async def get_risk_context(self, provider: str = "polymarket") -> RiskContext:
        """Get comprehensive risk context for proactive risk awareness.

        This method aggregates all risk-relevant state into a RiskContext
        dataclass that can be consumed by LLMs or monitoring systems.

        Args:
            provider: The trading provider to get context for.

        Returns:
            RiskContext with all current risk state and computed fields.
        """
        config = self.config.get_for_provider(provider)
        metrics = await self._get_current_metrics(provider)

        now = datetime.utcnow()

        daily_loss = abs(min(Decimal("0"), metrics.daily_pnl))
        remaining_loss_budget = config.daily_loss_limit_usd - daily_loss

        trades_last_minute = self.store.get_trades_count_since(
            now - timedelta(minutes=1), provider
        )
        trades_last_hour = self.store.get_trades_count_since(
            now - timedelta(hours=1), provider
        )

        remaining_trades_minute = config.max_trades_per_minute - trades_last_minute
        remaining_trades_hour = config.max_trades_per_hour - trades_last_hour

        remaining_position_budget = config.max_position_size_usd

        circuit_breaker_reason = ""
        if config.circuit_breaker_enabled and self.store.is_circuit_breaker_active(
            provider
        ):
            with sqlite3.connect(self.store.db_path) as conn:
                row = conn.execute(
                    "SELECT reason FROM circuit_breaker_events "
                    "WHERE (provider = ? OR provider = 'all') "
                    "ORDER BY triggered_at DESC LIMIT 1",
                    (provider,),
                ).fetchone()
                if row:
                    circuit_breaker_reason = row[0] or ""

        daily_pnl_pct = Decimal("0")
        if metrics.total_portfolio_value > 0:
            daily_pnl_pct = metrics.daily_pnl / metrics.total_portfolio_value

        risk_score = 0.0
        if not config.trading_enabled:
            risk_score = 100.0
        elif circuit_breaker_reason:
            risk_score = 100.0
        elif not config.agents_enabled:
            risk_score = 80.0
        else:
            if daily_loss > config.daily_loss_limit_usd * Decimal("0.8"):
                risk_score += 40
            if metrics.max_drawdown_current > config.max_drawdown_pct * Decimal("0.8"):
                risk_score += 30
            if trades_last_minute >= config.max_trades_per_minute * 0.8:
                risk_score += 20
            if trades_last_hour >= config.max_trades_per_hour * 0.8:
                risk_score += 10
            if metrics.largest_position_pct > config.max_position_size_pct:
                risk_score += 20

        risk_score = min(100.0, float(risk_score))

        if not config.trading_enabled or circuit_breaker_reason:
            status = RiskStatus.RED
        elif daily_loss > config.daily_loss_limit_usd * Decimal("0.8"):
            status = RiskStatus.YELLOW
        else:
            status = RiskStatus.GREEN

        return RiskContext(
            available_balance=metrics.available_balance,
            total_portfolio_value=metrics.total_portfolio_value,
            largest_position_pct=metrics.largest_position_pct,
            position_count=metrics.position_count,
            daily_pnl=metrics.daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            max_drawdown_current=metrics.max_drawdown_current,
            trades_today=metrics.trades_today,
            max_position_size_usd=config.max_position_size_usd,
            max_position_size_pct=config.max_position_size_pct,
            daily_loss_limit_usd=config.daily_loss_limit_usd,
            max_drawdown_pct=config.max_drawdown_pct,
            max_trades_per_minute=config.max_trades_per_minute,
            max_trades_per_hour=config.max_trades_per_hour,
            trades_last_minute=trades_last_minute,
            trades_last_hour=trades_last_hour,
            trading_enabled=config.trading_enabled,
            agents_enabled=config.agents_enabled,
            circuit_breaker_active=bool(circuit_breaker_reason),
            circuit_breaker_reason=circuit_breaker_reason,
            status=status,
            risk_score_current=risk_score,
            remaining_position_budget_usd=remaining_position_budget,
            remaining_loss_budget_usd=remaining_loss_budget,
            remaining_trades_this_minute=remaining_trades_minute,
            remaining_trades_this_hour=remaining_trades_hour,
        )
