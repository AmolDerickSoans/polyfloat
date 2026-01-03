"""Trading tools for agent use - wallet balance, order placement, trade history"""

import asyncio
import time
from typing import Dict, Any, Optional, List
import structlog
from polycli.models import Side
from polycli.providers.polymarket import PolyProvider
from polycli.providers.kalshi import KalshiProvider
from polycli.risk import RiskGuard
from polycli.risk.store import RiskAuditStore

logger = structlog.get_logger()


class ExecutionOutcomeLogger:
    """Helper to log execution outcomes."""

    def __init__(self, audit_store: Optional[RiskAuditStore] = None):
        self._audit_store = audit_store
        self._attempt_id: Optional[str] = None
        self._start_time: Optional[float] = None

    def start_execution(self, attempt_id: str) -> None:
        """Mark execution start for latency tracking."""
        self._attempt_id = attempt_id
        self._start_time = time.perf_counter()

    def log_success(
        self,
        order_id: str,
        filled_amount: Optional[float] = None,
    ) -> None:
        """Log successful execution."""
        if self._audit_store and self._attempt_id:
            latency_ms = (
                (time.perf_counter() - self._start_time) * 1000
                if self._start_time
                else None
            )
            self._audit_store.log_execution_outcome(
                attempt_id=self._attempt_id,
                execution_status="SUCCESS",
                order_id=order_id,
                filled_amount=filled_amount,
                latency_ms=latency_ms,
            )

    def log_failure(self, error: Optional[str] = None) -> None:
        """Log failed execution."""
        if self._audit_store and self._attempt_id:
            latency_ms = (
                (time.perf_counter() - self._start_time) * 1000
                if self._start_time
                else None
            )
            self._audit_store.log_execution_outcome(
                attempt_id=self._attempt_id,
                execution_status="FAILED",
                latency_ms=latency_ms,
            )

    def log_timeout(self) -> None:
        """Log timed out execution."""
        if self._audit_store and self._attempt_id:
            latency_ms = (
                (time.perf_counter() - self._start_time) * 1000
                if self._start_time
                else None
            )
            self._audit_store.log_execution_outcome(
                attempt_id=self._attempt_id,
                execution_status="TIMEOUT",
                latency_ms=latency_ms,
            )

    def reset(self) -> None:
        """Reset the logger for next use."""
        self._attempt_id = None
        self._start_time = None


class TradingTools:
    """Tools for trading operations"""

    def __init__(
        self,
        poly_provider: PolyProvider,
        kalshi_provider: Optional[KalshiProvider] = None,
        audit_store: Optional[RiskAuditStore] = None,
    ):
        self.poly = poly_provider
        self.kalshi = kalshi_provider
        self._paper_provider: Optional[Any] = None
        self._risk_guard: Optional[RiskGuard] = None
        self._execution_lock = asyncio.Lock()
        self._outcome_logger = ExecutionOutcomeLogger(audit_store)

    def _get_provider(self, provider: str = "polymarket"):
        """Get the appropriate provider (paper or real)."""
        from polycli.utils.config import get_paper_mode
        from polycli.paper import PaperTradingProvider

        if get_paper_mode():
            if self._paper_provider is None:
                self._paper_provider = PaperTradingProvider(self.poly)
            return self._paper_provider

        if provider.lower() == "polymarket":
            return self.poly
        elif provider.lower() == "kalshi" and self.kalshi:
            return self.kalshi
        return None

    def _get_risk_guard(self) -> RiskGuard:
        """Get or create risk guard instance."""
        if self._risk_guard is None:
            self._risk_guard = RiskGuard(
                get_balance_fn=self._get_balance_for_risk,
                get_positions_fn=self._get_positions_for_risk,
                get_price_fn=self._get_price_for_risk,
            )
        return self._risk_guard

    async def _get_balance_for_risk(
        self, provider: str = "polymarket"
    ) -> Dict[str, Any]:
        """Returns balance info for risk checks."""
        balance_info = await self.get_wallet_balance(provider)
        return {
            "balance": balance_info.get("balance", 0),
            "total_value": balance_info.get("balance", 0),
        }

    async def _get_positions_for_risk(
        self, provider: str = "polymarket"
    ) -> List[Dict[str, Any]]:
        """Returns positions for risk checks."""
        positions_info = await self.get_positions(provider)
        positions = positions_info.get("positions", [])
        return [
            {"size": pos.get("size", 0), "current_price": pos.get("avg_price", 0)}
            for pos in positions
        ]

    async def _get_price_for_risk(self, token_id: str, side: str) -> Optional[float]:
        """Returns market price for price sanity checks."""
        try:
            provider_obj = self._get_provider()
            if provider_obj is None:
                return None

            order_book = await provider_obj.get_orderbook(token_id)
            if order_book and order_book.bids and order_book.asks:
                return (order_book.bids[0].price + order_book.asks[0].price) / 2
            return None
        except Exception:
            return None

    async def get_wallet_balance(self, provider: str = "polymarket") -> Dict[str, Any]:
        """
        Get wallet balance for the specified provider.

        Args:
            provider: "polymarket" or "kalshi"

        Returns:
            Dict with balance information
        """
        try:
            provider_obj = self._get_provider(provider)
            if provider_obj is None:
                return {"error": "Invalid provider or provider not configured"}

            balance_info = await provider_obj.get_balance()
            return {
                "provider": provider.lower(),
                "balance": float(balance_info.get("balance", 0)),
                "currency": "USDC",
                "allowance": float(balance_info.get("allowance", 0)),
                "error": balance_info.get("error"),
            }
        except Exception as e:
            logger.error(
                "Failed to get wallet balance", provider=provider, error=str(e)
            )
            return {"error": str(e)}

    async def place_market_buy(
        self,
        token_id: str,
        amount: float,
        provider: str = "polymarket",
        agent_id: Optional[str] = None,
        agent_reasoning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a market buy order.

        Args:
            token_id: Token/market ID to buy
            amount: Dollar amount to spend
            provider: "polymarket" or "kalshi"
            agent_id: Optional agent ID for tracking
            agent_reasoning: Optional agent reasoning for tracking

        Returns:
            Dict with order result
        """
        attempt_id = f"buy_{token_id}_{int(time.time() * 1000)}"
        self._outcome_logger.start_execution(attempt_id)

        try:
            if provider.lower() == "kalshi":
                self._outcome_logger.log_failure("Kalshi not supported")
                return {
                    "success": False,
                    "error": "Only Polymarket supported currently",
                }

            provider_obj = self._get_provider(provider)

            risk_guard = self._get_risk_guard()
            risk_result = await risk_guard.check_trade(
                token_id=token_id,
                side="BUY",
                amount=amount,
                provider=provider,
                agent_id=agent_id,
                agent_reasoning=agent_reasoning,
            )

            if not risk_result.approved:
                self._outcome_logger.log_failure("Risk check failed")
                return {
                    "success": False,
                    "error": "Trade blocked by risk guard",
                    "violations": [v.message for v in risk_result.violations],
                    "risk_score": risk_result.risk_score,
                }

            async with self._execution_lock:
                balance_info = await provider_obj.get_balance()
                balance = float(balance_info.get("balance", 0))

                if amount > balance:
                    self._outcome_logger.log_failure("Insufficient balance")
                    return {
                        "success": False,
                        "error": f"Insufficient balance. Have: ${balance:.2f}, Need: ${amount:.2f}",
                    }

                order = await provider_obj.place_market_order(
                    token_id=token_id, side=Side.BUY, amount=amount
                )

            self._outcome_logger.log_success(order.id, amount)
            return {
                "success": True,
                "order_id": order.id,
                "token_id": token_id,
                "side": "BUY",
                "amount": amount,
                "status": order.status.value,
            }
        except Exception as e:
            self._outcome_logger.log_failure(str(e))
            logger.error(
                "Market buy failed", token_id=token_id, amount=amount, error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def place_market_sell(
        self,
        token_id: str,
        shares: float,
        provider: str = "polymarket",
        agent_id: Optional[str] = None,
        agent_reasoning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a market sell order.

        Args:
            token_id: Token/market ID to sell
            shares: Number of shares to sell
            provider: "polymarket" or "kalshi"
            agent_id: Optional agent ID for tracking
            agent_reasoning: Optional agent reasoning for tracking

        Returns:
            Dict with order result
        """
        attempt_id = f"sell_{token_id}_{int(time.time() * 1000)}"
        self._outcome_logger.start_execution(attempt_id)

        try:
            if provider.lower() == "kalshi":
                self._outcome_logger.log_failure("Kalshi not supported")
                return {
                    "success": False,
                    "error": "Only Polymarket supported currently",
                }

            provider_obj = self._get_provider(provider)

            risk_guard = self._get_risk_guard()
            risk_result = await risk_guard.check_trade(
                token_id=token_id,
                side="SELL",
                amount=shares,
                provider=provider,
                agent_id=agent_id,
                agent_reasoning=agent_reasoning,
            )

            if not risk_result.approved:
                self._outcome_logger.log_failure("Risk check failed")
                return {
                    "success": False,
                    "error": "Trade blocked by risk guard",
                    "violations": [v.message for v in risk_result.violations],
                    "risk_score": risk_result.risk_score,
                }

            async with self._execution_lock:
                order = await provider_obj.place_market_order(
                    token_id=token_id, side=Side.SELL, amount=shares
                )

            self._outcome_logger.log_success(order.id, shares)
            return {
                "success": True,
                "order_id": order.id,
                "token_id": token_id,
                "side": "SELL",
                "shares": shares,
                "status": order.status.value,
            }
        except Exception as e:
            self._outcome_logger.log_failure(str(e))
            logger.error(
                "Market sell failed", token_id=token_id, shares=shares, error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def get_trade_history(
        self,
        market_id: Optional[str] = None,
        provider: str = "polymarket",
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get trade history for the user.

        Args:
            market_id: Optional market ID to filter by
            provider: "polymarket" or "kalshi"
            limit: Max number of trades to return

        Returns:
            Dict with trade history
        """
        try:
            if provider.lower() == "kalshi":
                return {
                    "success": False,
                    "error": "Only Polymarket supported currently",
                }

            provider_obj = self._get_provider(provider)
            trades = await provider_obj.get_trades(market_id=market_id)

            trade_list = []
            for trade in trades[:limit]:
                trade_list.append(
                    {
                        "id": trade.id,
                        "market_id": trade.market_id,
                        "side": trade.side.value,
                        "price": trade.price,
                        "size": trade.size,
                        "total": trade.price * trade.size,
                        "timestamp": trade.timestamp,
                    }
                )

            return {
                "success": True,
                "provider": provider.lower(),
                "count": len(trade_list),
                "trades": trade_list,
            }
        except Exception as e:
            logger.error("Failed to get trade history", provider=provider, error=str(e))
            return {"success": False, "error": str(e)}

    async def get_positions(self, provider: str = "polymarket") -> Dict[str, Any]:
        """
        Get current positions.

        Args:
            provider: "polymarket" or "kalshi"

        Returns:
            Dict with positions
        """
        try:
            if provider.lower() == "kalshi" and self.kalshi:
                positions = await self.kalshi.get_positions()
                position_list = [
                    {
                        "market_id": pos.market_id,
                        "outcome": pos.outcome,
                        "size": pos.size,
                        "avg_price": pos.avg_price,
                        "realized_pnl": pos.realized_pnl,
                        "unrealized_pnl": pos.unrealized_pnl,
                    }
                    for pos in positions
                ]
                return {
                    "success": True,
                    "provider": "kalshi",
                    "count": len(position_list),
                    "positions": position_list,
                }

            provider_obj = self._get_provider(provider)
            positions = await provider_obj.get_positions()

            position_list = []
            for pos in positions:
                position_list.append(
                    {
                        "market_id": pos.market_id,
                        "outcome": pos.outcome,
                        "size": pos.size,
                        "avg_price": pos.avg_price,
                        "realized_pnl": pos.realized_pnl,
                        "unrealized_pnl": pos.unrealized_pnl,
                    }
                )

            return {
                "success": True,
                "provider": provider.lower(),
                "count": len(position_list),
                "positions": position_list,
            }
        except Exception as e:
            logger.error("Failed to get positions", provider=provider, error=str(e))
            return {"success": False, "error": str(e)}


def register_trading_tools(
    registry,
    poly_provider: PolyProvider,
    kalshi_provider: Optional[KalshiProvider] = None,
    audit_store: Optional[RiskAuditStore] = None,
):
    """Register trading tools with the tool registry"""
    tools = TradingTools(poly_provider, kalshi_provider, audit_store)

    registry.register(
        name="get_wallet_balance",
        description="Get wallet balance in USDC for trading",
        parameters={
            "provider": {
                "type": "string",
                "description": "Provider to check balance for (polymarket or kalshi)",
                "default": "polymarket",
            }
        },
        category="trading",
    )(tools.get_wallet_balance)

    registry.register(
        name="place_market_buy",
        description="Place a market buy order for a specified dollar amount",
        parameters={
            "token_id": {
                "type": "string",
                "description": "Token ID to buy",
                "required": True,
            },
            "amount": {
                "type": "number",
                "description": "Dollar amount to spend",
                "required": True,
            },
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket",
            },
        },
        category="trading",
    )(tools.place_market_buy)

    registry.register(
        name="place_market_sell",
        description="Place a market sell order for a specified number of shares",
        parameters={
            "token_id": {
                "type": "string",
                "description": "Token ID to sell",
                "required": True,
            },
            "shares": {
                "type": "number",
                "description": "Number of shares to sell",
                "required": True,
            },
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket",
            },
        },
        category="trading",
    )(tools.place_market_sell)

    registry.register(
        name="get_trade_history",
        description="Get recent trade history",
        parameters={
            "market_id": {
                "type": "string",
                "description": "Optional market ID to filter trades",
                "required": False,
            },
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of trades to return",
                "default": 50,
            },
        },
        category="trading",
    )(tools.get_trade_history)

    registry.register(
        name="get_positions",
        description="Get current open positions",
        parameters={
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket",
            }
        },
        category="trading",
    )(tools.get_positions)
