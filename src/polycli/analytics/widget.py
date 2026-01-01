"""Performance dashboard TUI widget."""
from decimal import Decimal
from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Static
from textual.reactive import reactive

from .calculator import PerformanceCalculator
from .models import PerformanceMetrics, PositionSummary


class PerformanceSummaryBox(Static):
    """Summary statistics box."""
    
    def __init__(self, metrics: Optional[PerformanceMetrics] = None, **kwargs):
        super().__init__(**kwargs)
        self.metrics = metrics or PerformanceMetrics()
    
    def render(self) -> str:
        m = self.metrics
        pnl_color = "green" if m.total_pnl >= 0 else "red"
        
        return (
            f"[bold]Performance Summary[/bold]\n"
            f"────────────────────\n"
            f"Total P&L: [{pnl_color}]${m.total_pnl:+.2f}[/]\n"
            f"  Realized: ${m.total_realized_pnl:+.2f}\n"
            f"  Unrealized: ${m.total_unrealized_pnl:+.2f}\n"
            f"────────────────────\n"
            f"Win Rate: {m.win_rate:.1%}\n"
            f"  Wins: {m.winning_trades} | Losses: {m.losing_trades}\n"
            f"────────────────────\n"
            f"Avg Win: ${m.avg_win:.2f}\n"
            f"Avg Loss: ${m.avg_loss:.2f}\n"
            f"Best: ${m.largest_win:+.2f}\n"
            f"Worst: ${m.largest_loss:+.2f}\n"
            f"────────────────────\n"
            f"Profit Factor: {m.profit_factor:.2f}\n"
            f"Max Drawdown: {m.max_drawdown_pct:.1%}"
        )
    
    def update_metrics(self, metrics: PerformanceMetrics) -> None:
        self.metrics = metrics
        self.refresh()


class PnLChart(Static):
    """ASCII-based P&L chart."""
    
    def __init__(self, data: Optional[List[Decimal]] = None, width: int = 40, height: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.data = data or []
        self.chart_width = width
        self.chart_height = height
    
    def render(self) -> str:
        if not self.data or len(self.data) < 2:
            return "[dim]Not enough data for chart[/dim]"
        
        # Normalize data to chart height
        min_val = min(self.data)
        max_val = max(self.data)
        val_range = max_val - min_val or Decimal("1")
        
        # Build ASCII chart
        lines = []
        for row in range(self.chart_height, -1, -1):
            line = ""
            threshold = min_val + (val_range * Decimal(row) / Decimal(self.chart_height))
            
            for i, val in enumerate(self.data[-self.chart_width:]):
                if val >= threshold:
                    if val >= 0:
                        line += "[green]█[/]"
                    else:
                        line += "[red]█[/]"
                else:
                    line += " "
            
            # Add Y-axis label
            if row == self.chart_height:
                lines.append(f"${max_val:>8.0f} │{line}")
            elif row == 0:
                lines.append(f"${min_val:>8.0f} │{line}")
            elif row == self.chart_height // 2:
                mid = (max_val + min_val) / 2
                lines.append(f"${mid:>8.0f} │{line}")
            else:
                lines.append(f"         │{line}")
        
        # Add X-axis
        lines.append("         └" + "─" * self.chart_width)
        lines.append("          " + "Past" + " " * (self.chart_width - 10) + "Now")
        
        return "\n".join(lines)
    
    def update_data(self, data: List[Decimal]) -> None:
        self.data = data
        self.refresh()


class PositionsTable(Container):
    """Positions breakdown table."""
    
    def __init__(self, positions: Optional[List[PositionSummary]] = None, **kwargs):
        super().__init__(**kwargs)
        self.positions = positions or []
    
    def compose(self) -> ComposeResult:
        yield DataTable(id="positions-table")
    
    def on_mount(self) -> None:
        table = self.query_one("#positions-table", DataTable)
        table.add_columns("Market", "Side", "Size", "Avg", "Current", "P&L", "% Port")
        self._populate_table()
    
    def _populate_table(self) -> None:
        table = self.query_one("#positions-table", DataTable)
        table.clear()
        
        for pos in self.positions:
            pnl_str = f"${pos.unrealized_pnl:+.2f}"
            if pos.unrealized_pnl >= 0:
                pnl_str = f"[green]{pnl_str}[/]"
            else:
                pnl_str = f"[red]{pnl_str}[/]"
            
            table.add_row(
                pos.market_name[:30],
                pos.outcome,
                f"{pos.size:.1f}",
                f"${pos.avg_price:.2f}",
                f"${pos.current_price:.2f}",
                pnl_str,
                f"{pos.portfolio_pct:.1%}"
            )
    
    def update_positions(self, positions: List[PositionSummary]) -> None:
        self.positions = positions
        self._populate_table()


class PerformanceDashboardWidget(Container):
    """Main performance dashboard widget."""
    
    DEFAULT_CSS = """
    PerformanceDashboardWidget {
        layout: grid;
        grid-size: 2 2;
        grid-rows: 1fr 1fr;
        grid-columns: 1fr 2fr;
        height: 100%;
    }
    
    #summary-box {
        row-span: 1;
        border: solid $primary;
        padding: 1;
    }
    
    #pnl-chart {
        border: solid $secondary;
        padding: 1;
    }
    
    #positions-table-container {
        column-span: 2;
        border: solid $accent;
    }
    """
    
    def __init__(
        self,
        calculator: Optional[PerformanceCalculator] = None,
        provider: str = "polymarket",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.calculator = calculator or PerformanceCalculator()
        self.provider = provider
        self.metrics: Optional[PerformanceMetrics] = None
        self.positions: List[PositionSummary] = []
    
    def compose(self) -> ComposeResult:
        yield PerformanceSummaryBox(id="summary-box")
        yield PnLChart(id="pnl-chart")
        yield Container(
            Static("[bold]Positions[/bold]"),
            PositionsTable(id="positions-table-container"),
            id="positions-container"
        )
    
    async def on_mount(self) -> None:
        """Load data on mount."""
        await self.refresh_data()
    
    async def refresh_data(self) -> None:
        """Refresh all analytics data."""
        # Get metrics
        self.metrics = await self.calculator.calculate_metrics(self.provider)
        
        # Update summary box
        summary = self.query_one("#summary-box", PerformanceSummaryBox)
        summary.update_metrics(self.metrics)
        
        # Update chart
        chart = self.query_one("#pnl-chart", PnLChart)
        chart.update_data(self.metrics.cumulative_pnl_series)
        
        # Get and update positions
        self.positions = await self.calculator.get_position_summaries(self.provider)
        positions_table = self.query_one("#positions-table-container", PositionsTable)
        positions_table.update_positions(self.positions)
