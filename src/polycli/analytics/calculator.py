"""Performance metrics calculator."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, List, Optional
import structlog

from .models import PerformanceMetrics, PositionSummary, TradeRecord, DailyPnL
from .store import AnalyticsStore

logger = structlog.get_logger()


class PerformanceCalculator:
    """Calculate trading performance metrics."""
    
    def __init__(
        self,
        store: Optional[AnalyticsStore] = None,
        get_balance_fn: Optional[Callable] = None,
        get_positions_fn: Optional[Callable] = None,
        get_price_fn: Optional[Callable] = None
    ):
        self.store = store or AnalyticsStore()
        self._get_balance = get_balance_fn
        self._get_positions = get_positions_fn
        self._get_price = get_price_fn
    
    async def calculate_metrics(
        self,
        provider: Optional[str] = None,
        days: int = 30
    ) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics."""
        metrics = PerformanceMetrics()
        
        # Get trades for period
        start_date = datetime.utcnow() - timedelta(days=days)
        trades = self.store.get_trades(start_date=start_date, provider=provider)
        
        if not trades:
            return metrics
        
        # Calculate trade-based metrics
        metrics.total_trades = len(trades)
        
        total_profit = Decimal("0")
        total_loss = Decimal("0")
        wins = []
        losses = []
        
        for trade in trades:
            if trade.pnl:
                if trade.pnl > 0:
                    metrics.winning_trades += 1
                    total_profit += trade.pnl
                    wins.append(trade.pnl)
                elif trade.pnl < 0:
                    metrics.losing_trades += 1
                    total_loss += abs(trade.pnl)
                    losses.append(trade.pnl)
        
        metrics.total_realized_pnl = total_profit - total_loss
        
        if metrics.total_trades > 0:
            metrics.win_rate = Decimal(str(metrics.winning_trades / metrics.total_trades))
        
        if wins:
            metrics.avg_win = sum(wins) / len(wins)
            metrics.largest_win = max(wins)
        
        if losses:
            metrics.avg_loss = sum(losses) / len(losses)
            metrics.largest_loss = min(losses)
        
        if total_loss > 0:
            metrics.profit_factor = total_profit / total_loss
        
        # Calculate position-based metrics
        if self._get_positions:
            try:
                positions = await self._get_positions(provider or "polymarket")
                metrics.current_positions = len(positions)
                
                total_value = Decimal("0")
                unrealized = Decimal("0")
                
                for pos in positions:
                    value = Decimal(str(pos.get("size", 0))) * Decimal(str(pos.get("current_price", 0)))
                    total_value += value
                    unrealized += Decimal(str(pos.get("unrealized_pnl", 0)))
                
                metrics.total_exposure = total_value
                metrics.total_unrealized_pnl = unrealized
            except Exception as e:
                logger.warning("Failed to get positions for metrics", error=str(e))
        
        metrics.total_pnl = metrics.total_realized_pnl + metrics.total_unrealized_pnl
        
        # Calculate drawdown
        if self._get_balance:
            try:
                balance_info = await self._get_balance(provider or "polymarket")
                current_balance = Decimal(str(balance_info.get("balance", 0)))
                peak_balance = self.store.get_peak_balance(provider)
                
                if peak_balance > 0:
                    drawdown = peak_balance - current_balance
                    metrics.max_drawdown = max(Decimal("0"), drawdown)
                    metrics.max_drawdown_pct = metrics.max_drawdown / peak_balance
                
                # Record balance for history
                self.store.record_balance(current_balance, provider or "polymarket")
            except Exception as e:
                logger.warning("Failed to get balance for metrics", error=str(e))
        
        # Get daily history
        daily = self.store.get_daily_snapshots(limit=days)
        metrics.daily_pnl_history = daily
        
        if daily:
            # Find best/worst days
            sorted_days = sorted(daily, key=lambda d: d.total_pnl, reverse=True)
            if sorted_days:
                metrics.best_day = sorted_days[0]
                metrics.worst_day = sorted_days[-1]
            
            # Calculate cumulative P&L series
            cumulative = Decimal("0")
            metrics.cumulative_pnl_series = []
            for day in reversed(daily):
                cumulative += day.total_pnl
                metrics.cumulative_pnl_series.append(cumulative)
        
        # P&L by provider
        pnl_by_provider = {}
        for trade in trades:
            if trade.pnl:
                pnl_by_provider[trade.provider] = pnl_by_provider.get(trade.provider, Decimal("0")) + trade.pnl
        metrics.pnl_by_provider = pnl_by_provider
        
        return metrics
    
    async def get_position_summaries(
        self,
        provider: str = "polymarket"
    ) -> List[PositionSummary]:
        """Get detailed position summaries."""
        if not self._get_positions or not self._get_price:
            return []
        
        positions = await self._get_positions(provider)
        summaries = []
        
        total_value = sum(
            Decimal(str(p.get("size", 0))) * Decimal(str(p.get("current_price", 0)))
            for p in positions
        )
        
        for pos in positions:
            size = Decimal(str(pos.get("size", 0)))
            avg_price = Decimal(str(pos.get("avg_price", 0)))
            current_price = Decimal(str(pos.get("current_price", avg_price)))
            cost_basis = size * avg_price
            market_value = size * current_price
            unrealized_pnl = market_value - cost_basis
            
            portfolio_pct = market_value / total_value if total_value > 0 else Decimal("0")
            unrealized_pnl_pct = unrealized_pnl / cost_basis if cost_basis > 0 else Decimal("0")
            
            summaries.append(PositionSummary(
                market_id=pos.get("market_id", ""),
                market_name=pos.get("market_name", pos.get("market_id", "")),
                token_id=pos.get("token_id", ""),
                outcome=pos.get("outcome", ""),
                size=size,
                avg_price=avg_price,
                current_price=current_price,
                cost_basis=cost_basis,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                portfolio_pct=portfolio_pct,
                provider=provider
            ))
        
        return summaries
