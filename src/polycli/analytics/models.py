"""Analytics data models."""
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict


@dataclass
class TradeRecord:
    """Individual trade record for analytics."""
    id: str
    timestamp: datetime
    market_id: str
    market_name: str
    token_id: str
    side: str  # "BUY" or "SELL"
    outcome: str  # "YES" or "NO"
    price: Decimal
    size: Decimal
    total: Decimal
    fee: Decimal
    provider: str
    pnl: Optional[Decimal] = None  # Realized P&L if closed
    

@dataclass
class PositionSummary:
    """Summary of a single position."""
    market_id: str
    market_name: str
    token_id: str
    outcome: str
    size: Decimal
    avg_price: Decimal
    current_price: Decimal
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    portfolio_pct: Decimal
    provider: str


@dataclass
class DailyPnL:
    """P&L for a single day."""
    date: date
    starting_balance: Decimal
    ending_balance: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    trades_count: int
    winning_trades: int
    losing_trades: int


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    # Overall P&L
    total_realized_pnl: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    total_pnl_pct: Decimal = Decimal("0")
    
    # Win/Loss stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal = Decimal("0")
    
    # Trade metrics
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")  # Gross profit / Gross loss
    
    # Position metrics
    current_positions: int = 0
    total_exposure: Decimal = Decimal("0")
    largest_position_pct: Decimal = Decimal("0")
    
    # Risk metrics
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    sharpe_ratio: Optional[Decimal] = None  # If enough data
    
    # Time-based
    best_day: Optional[DailyPnL] = None
    worst_day: Optional[DailyPnL] = None
    
    # Breakdown
    pnl_by_provider: Dict[str, Decimal] = field(default_factory=dict)
    pnl_by_market: Dict[str, Decimal] = field(default_factory=dict)
    
    # Time series for charting
    daily_pnl_history: List[DailyPnL] = field(default_factory=list)
    cumulative_pnl_series: List[Decimal] = field(default_factory=list)


@dataclass
class TradeAnalysis:
    """Analysis of an individual trade."""
    trade: TradeRecord
    hold_duration: Optional[float] = None  # Hours
    pnl_pct: Optional[Decimal] = None
    was_winner: Optional[bool] = None
    market_moved_pct: Optional[Decimal] = None  # Price change since entry
