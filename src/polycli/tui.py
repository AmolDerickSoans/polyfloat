from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label, Input, Button, ContentSwitcher, RadioSet, RadioButton
from dotenv import load_dotenv

load_dotenv(override=True)
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.reactive import reactive
from textual import work, on
from textual.screen import ModalScreen
import asyncio
import json
from typing import List, Optional, Dict, Any, Set
import plotext as plt
from polycli.providers.polymarket import PolyProvider
from polycli.providers.kalshi import KalshiProvider
from polycli.providers.polymarket_ws import PolymarketWebSocket
from polycli.providers.kalshi_ws import KalshiWebSocket
from polycli.models import PriceSeries, PricePoint, OrderBook, MultiLineSeries, Market, Trade, Side, OrderStatus, Order, PriceLevel
from polycli.utils.launcher import ChartManager
from polycli.arbitrage.tui_widget import ArbitrageScanner
from rich.panel import Panel
from rich.table import Table
from rich.bar import Bar
from rich.console import RenderableType
from rich.text import Text

class NewsTicker(Static):
    """Scrolling news ticker at the bottom of the screen"""
    news_items = [
        "US Election 2024: Trump leads in Pennsylvania by 2%",
        "FED: Powell hints at potential rate pause in January",
        "CRYPTO: BTC breaches $100k for the first time in history",
        "POLYX: New arbitrage opportunity detected in 'NBA Winner' markets",
        "MARKETS: Open interest on Polymarket hits record $2.5B"
    ]
    current_index = 0

    def on_mount(self) -> None:
        self.update_news()

    @work
    async def update_news(self) -> None:
        while True:
            item = self.news_items[self.current_index % len(self.news_items)]
            self.update(f"[bold yellow]NEWS FLASH:[/bold yellow] {item}")
            self.current_index += 1
            await asyncio.sleep(5)

class QuickOrderModal(ModalScreen):
    """Confirm order before execution"""
    def __init__(self, market: Market, side: Side):
        super().__init__()
        self.market = market
        self.side = side
    def compose(self) -> ComposeResult:
        with Vertical(id="modal_dialog"):
            yield Label(f"CONFIRM {self.side.value.upper()} ORDER")
            yield Label(f"Market: {self.market.question}")
            # yield Label(f"Price: ${self.market.price:.2f}") # Price not directly in Market model now
            with Horizontal(classes="item"):
                yield Label("Amount ($):")
                yield Input(placeholder="100", id="order_amount")
            with Horizontal(classes="item"):
                yield Button("Execute", variant="success", id="confirm")
                yield Button("Cancel", variant="error", id="cancel")
    @on(Button.Pressed, "#confirm")
    def confirm(self) -> None:
        amt = self.query_one("#order_amount", Input).value
        try:
             amount = float(amt or 0)
             # Basic return, handle_order will fill in price from current OB or state
             self.dismiss({"amount": amount, "side": self.side})
        except ValueError:
             self.app.notify("Invalid amount", severity="error")
             
    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None: self.dismiss(None)

class OrderbookDepth(Static):
    """Widget to display orderbook depth"""
    snapshot: reactive[Optional[OrderBook]] = reactive(None)

    def render(self) -> RenderableType:
        if not self.snapshot or (not self.snapshot.bids and not self.snapshot.asks):
            return Panel("Orderbook: No data", border_style="red")
        
        bids = self.snapshot.bids[:5]
        asks = self.snapshot.asks[:5]
        
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Bids", justify="right")
        table.add_column("Px", justify="center")
        table.add_column("Asks", justify="left")
        
        max_size = 1.0
        all_sizes = [float(x.size) for x in bids + asks]
        if all_sizes:
            max_size = max(all_sizes)

        for i in range(max(len(bids), len(asks))):
            b = bids[i] if i < len(bids) else None
            a = asks[i] if i < len(asks) else None
            
            table.add_row(
                Bar(max_size, 0, float(b.size), color="green") if b else "",
                f"[bold cyan]{b.price if b else (a.price if a else '')}[/]",
                Bar(max_size, 0, float(a.size), color="red") if a else ""
            )
            
        # Standard imbalance: bids - asks
        imbalance = sum(b.size for b in bids) - sum(a.size for a in asks)
        title = f"Orderbook Depth Δ={imbalance:+.0f}"
        return Panel(table, title=title, border_style="blue")

class MarketMetadata(Static):
    """Widget to display key market data points in a table"""
    market: reactive[Optional[Market]] = reactive(None)

    def render(self) -> RenderableType:
        if not self.market:
            return Panel("Metadata: No market selected", border_style="dim")
        
        m = self.market
        extra = m.metadata or {}
        
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Key", style="bold cyan", width=15)
        table.add_column("Value", style="bold white")
        
        table.add_row("Ticker", f"[green]{m.id}[/]")
        table.add_row("Status", f"[green]{m.status.value.upper()}[/]")
        
        # Mapping varied metadata
        if m.provider == "kalshi":
            table.add_row("24h Volume", f"[bold white]{extra.get('volume_24h', 0):,.0f}[/] contracts")
            table.add_row("Liquidity", f"[bold green]${extra.get('liquidity', 0)/100.0:,.2f}[/]")
        else:
            table.add_row("24h Volume", f"[bold white]{extra.get('volume24hr', 0):,.0f}[/]")
            table.add_row("Liquidity", f"[bold green]${extra.get('liquidity', 0):,.2f}[/]")

        return Panel(table, title="Market Metrics", border_style="cyan")

class MarketDetail(Vertical):
    """Focused view of a single market"""
    market = reactive(None)
    current_tid = None

    def compose(self) -> ComposeResult:
        yield Label("Select a market", id="detail_title")
        yield MarketMetadata(id="market_metadata")
        yield OrderbookDepth(id="depth_wall")

    def watch_market(self, market: Optional[Market]) -> None:
        if market:
            self.query_one("#detail_title", Label).update(f"FOCUS: {market.question}")
            self.setup_market(market)

    @work(exclusive=True)
    async def setup_market(self, market: Market) -> None:
        """Fetch static data and handle WS subscription"""
        try:
            multi_series = MultiLineSeries(title=market.question)
            
            if market.provider == "kalshi":
                # 1. Fetch History
                # (Logic would go here to fetch and populate multi_series)
                
                # 2. Setup Orderbook Snapshot
                b = await self.app.kalshi.get_orderbook(market.id)
                self.query_one("#depth_wall", OrderbookDepth).snapshot = b
                
                # 3. WS Subscription
                if self.current_tid:
                    # Unsubscribe logic
                    pass
                self.current_tid = market.id
                await self.app.kalshi_ws.subscribe(market.id)
                self.app.kalshi_ws.add_callback("orderbook", self.on_k_ob)
                self.app.kalshi_ws.add_callback("trade", self.on_k_trade)

            else:
                # Polymarket Logic
                # (Polymarket-specific history and OB setup)
                ctids = extra = market.metadata.get("clobTokenIds", [])
                if isinstance(ctids, str): ctids = json.loads(ctids)
                
                if ctids:
                    tid = ctids[0]
                    b = await self.app.poly.get_orderbook(tid)
                    self.query_one("#depth_wall", OrderbookDepth).snapshot = b
                    
                    if self.current_tid:
                        await self.app.ws_client.unsubscribe(self.current_tid, self.on_ws_message)
                    self.current_tid = tid
                    await self.app.ws_client.subscribe(tid, self.on_ws_message)

        except Exception as e:
            self.app.notify(f"Sync Error: {e}", severity="error")

    def on_ws_message(self, data: Dict[str, Any]) -> None:
        """Callback for real-time updates (Polymarket)"""
        # (Map raw WS data to models)
        pass

    async def on_k_ob(self, data: Dict) -> None:
        """Handle Kalshi OB updates (already standardized by WS class)"""
        self.query_one("#depth_wall", OrderbookDepth).snapshot = OrderBook(
            market_id=data["market_ticker"],
            bids=[PriceLevel(**b) for b in data["bids"]],
            asks=[PriceLevel(**a) for a in data["asks"]],
            timestamp=0.0
        )

    async def on_k_trade(self, trade: Dict) -> None:
         if self.parent:
             tape = self.app.query_one("#tape_view", TimeAndSales)
             if tape: tape.add_trade(trade)

class TimeAndSales(Static):
    """Real-time trade tape"""
    def compose(self) -> ComposeResult:
        yield Label("TIME & SALES", classes="section_title")
        yield DataTable(id="tape_table")

    def on_mount(self) -> None:
        table = self.query_one("#tape_table", DataTable)
        table.add_columns("Time", "Px", "Size", "Side")
        table.cursor_type = "row"

    def add_trade(self, trade: Dict) -> None:
        table = self.query_one("#tape_table", DataTable)
        ts = trade.get("time", "")[-8:]
        side_color = "green" if trade.get("side") == "buy" else "red"
        table.add_row(ts, f"${trade.get('price', 0):.2f}", str(trade.get("size", 0)), f"[{side_color}]{trade.get('side', 'N/A').upper()}[/]", at=0)
        if table.row_count > 50: table.remove_row(table.get_row_at(50).key)

class PortfolioView(Container):
    """Unified Portfolio and Order Management"""
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("PORTFOLIO", classes="p_title")
            yield DataTable(id="positions_table")
            yield Label("ACTIVE ORDERS", classes="p_title")
            yield DataTable(id="orders_table")
            with Horizontal(id="p_controls"):
                yield Button("Refresh", id="p_refresh")

    def on_mount(self) -> None:
        self.query_one("#positions_table", DataTable).add_columns("Symbol", "Size", "Entry", "PnL", "Prov")
        self.query_one("#orders_table", DataTable).add_columns("ID", "Symbol", "Side", "Px", "Size", "Status")
        self.load_data()

    @work(exclusive=True)
    async def load_data(self) -> None:
        try:
            pos_tasks = [self.app.poly.get_positions(), self.app.kalshi.get_positions()]
            order_tasks = [self.app.poly.get_orders(), self.app.kalshi.get_orders()]
            
            p_results = await asyncio.gather(*pos_tasks, return_exceptions=True)
            o_results = await asyncio.gather(*order_tasks, return_exceptions=True)
            
            pt = self.query_one("#positions_table", DataTable); pt.clear()
            for res in p_results:
                if isinstance(res, list):
                    for p in res:
                        pt.add_row(p.market_id, str(p.size), f"${p.avg_price:.2f}", f"${p.realized_pnl:.2f}", "K" if p.market_id.startswith("KX") else "P")

            ot = self.query_one("#orders_table", DataTable); ot.clear()
            for res in o_results:
                if isinstance(res, list):
                    for o in res:
                        ot.add_row(o.id[:8], o.market_id, o.side.value.upper(), f"${o.price:.2f}", str(o.size), o.status.value.upper())
        except Exception as e:
            self.app.notify(f"Load error: {e}", severity="error")

class DashboardApp(App):
    """PolyCLI Bloomberg Terminal"""
    markets_cache: Dict[str, Market] = {}
    watchlist: Set[str] = set()
    selected_provider: reactive[str] = reactive("polymarket")
    
    CSS_PATH = "tui.css" # Assume external CSS for brevity or keep internal
    BINDINGS = [
        ("q", "quit", "Quit"), ("r", "refresh", "Refresh"),
        ("b", "buy", "Buy"), ("s", "sell", "Sell"),
        ("w", "toggle_watchlist", "Watchlist"), ("/", "focus_search", "Search"),
        ("a", "show_arb", "Arbitrage"), ("d", "show_dash", "Dashboard"),
        ("p", "show_portfolio", "Portfolio"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with ContentSwitcher(initial="dashboard", id="switcher"):
            with Container(id="dashboard"):
                 with Container(id="main_grid"):
                    with Vertical(id="market_sidebar"):
                        yield Label("MARKETS", classes="title")
                        with RadioSet(id="provider_radios"):
                             yield RadioButton("Polymarket", value=True, id="p_poly")
                             yield RadioButton("Kalshi", id="p_kalshi")
                             yield RadioButton("Both", id="p_both")
                        yield Input(placeholder="Search...", id="search_box")
                        yield DataTable(id="market_list")
                        yield DataTable(id="watch_list", classes="title")
                    with Vertical(id="detail_panel"):
                        yield MarketDetail(id="market_focus")
                        yield TimeAndSales(id="tape_view")
            with Container(id="portfolio"): yield PortfolioView()
        yield NewsTicker()
        yield Footer()

    def on_mount(self) -> None:
        self.poly = PolyProvider()
        self.kalshi = KalshiProvider()
        self.ws_client = PolymarketWebSocket(); self.ws_client.start()
        self.kalshi_ws = KalshiWebSocket(); self.call_later(self.kalshi_ws.connect)
        
        mlist = self.query_one("#market_list", DataTable); mlist.add_columns("Market", "Px", "Src")
        self.update_markets()

    @work(exclusive=True)
    async def update_markets(self) -> None:
        try:
            m = await self.poly.get_markets()
            table = self.query_one("#market_list", DataTable); table.clear()
            for market in m:
                table.add_row(market.question[:20], "0.50", "POLY", key=market.id)
                self.markets_cache[market.id] = market
        except Exception as e: self.notify(str(e))

    def action_show_portfolio(self) -> None: self.query_one("#switcher").current = "portfolio"
    def action_show_dash(self) -> None: self.query_one("#switcher").current = "dashboard"

    @on(DataTable.RowSelected, "#market_list")
    def select_market(self, event: DataTable.RowSelected) -> None:
        m = self.markets_cache.get(event.row_key.value)
        if m: self.query_one("#market_focus", MarketDetail).market = m

if __name__ == "__main__":
    app = DashboardApp()
    app.run()
