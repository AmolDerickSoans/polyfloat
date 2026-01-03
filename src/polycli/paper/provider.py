"""Paper trading provider that simulates real trading."""
import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional
import structlog

from .models import (
    PaperOrder, PaperPosition, PaperTrade, PaperWallet,
    PaperOrderStatus, PaperOrderSide
)
from .store import PaperTradingStore
from ..providers.base import BaseProvider
from ..providers.polymarket import PolyProvider

logger = structlog.get_logger()


class PaperTradingProvider(BaseProvider):
    """
    Simulates trading operations using real market data.
    
    This provider intercepts trading calls and simulates execution
    while fetching real prices from the underlying market provider.
    """
    
    # Simulated fees (matching real Polymarket fees)
    MAKER_FEE = Decimal("0.00")  # 0%
    TAKER_FEE = Decimal("0.01")  # 1%
    
    def __init__(
        self,
        real_provider: PolyProvider,
        store: Optional[PaperTradingStore] = None,
        provider_name: str = "polymarket"
    ):
        self.real_provider = real_provider
        self.store = store or PaperTradingStore()
        self.provider_name = provider_name
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the paper trading provider."""
        if not self._initialized:
            # Ensure wallet exists
            self.store.get_wallet(self.provider_name)
            self._initialized = True
            logger.info("Paper trading provider initialized", provider=self.provider_name)
    
    async def get_balance(self) -> Dict[str, Any]:
        """Get paper trading balance."""
        wallet = self.store.get_wallet(self.provider_name)
        positions = self.store.get_positions(self.provider_name)
        
        # Calculate unrealized P&L from current positions
        unrealized_pnl = Decimal("0")
        for pos in positions:
            try:
                current_price = await self._get_current_price(pos.token_id)
                pos_unrealized = (current_price - pos.avg_price) * pos.size
                unrealized_pnl += pos_unrealized
            except Exception as e:
                logger.warning("Failed to get price for position", token_id=pos.token_id, error=str(e))
        
        return {
            "balance": float(wallet.balance),
            "allowance": float(wallet.balance),  # Paper trading has unlimited allowance
            "currency": "USDC",
            "initial_balance": float(wallet.initial_balance),
            "realized_pnl": float(wallet.realized_pnl),
            "unrealized_pnl": float(unrealized_pnl),
            "total_value": float(wallet.balance + unrealized_pnl),
            "paper_mode": True
        }
    
    async def _get_current_price(self, token_id: str) -> Decimal:
        """Get current market price for a token."""
        try:
            # Use real provider to get actual market price
            midpoint = await asyncio.to_thread(
                self.real_provider.client.get_midpoint, token_id
            )
            return Decimal(str(midpoint))
        except Exception as e:
            logger.error("Failed to get midpoint", token_id=token_id, error=str(e))
            raise
    
    async def _get_best_price(self, token_id: str, side: str) -> Decimal:
        """Get best available price for a side (BUY/SELL)."""
        try:
            price = await asyncio.to_thread(
                self.real_provider.client.get_price, token_id, side
            )
            return Decimal(str(price))
        except Exception as e:
            logger.error("Failed to get price", token_id=token_id, side=side, error=str(e))
            raise
    
    async def place_market_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        amount: float,
        market_id: str = ""
    ) -> Dict[str, Any]:
        """
        Simulate a market order execution.
        
        For BUY: amount is in dollars
        For SELL: amount is in shares
        """
        await self.initialize()
        
        order_side = PaperOrderSide.BUY if side.upper() == "BUY" else PaperOrderSide.SELL
        amount_decimal = Decimal(str(amount))
        
        # Get current market price
        try:
            execution_price = await self._get_best_price(token_id, side.upper())
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get market price: {e}",
                "paper_mode": True
            }
        
        wallet = self.store.get_wallet(self.provider_name)
        
        # Initialize variables that are used in both branches
        shares = Decimal("0")
        total_cost = Decimal("0")
        total_proceeds = Decimal("0")
        total_with_fee = Decimal("0")
        fee = Decimal("0")
        new_balance = wallet.balance
        
        if order_side == PaperOrderSide.BUY:
            # Calculate shares we can buy
            shares = amount_decimal / execution_price
            total_cost = amount_decimal
            fee = total_cost * self.TAKER_FEE
            total_with_fee = total_cost + fee
            
            # Check balance
            if total_with_fee > wallet.balance:
                return {
                    "success": False,
                    "error": f"Insufficient balance. Have: ${wallet.balance:.2f}, Need: ${total_with_fee:.2f}",
                    "paper_mode": True
                }
            
            # Execute the order
            new_balance = wallet.balance - total_with_fee
            self.store.update_wallet_balance(self.provider_name, new_balance)
            
            # Update position
            position = self.store.get_position(token_id, self.provider_name)
            if position:
                # Average into existing position
                total_size = position.size + shares
                total_cost_basis = position.cost_basis + total_cost
                new_avg_price = total_cost_basis / total_size
                position.size = total_size
                position.avg_price = new_avg_price
                position.cost_basis = total_cost_basis
            else:
                position = PaperPosition(
                    token_id=token_id,
                    market_id=market_id,
                    outcome="YES",  # Default, should be passed
                    size=shares,
                    avg_price=execution_price,
                    cost_basis=total_cost,
                    provider=self.provider_name
                )
            self.store.save_position(position)
            
        else:  # SELL
            shares = amount_decimal
            position = self.store.get_position(token_id, self.provider_name)
            
            if not position or position.size < shares:
                available = position.size if position else Decimal("0")
                return {
                    "success": False,
                    "error": f"Insufficient shares. Have: {available}, Need: {shares}",
                    "paper_mode": True
                }
            
            # Calculate proceeds
            total_proceeds = shares * execution_price
            fee = total_proceeds * self.TAKER_FEE
            net_proceeds = total_proceeds - fee
            
            # Calculate realized P&L
            cost_of_shares = shares * position.avg_price
            realized_pnl = net_proceeds - cost_of_shares
            
            # Update wallet
            new_balance = wallet.balance + net_proceeds
            new_realized_pnl = wallet.realized_pnl + realized_pnl
            self.store.update_wallet_balance(self.provider_name, new_balance, new_realized_pnl)
            
            # Update position
            position.size -= shares
            position.cost_basis -= cost_of_shares
            position.realized_pnl += realized_pnl
            self.store.save_position(position)
        
        # Create order record
        order = PaperOrder(
            token_id=token_id,
            market_id=market_id,
            side=order_side,
            amount=amount_decimal,
            status=PaperOrderStatus.FILLED,
            filled_amount=shares if order_side == PaperOrderSide.BUY else amount_decimal,
            avg_fill_price=execution_price,
            provider=self.provider_name
        )
        self.store.save_order(order)
        
        # Create trade record
        trade = PaperTrade(
            order_id=order.id,
            token_id=token_id,
            market_id=market_id,
            side=order_side,
            price=execution_price,
            size=shares if order_side == PaperOrderSide.BUY else amount_decimal,
            total=total_cost if order_side == PaperOrderSide.BUY else total_proceeds,
            fee=fee,
            provider=self.provider_name
        )
        self.store.save_trade(trade)
        
        logger.info(
            "Paper trade executed",
            order_id=order.id,
            side=side,
            token_id=token_id,
            price=float(execution_price),
            size=float(order.filled_amount),
            fee=float(fee)
        )
        
        return {
            "success": True,
            "order_id": order.id,
            "token_id": token_id,
            "side": side,
            "price": float(execution_price),
            "size": float(order.filled_amount),
            "total": float(trade.total),
            "fee": float(fee),
            "new_balance": float(new_balance if order_side == PaperOrderSide.SELL else wallet.balance - total_with_fee),
            "status": "FILLED",
            "paper_mode": True
        }
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all paper trading positions."""
        positions = self.store.get_positions(self.provider_name)
        result = []
        
        for pos in positions:
            try:
                current_price = await self._get_current_price(pos.token_id)
                unrealized_pnl = (current_price - pos.avg_price) * pos.size
            except Exception:
                current_price = pos.avg_price
                unrealized_pnl = Decimal("0")
            
            result.append({
                "token_id": pos.token_id,
                "market_id": pos.market_id,
                "outcome": pos.outcome,
                "size": float(pos.size),
                "avg_price": float(pos.avg_price),
                "current_price": float(current_price),
                "cost_basis": float(pos.cost_basis),
                "unrealized_pnl": float(unrealized_pnl),
                "realized_pnl": float(pos.realized_pnl),
                "paper_mode": True
            })
        
        return result
    
    async def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get paper trade history."""
        trades = self.store.get_trades(self.provider_name, limit)
        return [
            {
                "id": t.id,
                "order_id": t.order_id,
                "token_id": t.token_id,
                "market_id": t.market_id,
                "side": t.side.value,
                "price": float(t.price),
                "size": float(t.size),
                "total": float(t.total),
                "fee": float(t.fee),
                "executed_at": t.executed_at.isoformat() if hasattr(t.executed_at, 'isoformat') else str(t.executed_at),
                "paper_mode": True
            }
            for t in trades
        ]

    async def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get paper order history."""
        orders = self.store.get_orders(self.provider_name, limit)
        return [
            {
                "id": o.id,
                "token_id": o.token_id,
                "market_id": o.market_id,
                "side": o.side.value,
                "amount": float(o.amount),
                "price": float(o.price) if o.price else None,
                "status": o.status.value,
                "filled_amount": float(o.filled_amount),
                "avg_fill_price": float(o.avg_fill_price),
                "created_at": o.created_at.isoformat() if hasattr(o.created_at, 'isoformat') else str(o.created_at),
                "paper_mode": True
            }
            for o in orders
        ]
    
    async def reset(self, initial_balance: float = 1000.0) -> Dict[str, Any]:
        """Reset paper trading state."""
        self.store.reset(self.provider_name, Decimal(str(initial_balance)))
        logger.info("Paper trading reset", provider=self.provider_name, initial_balance=initial_balance)
        return {
            "success": True,
            "message": f"Paper trading reset with ${initial_balance:.2f} balance",
            "paper_mode": True
        }
    
    # Proxy methods for real market data
    async def get_markets(self, **kwargs):
        """Proxy to real provider for market data."""
        return await self.real_provider.get_markets(**kwargs)
    
    async def get_market(self, market_id: str):
        """Proxy to real provider for market details."""
        markets = await self.real_provider.get_markets()
        for market in markets:
            if market.id == market_id:
                return market
        return None
    
    async def get_orderbook(self, token_id: str):
        """Proxy to real provider for orderbook."""
        return await self.real_provider.get_orderbook(token_id)

    async def get_prices_history(
        self,
        token_id: str,
        interval: str = "1d",
        fidelity: int = 60
    ):
        """Proxy to real provider for historical price data."""
        return await self.real_provider.get_prices_history(
            token_id=token_id,
            interval=interval,
            fidelity=fidelity
        )

    async def search(self, query: str):
        """Proxy to real provider for market search."""
        return await self.real_provider.search(query)

    async def get_events(self, category: Optional[str] = None, limit: int = 100):
        """Proxy to real provider for events."""
        return await self.real_provider.get_events(category=category, limit=limit)

    async def get_news(self, query: Optional[str] = None, limit: int = 10):
        """Proxy to real provider for news."""
        return await self.real_provider.get_news(query=query, limit=limit)

    async def get_history(self, market_id: Optional[str] = None):
        """Proxy to real provider for trade history."""
        # Note: BaseProvider.get_history refers to trade history
        # Polymarket implementation returns user trades.
        # For paper trading, we might want to return paper trades or real ones?
        # Usually TUI uses this for 'Trade History' view.
        # Re-using the real provider's get_history for now if it doesn't crash.
        return await self.real_provider.get_history(market_id=market_id)

    async def place_order(
        self,
        market_id: str,
        side: Any,
        size: float,
        price: float,
        order_type: Any = None
    ):
        """
        Implementation of BaseProvider.place_order.
        Proxies to place_market_order for now or simulates limit order.
        """
        # For now, we simulate as market order if it's paper trading.
        # Or we could implement limit orders in PaperTradingStore.
        return await self.place_market_order(market_id, str(side), size, market_id=market_id)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order (simulated)."""
        # Paper trading currently fill-or-kill, but we should satisfy interface.
        return True
