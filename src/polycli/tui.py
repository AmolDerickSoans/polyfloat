from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label, Input, Button, ContentSwitcher, RadioSet, RadioButton
from dotenv import load_dotenv

load_dotenv()
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
from polycli.providers.base import MarketData, OrderArgs, OrderSide, OrderType
from polycli.models import PriceSeries, PricePoint, OrderBookSnapshot, MultiLineSeries
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
    def __init__(self, market: MarketData, side: OrderSide):
        super().__init__()
        self.market = market
        self.side = side
    def compose(self) -> ComposeResult:
        with Vertical(id="modal_dialog"):
            yield Label(f"CONFIRM {self.side.upper()} ORDER")
            yield Label(f"Market: {self.market.title}")
            yield Label(f"Price: ${self.market.price:.2f}")
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
             self.dismiss(OrderArgs(token_id=self.market.token_id, side=self.side, amount=amount, price=self.market.price))
        except ValueError:
             self.app.notify("Invalid amount", severity="error")
             
    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None: self.dismiss(None)

class OrderbookDepth(Static):
    """Widget to display orderbook depth"""
    snapshot: reactive[Optional[OrderBookSnapshot]] = reactive(None)

    def render(self) -> RenderableType:
        if not self.snapshot or (not self.snapshot.bids and not self.snapshot.asks):
            return Panel("Orderbook: No data", border_style="red")
        
        bids = sorted(self.snapshot.bids, key=lambda x: float(x['price']), reverse=True)[:5]
        asks = sorted(self.snapshot.asks, key=lambda x: float(x['price']))[:5]
        
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Bids", justify="right")
        table.add_column("Px", justify="center")
        table.add_column("Asks", justify="left")
        
        max_size = 1.0
        # Calculate max size for bar scaling
        all_sizes = [float(x['size']) for x in bids + asks]
        if all_sizes:
            max_size = max(all_sizes)

        for i in range(max(len(bids), len(asks))):
            b = bids[i] if i < len(bids) else None
            a = asks[i] if i < len(asks) else None
            
            table.add_row(
                Bar(max_size, 0, float(b['size']), color="green") if b else "",
                f"[bold cyan]{b['price'] if b else (a['price'] if a else '')}[/]",
                Bar(max_size, 0, float(a['size']), color="red") if a else ""
            )
            
        imbalance = self.snapshot.imbalance()
        title = f"Orderbook Depth Δ={imbalance:+.0f}"
        return Panel(table, title=title, border_style="blue")

class MarketDetail(Vertical):
    """Focused view of a single market"""
    market = reactive(None)
    current_tid = None

    def compose(self) -> ComposeResult:
        yield Label("Select a market", id="detail_title")
        yield OrderbookDepth(id="depth_wall")

    def watch_market(self, market: Optional[MarketData]) -> None:
        if market:
            self.query_one("#detail_title", Label).update(f"FOCUS: {market.title}")
            self.setup_market(market)

    @work(exclusive=True)
    async def setup_market(self, market: MarketData) -> None:
        """Fetch static data and handle WS subscription"""
        poly = PolyProvider()
        try:
            # 1. Determine if this is part of a larger event
            slug = market.extra_data.get("slug") or market.extra_data.get("event_slug")
            event_data = {}
            if slug:
                event_data = await poly.get_event_by_slug(slug)
            
            # 2. Identify all outcomes (markets) to plot
            # If event_data found, use its markets. Otherwise fallback to single market.
            markets_to_plot = []
            if event_data and "markets" in event_data:
                markets_to_plot = event_data["markets"]
            else:
                # Fallback structure
                markets_to_plot = [{"id": market.token_id, "question": market.title, "clobTokenIds": market.extra_data.get("clob_token_ids")}]

            self.app.notify(f"Fetching history for {len(markets_to_plot)} outcomes...", severity="information")

            # 3. Parallel fetch of history for all outcomes
            tasks = []
            valid_markets = []
            
            for m in markets_to_plot:
                # Extract CLOB Token ID
                ctid = None
                if "clobTokenIds" in m:
                    raw = m["clobTokenIds"]
                    try:
                        # Sometimes it's a list, sometimes a string representation of a list
                        if isinstance(raw, str):
                            ctid = json.loads(raw)[0]
                        elif isinstance(raw, list):
                            ctid = raw[0]
                    except:
                        pass
                
                # If we couldn't parse it from event, try the fallback from the input market obj
                if not ctid and m["id"] == market.token_id:
                     raw = market.extra_data.get("clob_token_ids", "[]")
                     ctid = json.loads(raw)[0] if json.loads(raw) else None

                if ctid:
                    tasks.append(poly.get_history(ctid))
                    valid_markets.append(m)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 4. Build MultiLineSeries
            multi_series = MultiLineSeries(title=event_data.get("title", market.title))
            colors = ["#2ecc71", "#e74c3c", "#3498db", "#f1c40f", "#9b59b6", "#e67e22"]
            
            for i, res in enumerate(results):
                if isinstance(res, list) and res:
                    m_info = valid_markets[i]
                    name = m_info.get("groupItemTitle", m_info.get("question", "Unknown"))
                    
                    # Clean up name (e.g. remove "Winner - ")
                    series = PriceSeries(
                        name=name,
                        color=colors[i % len(colors)],
                        points=[PricePoint(t=float(p["t"]), p=float(p["p"])) for p in res],
                        max_size=1000
                    )
                    multi_series.add_trace(series)

            # 5. Launch Chart
            metadata = {
                "volume_24h": market.volume_24h,
                "liquidity": market.liquidity,
                "end_date": market.end_date,
                "description": market.description,
                "is_watched": market.token_id in self.app.watchlist,
                "token_id": market.token_id # For reference
            }
            ChartManager().plot(multi_series, metadata=metadata)
            
            # 6. Setup Orderbook (for the SPECIFICALLY selected market only)
            token_ids = json.loads(market.extra_data.get("clob_token_ids", "[]"))
            if token_ids:
                tid = token_ids[0]
                b = await poly.get_orderbook(tid)
                snapshot = OrderBookSnapshot(
                    bids=b.get("bids", []),
                    asks=b.get("asks", [])
                )
                self.query_one("#depth_wall", OrderbookDepth).snapshot = snapshot
                
                # Live Sync
                if self.current_tid:
                    await self.app.ws_client.unsubscribe(self.current_tid, self.on_ws_message)
                    await self.app.kalshi_ws.subscribe(self.current_tid) # Re-sub to old? No, this logic is for Polymarket.
                
                self.current_tid = tid
                
                if market.provider == "kalshi":
                     await self.app.kalshi_ws.subscribe(tid)
                     # Callbacks are global, handled by app level distribution or we add specific here
                     self.app.kalshi_ws.add_callback("orderbook", self.on_k_ob)
                     self.app.kalshi_ws.add_callback("trade", self.on_k_trade)
                else:
                     await self.app.ws_client.subscribe(tid, self.on_ws_message)

        except Exception as e:
            self.app.notify(f"Sync Error: {e}", severity="error")
            import traceback
            traceback.print_exc()

    def on_ws_message(self, data: Dict[str, Any]) -> None:
        """Callback for real-time updates"""
        if "bids" in data or "asks" in data:
            self.query_one("#depth_wall", OrderbookDepth).snapshot = OrderBookSnapshot(
                bids=data.get("bids", []),
                asks=data.get("asks", [])
            )
            
        if "price" in data:
             # Real-time chart updates would go here via ChartManager().update()
             # For now, we rely on the initial load as PyWry update logic is complex
            pass

    async def on_k_ob(self, data: Dict) -> None:
        """Handle Kalshi OB updates"""
        # data is raw delta or snapshot
        # For simplify, we assume we just trigger a refresh or apply delta
        # Since applying delta is complex, we might just re-fetch snapshot occasionally or use delta logic if implemented.
        # For TUI demo, let's just indicate activity or fetch snapshot if "snapshot" type.
        pass

    async def on_k_trade(self, trade: Dict) -> None:
         # Forward to Tape
         if self.parent:
             tape = self.parent.parent.query_one("#tape_view", TimeAndSales)
             if tape: tape.add_trade(trade)

class TimeAndSales(Static):
    """Real-time trade tape"""
    trades: reactive[List[Dict]] = reactive([])
    
    def compose(self) -> ComposeResult:
        yield Label("TIME & SALES", classes="section_title")
        yield DataTable(id="tape_table")

    def on_mount(self) -> None:
        table = self.query_one("#tape_table", DataTable)
        table.add_columns("Time", "Px", "Size", "Side")
        table.cursor_type = "row"

    def add_trade(self, trade: Dict) -> None:
        """Add a trade to the top of the tape"""
        table = self.query_one("#tape_table", DataTable)
        ts = trade.get("time", "")[-8:] # Simple timestamp
        side_color = "green" if trade.get("side") == "buy" else "red"
        
        table.add_row(
            ts, 
            f"${trade.get('price', 0):.2f}", 
            str(trade.get("size", 0)), 
            f"[{side_color}]{trade.get('side', 'N/A').upper()}[/]",
            at=0
        )
        # Keep only last 50
        if table.row_count > 50:
            table.remove_row(table.get_row_at(50).key)

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
                yield Button("Cancel Selected Order", variant="error", id="p_cancel")

    def on_mount(self) -> None:
        pt = self.query_one("#positions_table", DataTable)
        pt.add_columns("Symbol", "Size", "Entry", "Value", "PnL", "Prov")
        
        ot = self.query_one("#orders_table", DataTable)
        ot.add_columns("ID", "Symbol", "Side", "Px", "Size", "Status")
        
        self.load_data()

    @on(Button.Pressed, "#p_refresh")
    async def load_data(self) -> None:
        self.query_one("#p_refresh", Button).disabled = True
        try:
            # Parallel Fetch
            p_poly, p_kalshi = await asyncio.gather(
                PolyProvider().get_positions(),
                KalshiProvider().get_positions(),
                return_exceptions=True
            )
            
            # Positions
            pt = self.query_one("#positions_table", DataTable)
            pt.clear()
            
            combined_pos = (p_poly if isinstance(p_poly, list) else []) + \
                           (p_kalshi if isinstance(p_kalshi, list) else [])
                           
            for p in combined_pos:
                pnl_color = "green" if p.get("pnl", 0) >= 0 else "red"
                val = p.get("size", 0) * p.get("current_price", 0) # Approx
                if val == 0 and p.get("entry_price"): val = p["size"] * p["entry_price"]
                
                pt.add_row(
                    p["symbol"],
                    str(p["size"]),
                    f"${p.get('entry_price', 0):.2f}",
                    f"${val:.2f}",
                    f"[{pnl_color}]${p.get('pnl', 0):.2f}[/]",
                    p["provider"].upper()
                )
                
            # Orders (Placeholder as Providers don't fully support list_orders yet)
            # We would fetch open orders here.
            
        except Exception as e:
            self.app.notify(f"Portfolio Error: {e}", severity="error")
        
        self.query_one("#p_refresh", Button).disabled = False

    @on(Button.Pressed, "#p_cancel")
    async def cancel_selected(self) -> None:
        ot = self.query_one("#orders_table", DataTable)
        # Implementation depends on logic
        pass

class DashboardApp(App):
    """PolyCLI Bloomberg Terminal"""
    markets_cache: Dict[str, MarketData] = {}
    all_markets: List[MarketData] = []
    focused_market: Optional[MarketData] = None
    watchlist: Set[str] = set()
    selected_provider: reactive[str] = reactive("polymarket")
    _search_timer: Optional[asyncio.TimerHandle] = None
    
    CSS = """
    Screen { background: #0d1117; color: #c9d1d9; }
    #main_grid { layout: grid; grid-size: 2; grid-columns: 3fr 7fr; height: 1fr; }
    #market_sidebar { border-right: tall #30363d; height: 100%; }
    #detail_panel { padding: 1; height: 100%; }
    MarketDetail { height: 100%; }
    NewsTicker { height: 3; background: #161b22; border-top: solid #58a6ff; padding: 1; }
    .title { text-style: bold; color: #58a6ff; background: #161b22; padding: 0 1; text-align: center; }
    DataTable { height: 1fr; background: #0d1117; border: none; }
    PriceChart { height: 30; border: solid #30363d; margin: 1 0; }
    OrderbookDepth { height: 20; border: solid #30363d; }
    .info_box { margin: 1; padding: 1; border: tall #58a6ff; text-align: center; }
    #modal_dialog { background: #161b22; border: solid cyan; padding: 2; width: 40; height: 15; align: center middle; }
    #modal_dialog .item { height: 3; margin-top: 1; }
    #search_box { margin: 1; border: solid #30363d; border-title-align: left; }
    
    /* Arbitrage Styles */
    ArbitrageScanner { height: 100%; }
    #arb_header { background: #161b22; color: #58a6ff; text-align: center; text-style: bold; }
    #arb_controls { height: 3; margin: 1; align: center middle; }
    #arb_controls Button { margin: 0 1; }
    #arb_table { height: 1fr; border: solid #30363d; }
    
    /* Portfolio Styles */
    PortfolioView { padding: 1; }
    .p_title { text-style: bold; color: #58a6ff; background: #161b22; margin-top: 1; }
    #p_controls { height: 3; margin-top: 1; }
    
    /* Time & Sales */
    TimeAndSales { height: 20; border: solid #30363d; }
    .section_title { background: #161b22; color: yellow; text-align: center; }
    
    #provider_radios { height: 1; border: none; margin: 0; padding: 0; width: 100%; layout: horizontal; }
    RadioSet > RadioButton { width: auto; margin-right: 1; }
    
    #search_box { margin-top: 0; margin-bottom: 1; height: 3; border: solid #30363d; border-title-align: left; }
    
    /* Arbitrage Styles */
    
    """
    BINDINGS = [
        ("q", "quit", "Quit"), 
        ("r", "refresh", "Refresh"),
        ("b", "buy", "Buy"),
        ("s", "sell", "Sell"),
        ("w", "toggle_watchlist", "Watchlist"),
        ("/", "focus_search", "Search"),
        ("a", "show_arb", "Arbitrage"),
        ("d", "show_dash", "Dashboard"),
        ("p", "show_portfolio", "Portfolio"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with ContentSwitcher(initial="dashboard", id="switcher"):
            with Container(id="dashboard"):
                 with Container(id="main_grid"):
                    with Vertical(id="market_sidebar"):
                        yield Label("MARKETS", classes="title")
                        with Horizontal(classes="provider_select"):
                             with RadioSet(id="provider_radios"):
                                 yield RadioButton("Polymarket", value=True, id="p_poly")
                                 yield RadioButton("Kalshi", id="p_kalshi")
                                 yield RadioButton("Both", id="p_both")
                        yield Input(placeholder="Search markets...", id="search_box")
                        yield DataTable(id="market_list")
                        yield Label("WATCHLIST [Hotkey: 'w']", classes="title")
                        yield DataTable(id="watch_list")
                    with Vertical(id="detail_panel"):
                        yield MarketDetail(id="market_focus")
                        yield TimeAndSales(id="tape_view")
            
            with Container(id="arbitrage"):
                 yield ArbitrageScanner()
                 
            with Container(id="portfolio"):
                 yield PortfolioView()
        
        yield NewsTicker()
        yield Footer()

    def on_mount(self) -> None:
        self.ws_client = PolymarketWebSocket()
        self.ws_client.start()
        
        self.kalshi_ws = KalshiWebSocket()
        self.call_later(self.start_kalshi_ws)
        
        mlist = self.query_one("#market_list", DataTable); mlist.cursor_type = "row"; mlist.add_columns("Market", "Px", "Vol", "Src")
        wlist = self.query_one("#watch_list", DataTable); wlist.cursor_type = "row"; wlist.add_columns("Market", "Px")
        self.update_markets()

    def action_show_arb(self) -> None:
        self.query_one("#switcher", ContentSwitcher).current = "arbitrage"
        self.notify("Switched to Arbitrage Scanner")
        
    def action_show_dash(self) -> None:
        self.query_one("#switcher", ContentSwitcher).current = "dashboard"
        self.notify("Switched to Dashboard")

    def action_show_portfolio(self) -> None:
        self.query_one("#switcher", ContentSwitcher).current = "portfolio"
        self.query_one(PortfolioView).load_data()
        self.notify("Switched to Portfolio")
    
    async def start_kalshi_ws(self) -> None:
        await self.kalshi_ws.connect()
        await self.kalshi_ws.subscribe_user_channels()

    async def on_unmount(self) -> None:
        if hasattr(self, "ws_client"):
            await self.ws_client.stop()
        if hasattr(self, "kalshi_ws"):
            await self.kalshi_ws.disconnect()

    @work(exclusive=True)
    async def update_markets(self) -> None:
        poly = PolyProvider()
        try:
            self.all_markets = await poly.get_markets(limit=250)
            self.filter_markets("")
        except Exception as e:
            self.notify(f"Market Load Error: {e}", severity="error")

    def filter_markets(self, query: str) -> None:
        table = self.query_one("#market_list", DataTable)
        table.clear()
        query = query.lower()
        for m in self.all_markets:
            if query in m.title.lower():
                src_tag = f"[blue]POLY[/]" if m.provider == "polymarket" else f"[green]KALSHI[/]"
                table.add_row(m.title[:20], f"${m.price:.2f}", f"${m.volume_24h/1000:.0f}k", src_tag, key=m.token_id)
                self.markets_cache[m.token_id] = m

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "provider_radios":
             if event.pressed.id == "p_poly": self.selected_provider = "polymarket"
             elif event.pressed.id == "p_kalshi": self.selected_provider = "kalshi"
             else: self.selected_provider = "all"
             self.notify(f"Provider switched to {self.selected_provider.upper()}")
             self.update_markets()

    @on(Input.Changed, "#search_box")
    def on_search(self, event: Input.Changed) -> None:
        """Handle search input with debounce"""
        query = event.value.strip()
        if not query:
            if self._search_timer:
                self._search_timer.cancel()
            self.filter_markets("") # Revert to default view
            return
        self.debounced_search(query)

    @work(exclusive=True)
    async def debounced_search(self, query: str) -> None:
        """Wait for debounce and then perform search"""
        await asyncio.sleep(0.3)
        await self.perform_search(query)

    async def perform_search(self, query: str) -> None:
        """Execute server-side search via Providers"""
        table = self.query_one("#market_list", DataTable)
        table.clear()
        table.add_row(f"[italic cyan]Searching ({self.selected_provider})...", "", "", "")
        
        try:
            results = []
            tasks = []
            
            # Polymarket
            if self.selected_provider in ["polymarket", "all"]:
                tasks.append(PolyProvider().search(query))
            
            # Kalshi
            if self.selected_provider in ["kalshi", "all"]:
                # Use updated KalshiProvider search which filters Events and fetches matching markets
                tasks.append(KalshiProvider().search(query))

            # Gather
            gathered_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in gathered_results:
                if isinstance(res, list):
                    results.extend(res)
            
            table.clear()
            if not results:
                table.add_row("[red]No results found", "", "", "")
                return
            
            # Limit results
            results = results[:50]
                
            for m in results:
                try:
                    display_title = m.title[:50] + ("..." if len(m.title) > 50 else "")
                    vol_fmt = f"${m.volume_24h/1000:.1f}k" if m.volume_24h >= 1000 else f"${m.volume_24h:.0f}"
                    
                    # Determine Source Color
                    src_tag = f"[blue]POLY[/]" if m.provider == "polymarket" else f"[green]KALSHI[/]"
                    
                    table.add_row(
                        display_title, 
                        f"${m.price:.2f}", 
                        vol_fmt,
                        src_tag,
                        key=m.token_id
                    )
                    self.markets_cache[m.token_id] = m
                except Exception:
                    continue
            
            self.notify(f"Found {len(results)} matches", severity="information")
            
        except Exception as e:
            self.notify(f"Search Error: {e}", severity="error")
            table.clear()
            table.add_row("[red]Search Failed", "", "", str(e))

    def on_key(self, event) -> None:
        """Global Key Handler"""
        # Search Box Navigation
        if self.query_one("#search_box").has_focus:
            if event.key == "down":
                 self.query_one("#market_list").focus()
            elif event.key == "escape":
                 self.query_one("#market_list").focus()
    
    def action_focus_search(self) -> None:
        self.query_one("#search_box", Input).focus()

    @on(DataTable.RowSelected, "#market_list")
    def select_market(self, event: DataTable.RowSelected) -> None:
        m = self.markets_cache.get(event.row_key.value)
        if m: self.focused_market = m; self.query_one("#market_focus", MarketDetail).market = m

    @on(DataTable.RowSelected, "#watch_list")
    def select_watchlist_market(self, event: DataTable.RowSelected) -> None:
        m = self.markets_cache.get(event.row_key.value)
        if m: self.focused_market = m; self.query_one("#market_focus", MarketDetail).market = m

    def action_toggle_watchlist(self) -> None:
        if self.focused_market:
            tid = self.focused_market.token_id
            wlist = self.query_one("#watch_list", DataTable)
            if tid in self.watchlist:
                self.watchlist.remove(tid)
                wlist.remove_row(tid)
                self.notify("Removed from watchlist")
            else:
                self.watchlist.add(tid)
                wlist.add_row(self.focused_market.title[:15], f"${self.focused_market.price:.2f}", key=tid)
                self.notify("Added to watchlist", severity="information")

    def action_buy(self) -> None:
        if self.focused_market: self.push_screen(QuickOrderModal(self.focused_market, OrderSide.BUY), self.handle_order)
    def action_sell(self) -> None:
        if self.focused_market: self.push_screen(QuickOrderModal(self.focused_market, OrderSide.SELL), self.handle_order)

    async def handle_order(self, order: Optional[OrderArgs]) -> None:
        if order:
            # Route to Correct Provider
            if self.focused_market and self.focused_market.provider == "kalshi":
                 res = await KalshiProvider().place_order(order)
            else:
                 res = await PolyProvider().place_order(order)

            self.notify("Order Submitted!" if res.status in ["submitted", "pending"] else f"Error: {res.status}", 
                        severity="information" if res.status in ["submitted", "pending"] else "error")

if __name__ == "__main__":
    app = DashboardApp()
    app.run()