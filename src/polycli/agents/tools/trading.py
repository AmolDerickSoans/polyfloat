"""Trading tools for agent use - wallet balance, order placement, trade history"""

from typing import Dict, Any, Optional, List
import structlog
from polycli.models import Side, OrderType
from polycli.providers.polymarket import PolyProvider
from polycli.providers.kalshi import KalshiProvider

logger = structlog.get_logger()


class TradingTools:
    """Tools for trading operations"""
    
    def __init__(self, poly_provider: PolyProvider, kalshi_provider: Optional[KalshiProvider] = None):
        self.poly = poly_provider
        self.kalshi = kalshi_provider
    
    async def get_wallet_balance(self, provider: str = "polymarket") -> Dict[str, Any]:
        """
        Get wallet balance for the specified provider.
        
        Args:
            provider: "polymarket" or "kalshi"
            
        Returns:
            Dict with balance information
        """
        try:
            if provider.lower() == "polymarket":
                balance_info = await self.poly.get_balance()
                return {
                    "provider": "polymarket",
                    "balance": float(balance_info.get("balance", 0)),
                    "currency": "USDC",
                    "allowance": float(balance_info.get("allowance", 0)),
                    "error": balance_info.get("error")
                }
            elif provider.lower() == "kalshi" and self.kalshi:
                # Kalshi balance check would go here
                return {
                    "provider": "kalshi",
                    "balance": 0.0,
                    "currency": "USD",
                    "error": "Not implemented"
                }
            else:
                return {"error": "Invalid provider or provider not configured"}
        except Exception as e:
            logger.error("Failed to get wallet balance", provider=provider, error=str(e))
            return {"error": str(e)}
    
    async def place_market_buy(
        self,
        token_id: str,
        amount: float,
        provider: str = "polymarket"
    ) -> Dict[str, Any]:
        """
        Place a market buy order.
        
        Args:
            token_id: Token/market ID to buy
            amount: Dollar amount to spend
            provider: "polymarket" or "kalshi"
            
        Returns:
            Dict with order result
        """
        try:
            if provider.lower() == "polymarket":
                # Check balance first
                balance_info = await self.poly.get_balance()
                balance = float(balance_info.get("balance", 0))
                
                if amount > balance:
                    return {
                        "success": False,
                        "error": f"Insufficient balance. Have: ${balance:.2f}, Need: ${amount:.2f}"
                    }
                
                order = await self.poly.place_market_order(
                    token_id=token_id,
                    side=Side.BUY,
                    amount=amount
                )
                
                return {
                    "success": True,
                    "order_id": order.id,
                    "token_id": token_id,
                    "side": "BUY",
                    "amount": amount,
                    "status": order.status.value
                }
            else:
                return {"success": False, "error": "Only Polymarket supported currently"}
        except Exception as e:
            logger.error("Market buy failed", token_id=token_id, amount=amount, error=str(e))
            return {"success": False, "error": str(e)}
    
    async def place_market_sell(
        self,
        token_id: str,
        shares: float,
        provider: str = "polymarket"
    ) -> Dict[str, Any]:
        """
        Place a market sell order.
        
        Args:
            token_id: Token/market ID to sell
            shares: Number of shares to sell
            provider: "polymarket" or "kalshi"
            
        Returns:
            Dict with order result
        """
        try:
            if provider.lower() == "polymarket":
                order = await self.poly.place_market_order(
                    token_id=token_id,
                    side=Side.SELL,
                    amount=shares
                )
                
                return {
                    "success": True,
                    "order_id": order.id,
                    "token_id": token_id,
                    "side": "SELL",
                    "shares": shares,
                    "status": order.status.value
                }
            else:
                return {"success": False, "error": "Only Polymarket supported currently"}
        except Exception as e:
            logger.error("Market sell failed", token_id=token_id, shares=shares, error=str(e))
            return {"success": False, "error": str(e)}
    
    async def get_trade_history(
        self,
        market_id: Optional[str] = None,
        provider: str = "polymarket",
        limit: int = 50
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
            if provider.lower() == "polymarket":
                trades = await self.poly.get_trades(market_id=market_id)
                
                trade_list = []
                for trade in trades[:limit]:
                    trade_list.append({
                        "id": trade.id,
                        "market_id": trade.market_id,
                        "side": trade.side.value,
                        "price": trade.price,
                        "size": trade.size,
                        "total": trade.price * trade.size,
                        "timestamp": trade.timestamp
                    })
                
                return {
                    "success": True,
                    "provider": "polymarket",
                    "count": len(trade_list),
                    "trades": trade_list
                }
            else:
                return {"success": False, "error": "Only Polymarket supported currently"}
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
            if provider.lower() == "polymarket":
                positions = await self.poly.get_positions()
                
                position_list = []
                for pos in positions:
                    position_list.append({
                        "market_id": pos.market_id,
                        "outcome": pos.outcome,
                        "size": pos.size,
                        "avg_price": pos.avg_price,
                        "realized_pnl": pos.realized_pnl,
                        "unrealized_pnl": pos.unrealized_pnl
                    })
                
                return {
                    "success": True,
                    "provider": "polymarket",
                    "count": len(position_list),
                    "positions": position_list
                }
            elif provider.lower() == "kalshi" and self.kalshi:
                positions = await self.kalshi.get_positions()
                position_list = [
                    {
                        "market_id": pos.market_id,
                        "outcome": pos.outcome,
                        "size": pos.size,
                        "avg_price": pos.avg_price,
                        "realized_pnl": pos.realized_pnl,
                        "unrealized_pnl": pos.unrealized_pnl
                    }
                    for pos in positions
                ]
                return {
                    "success": True,
                    "provider": "kalshi",
                    "count": len(position_list),
                    "positions": position_list
                }
            else:
                return {"success": False, "error": "Invalid provider"}
        except Exception as e:
            logger.error("Failed to get positions", provider=provider, error=str(e))
            return {"success": False, "error": str(e)}


def register_trading_tools(registry, poly_provider: PolyProvider, kalshi_provider: Optional[KalshiProvider] = None):
    """Register trading tools with the tool registry"""
    tools = TradingTools(poly_provider, kalshi_provider)
    
    registry.register(
        name="get_wallet_balance",
        description="Get wallet balance in USDC for trading",
        parameters={
            "provider": {
                "type": "string",
                "description": "Provider to check balance for (polymarket or kalshi)",
                "default": "polymarket"
            }
        },
        category="trading"
    )(tools.get_wallet_balance)
    
    registry.register(
        name="place_market_buy",
        description="Place a market buy order for a specified dollar amount",
        parameters={
            "token_id": {
                "type": "string",
                "description": "Token ID to buy",
                "required": True
            },
            "amount": {
                "type": "number",
                "description": "Dollar amount to spend",
                "required": True
            },
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket"
            }
        },
        category="trading"
    )(tools.place_market_buy)
    
    registry.register(
        name="place_market_sell",
        description="Place a market sell order for a specified number of shares",
        parameters={
            "token_id": {
                "type": "string",
                "description": "Token ID to sell",
                "required": True
            },
            "shares": {
                "type": "number",
                "description": "Number of shares to sell",
                "required": True
            },
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket"
            }
        },
        category="trading"
    )(tools.place_market_sell)
    
    registry.register(
        name="get_trade_history",
        description="Get recent trade history",
        parameters={
            "market_id": {
                "type": "string",
                "description": "Optional market ID to filter trades",
                "required": False
            },
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of trades to return",
                "default": 50
            }
        },
        category="trading"
    )(tools.get_trade_history)
    
    registry.register(
        name="get_positions",
        description="Get current open positions",
        parameters={
            "provider": {
                "type": "string",
                "description": "Provider (polymarket or kalshi)",
                "default": "polymarket"
            }
        },
        category="trading"
    )(tools.get_positions)
