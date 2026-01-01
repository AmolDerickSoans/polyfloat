"""Order cancellation utilities for emergency stop."""
import asyncio
from typing import Any, Optional
import structlog

logger = structlog.get_logger()


class OrderCanceller:
    """Handles cancellation of all pending orders across platforms."""

    def __init__(
        self,
        poly_provider: Optional[Any] = None,
        kalshi_provider: Optional[Any] = None
    ):
        self.poly = poly_provider
        self.kalshi = kalshi_provider

    async def cancel_all_orders(self) -> int:
        """
        Cancel all pending orders across all providers.

        Returns:
            Total number of orders cancelled
        """
        total_cancelled = 0

        task_providers = []
        tasks = []

        if self.poly:
            tasks.append(self._cancel_polymarket_orders())
            task_providers.append("Polymarket")

        if self.kalshi:
            tasks.append(self._cancel_kalshi_orders())
            task_providers.append("Kalshi")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                provider = task_providers[i]

                if isinstance(result, Exception):
                    logger.error(
                        "Failed to cancel orders",
                        provider=provider,
                        error=str(result)
                    )
                else:
                    total_cancelled += result
                    logger.info(
                        "Cancelled orders",
                        provider=provider,
                        count=result
                    )

        return total_cancelled

    async def _cancel_polymarket_orders(self) -> int:
        """Cancel all Polymarket orders."""
        from py_clob_client.clob_types import OpenOrderParams

        try:
            open_orders = self.poly.client.get_orders(OpenOrderParams())

            if not open_orders:
                return 0

            self.poly.client.cancel_all()

            return len(open_orders)

        except Exception as e:
            logger.error("Polymarket cancel error", error=str(e))
            raise

    async def _cancel_kalshi_orders(self) -> int:
        """Cancel all Kalshi orders."""
        try:
            orders_response = await self.kalshi.get_orders(status="resting")
            orders = orders_response.get("orders", [])

            if not orders:
                return 0

            cancelled = 0
            for order in orders:
                try:
                    await self.kalshi.cancel_order(order["order_id"])
                    cancelled += 1
                except Exception as e:
                    logger.warning(
                        "Failed to cancel individual Kalshi order",
                        order_id=order.get("order_id"),
                        error=str(e)
                    )

            return cancelled

        except Exception as e:
            logger.error("Kalshi cancel error", error=str(e))
            raise
