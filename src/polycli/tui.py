from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    Label,
    Input,
    Button,
    ContentSwitcher,
    RadioSet,
    RadioButton,
)
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
from polycli.models import (
    PriceSeries,
    PricePoint,
    OrderBook,
    MultiLineSeries,
    Market,
    Trade,
    Side,
    OrderStatus,
    Order,
    PriceLevel,
    MarketStatus,
)
from polycli.utils.launcher import ChartManager
from polycli.arbitrage.tui_widget import ArbitrageScanner
from rich.panel import Panel
from rich.table import Table
from rich.bar import Bar
from rich.console import RenderableType
from rich.text import Text
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.tui_agent_panel import AgentStatusPanel
from polycli.tui_agent_chat import AgentChatInterface
from polycli.agents import SupervisorAgent


class NewsTicker(Static):
    """Scrolling news ticker at the bottom of the screen"""

    news_items = [
        "US Election 2024: Trump leads in Pennsylvania by 2%",
        "FED: Powell hints at potential rate pause in January",
        "CRYPTO: BTC breaches $100k for the first time in history",
        "POLYX: New arbitrage opportunity detected in 'NBA Winner' markets",
        "MARKETS: Open interest on Polymarket hits record $2.5B",
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
    def cancel(self) -> None:
        self.dismiss(None)


class OrderbookDepth(Static):
    """Widget to display orderbook depth"""

    snapshot: reactive[Optional[OrderBook]] = reactive(None)

    def render(self) -> RenderableType:
        if not self.snapshot or (not self.snapshot.bids and not self.snapshot.asks):
            return Panel("Orderbook: No data", border_style="red")

        # Show more depth (10 levels)
        bids = self.snapshot.bids[:10]
        asks = self.snapshot.asks[:10]

        table = Table(show_header=True, expand=True, box=None, padding=(0, 1))
        table.add_column("Size", justify="right", style="dim")
        table.add_column("Bid", justify="right", style="green")
        table.add_column("Ask", justify="left", style="red")
        table.add_column("Size", justify="left", style="dim")

        # Calculate cumulative sizes for depth visualization
        max_size = 1.0
        all_sizes = [float(x.size) for x in bids + asks]
        if all_sizes:
            max_size = max(all_sizes)

        # Build rows showing bid and ask at same level
        max_rows = max(len(bids), len(asks))
        for i in range(max_rows):
            b = bids[i] if i < len(bids) else None
            a = asks[i] if i < len(asks) else None

            bid_size = f"{b.size:,.0f}" if b else ""
            bid_price = f"${b.price:.3f}" if b else ""
            ask_price = f"${a.price:.3f}" if a else ""
            ask_size = f"{a.size:,.0f}" if a else ""

            table.add_row(bid_size, bid_price, ask_price, ask_size)

        # Calculate summary stats
        total_bid_vol = sum(b.size for b in bids)
        total_ask_vol = sum(a.size for a in asks)
        imbalance = total_bid_vol - total_ask_vol

        # Calculate mid price and spread
        mid_price = None
        spread = None
        spread_bps = None

        if bids and asks:
            best_bid = bids[0].price
            best_ask = asks[0].price
            mid_price = (best_bid + best_ask) / 2
            spread = best_ask - best_bid
            spread_bps = (spread / mid_price) * 10000 if mid_price else 0

        # Build title with key metrics
        title_parts = ["📖 Order Book"]
        if mid_price:
            title_parts.append(f"Mid: ${mid_price:.3f}")
        if spread is not None:
            title_parts.append(f"Spread: {spread_bps:.0f}bps")

        title = " | ".join(title_parts)

        # Add footer with imbalance
        footer = f"Bid Vol: {total_bid_vol:,.0f} | Ask Vol: {total_ask_vol:,.0f} | Δ: {imbalance:+,.0f}"

        return Panel(table, title=title, subtitle=footer, border_style="blue")


class MarketMetadata(Static):
    """Widget to display key market data points in a table"""

    market: reactive[Optional[Market]] = reactive(None)

    def render(self) -> RenderableType:
        if not self.market:
            return Panel("Metadata: No market selected", border_style="dim")

        m = self.market
        extra = m.metadata or {}

        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Key", style="bold cyan", width=16)
        table.add_column("Value", style="bold white")

        # Common fields
        table.add_row("Provider", f"[yellow]{m.provider.upper()}[/]")
        table.add_row(
            "Status",
            f"[green]{m.status.value.upper()}[/]"
            if m.status == MarketStatus.ACTIVE
            else f"[red]{m.status.value.upper()}[/]",
        )

        if m.provider == "kalshi":
            # Kalshi-specific metadata
            last_price = extra.get("_last_price", 0)
            prev_price = extra.get("_previous_price", 0)

            table.add_row("Ticker", f"[green]{m.id[:20]}[/]")
            table.add_row("Last Price", f"[bold white]{last_price}¢[/]")

            # Price change
            if prev_price and last_price:
                change = last_price - prev_price
                change_pct = (change / prev_price * 100) if prev_price else 0
                color = "green" if change >= 0 else "red"
                table.add_row(
                    "Change", f"[{color}]{change:+.0f}¢ ({change_pct:+.1f}%)[/]"
                )

            # Bid/Ask
            yes_bid = extra.get("_yes_bid", 0)
            yes_ask = extra.get("_yes_ask", 0)
            if yes_bid or yes_ask:
                table.add_row("Yes Bid/Ask", f"[cyan]{yes_bid}¢ / {yes_ask}¢[/]")
                spread = yes_ask - yes_bid if (yes_ask and yes_bid) else 0
                if spread:
                    table.add_row(
                        "Spread",
                        f"[yellow]{spread}¢ ({spread/yes_ask*10000:.0f} bps)[/]",
                    )

            # Volume
            volume = extra.get("_volume", 0)
            volume_24h = extra.get("_volume_24h", 0)
            table.add_row("Total Volume", f"[bold white]{volume:,.0f}[/] contracts")
            table.add_row("24h Volume", f"[bold white]{volume_24h:,.0f}[/] contracts")

            # Liquidity
            liquidity = extra.get("_liquidity", 0)
            table.add_row("Liquidity", f"[bold green]${liquidity/100.0:,.2f}[/]")

            # Open Interest
            open_interest = extra.get("_open_interest", 0)
            if open_interest:
                table.add_row(
                    "Open Interest", f"[white]{open_interest:,.0f}[/] contracts"
                )

            # Dates
            close_time = extra.get("_close_time", "")
            if close_time:
                table.add_row("Closes", f"[dim]{close_time[:10]}[/]")

        else:
            # Polymarket-specific metadata
            table.add_row("Market ID", f"[green]{m.id[:12]}...[/]")

            # Current prices
            outcome_prices = extra.get("outcomePrices", [])
            if isinstance(outcome_prices, str):
                import json

                try:
                    outcome_prices = json.loads(outcome_prices)
                except:
                    outcome_prices = []

            if len(outcome_prices) >= 2:
                yes_price = float(outcome_prices[0])
                no_price = float(outcome_prices[1])
                table.add_row(
                    "Yes Price", f"[cyan]${yes_price:.3f}[/] ({yes_price*100:.1f}%)"
                )
                table.add_row(
                    "No Price", f"[magenta]${no_price:.3f}[/] ({no_price*100:.1f}%)"
                )

            # Best bid/ask
            best_bid = extra.get("bestBid", 0)
            best_ask = extra.get("bestAsk", 0)
            if best_bid or best_ask:
                table.add_row(
                    "Best Bid/Ask", f"[cyan]${best_bid:.3f} / ${best_ask:.3f}[/]"
                )
                spread = best_ask - best_bid if (best_ask and best_bid) else 0
                if spread and best_ask:
                    table.add_row(
                        "Spread",
                        f"[yellow]${spread:.3f} ({spread/best_ask*10000:.0f} bps)[/]",
                    )

            # Price changes
            day_change = extra.get("oneDayPriceChange", 0)
            week_change = extra.get("oneWeekPriceChange", 0)
            if day_change:
                color = "green" if day_change >= 0 else "red"
                table.add_row("24h Change", f"[{color}]{day_change*100:+.2f}%[/]")
            if week_change:
                color = "green" if week_change >= 0 else "red"
                table.add_row("7d Change", f"[{color}]{week_change*100:+.2f}%[/]")

            # Volume
            volume = extra.get("volumeNum", 0) or extra.get("volume", 0)
            volume_24h = extra.get("volume24hr", 0)
            volume_1w = extra.get("volume1wk", 0)

            if isinstance(volume, str):
                volume = float(volume)
            if isinstance(volume_24h, str):
                volume_24h = float(volume_24h)

            table.add_row("Total Volume", f"[bold white]${volume:,.0f}[/]")
            table.add_row("24h Volume", f"[bold white]${volume_24h:,.0f}[/]")
            if volume_1w:
                table.add_row("7d Volume", f"[white]${volume_1w:,.0f}[/]")

            # Liquidity
            liquidity = extra.get("liquidityNum", 0) or extra.get("liquidity", 0)
            if isinstance(liquidity, str):
                liquidity = float(liquidity)
            table.add_row("Liquidity", f"[bold green]${liquidity:,.2f}[/]")

            # Competitive score
            competitive = extra.get("competitive", 0)
            if competitive:
                table.add_row("Quality Score", f"[yellow]{competitive:.2%}[/]")

            # End date
            end_date = extra.get("endDateIso", "") or extra.get("endDate", "")
            if end_date:
                table.add_row("Ends", f"[dim]{end_date[:10]}[/]")

        return Panel(table, title="Market Details", border_style="cyan")


class MarketDetail(Vertical):
    """Focused view of a single market"""

    market = reactive(None)
    current_tid = None

    def compose(self) -> ComposeResult:
        yield Label("Select a market", id="detail_title")
        with Horizontal():
            yield MarketMetadata(id="market_metadata")
            yield OrderbookDepth(id="depth_wall")

    def watch_market(self, market: Optional[Market]) -> None:
        if market:
            self.query_one("#detail_title", Label).update(f"FOCUS: {market.question}")
            self.setup_market(market)

    @work(exclusive=True)
    async def setup_market(self, market: Market) -> None:
        """Fetch static data and handle WS subscription"""
        import structlog

        logger = structlog.get_logger()

        try:
            logger.info(
                "Setting up market",
                market_id=market.id,
                provider=market.provider,
                question=market.question[:50],
            )

            # Show loading state
            self.query_one("#detail_title", Label).update(
                f"Loading: {market.question[:50]}..."
            )

            # Update metadata widget first (always works)
            self.query_one("#market_metadata", MarketMetadata).market = market

            if market.provider == "kalshi":
                logger.info("Fetching Kalshi market data", ticker=market.id)

                # Fetch Orderbook
                try:
                    b = await self.app.kalshi.get_orderbook(market.id)
                    logger.info(
                        "Kalshi orderbook fetched", bids=len(b.bids), asks=len(b.asks)
                    )

                    self.query_one("#depth_wall", OrderbookDepth).snapshot = b

                    if not b.bids and not b.asks:
                        self.app.notify("⚠ Orderbook is empty", severity="warning")
                except Exception as e:
                    logger.error(
                        "Failed to fetch Kalshi orderbook",
                        error=str(e),
                        market_id=market.id,
                    )
                    self.app.notify(f"Orderbook error: {str(e)[:50]}", severity="error")

                # WS Subscription
                try:
                    if self.current_tid and self.current_tid != market.id:
                        # TODO: Add unsubscribe logic when available
                        pass

                    self.current_tid = market.id
                    await self.app.kalshi_ws.subscribe(market.id)
                    self.app.kalshi_ws.add_callback("orderbook", self.on_k_ob)
                    self.app.kalshi_ws.add_callback("trade", self.on_k_trade)
                    logger.info("Kalshi WebSocket subscribed", ticker=market.id)
                except Exception as e:
                    logger.error("Kalshi WebSocket subscription failed", error=str(e))
                    # Non-critical, continue

                # ===== CHART DATA FETCHING (KALSHI) =====
                self.app.notify("📊 Fetching chart data...", severity="information")

                multi_series = MultiLineSeries(title=market.question)

                candles = await self.app.kalshi.get_candlesticks(
                    market.id, period="hour", limit=100
                )
                if candles:
                    series = PriceSeries(
                        name="Yes", color="#2ecc71", points=candles, max_size=1000
                    )
                    multi_series.add_trace(series)
                    self.app.notify(
                        f"✓ {len(candles)} candles loaded", severity="information"
                    )

                    metadata = {
                        "volume_24h": market.metadata.get("_volume_24h", 0),
                        "liquidity": market.metadata.get("_liquidity", 0),
                        "end_date": market.metadata.get("_close_time")
                        or market.metadata.get("endDateIso"),
                        "description": market.question,
                        "is_watched": market.id in self.app.watchlist,
                        "token_id": market.id,
                    }
                    ChartManager().plot(multi_series, metadata=metadata)
                else:
                    self.app.notify("⚠ No chart data available", severity="warning")
                # AGENTS: DO NOT DELETE THIS FUNCTIONALITY WITHOUT PRIOR PERMISSION

            else:
                # Polymarket Logic
                logger.info(
                    "Fetching Polymarket market data", condition_id=market.id[:20]
                )

                extra = market.metadata or {}
                ctids = extra.get("clobTokenIds", [])

                if isinstance(ctids, str):
                    try:
                        ctids = json.loads(ctids)
                    except Exception as e:
                        logger.error("Failed to parse clobTokenIds", error=str(e))
                        ctids = []

                if not ctids:
                    self.app.notify(
                        "⚠ No CLOB token IDs found for this market", severity="warning"
                    )
                    logger.warning(
                        "No clobTokenIds in market metadata", market_id=market.id
                    )
                    return

                tid = ctids[0]
                logger.info("Using token ID for orderbook", token_id=tid[:20])

                # Fetch Orderbook
                try:
                    b = await self.app.poly.get_orderbook(tid)
                    logger.info(
                        "Polymarket orderbook fetched",
                        bids=len(b.bids),
                        asks=len(b.asks),
                        token_id=tid[:20],
                    )

                    self.query_one("#depth_wall", OrderbookDepth).snapshot = b

                    if not b.bids and not b.asks:
                        self.app.notify("⚠ Orderbook is empty", severity="warning")
                    elif len(b.bids) > 0 and len(b.asks) > 0:
                        # Show best bid/ask as confirmation
                        best_bid = b.bids[0].price
                        best_ask = b.asks[0].price
                        logger.info(
                            "Orderbook loaded",
                            best_bid=best_bid,
                            best_ask=best_ask,
                            spread=best_ask - best_bid,
                        )

                except Exception as e:
                    logger.error(
                        "Failed to fetch Polymarket orderbook",
                        error=str(e),
                        token_id=tid[:20],
                    )
                    self.app.notify(f"Orderbook error: {str(e)[:50]}", severity="error")

                # WS Subscription
                try:
                    if self.current_tid and self.current_tid != tid:
                        await self.app.ws_client.unsubscribe(
                            self.current_tid, self.on_ws_message
                        )
                        logger.info(
                            "Unsubscribed from previous market",
                            token_id=self.current_tid[:20],
                        )

                    self.current_tid = tid
                    await self.app.ws_client.subscribe(tid, self.on_ws_message)
                    logger.info("Polymarket WebSocket subscribed", token_id=tid[:20])
                except Exception as e:
                    logger.error(
                        "Polymarket WebSocket subscription failed", error=str(e)
                    )
                    # Non-critical, continue

                # ===== CHART DATA FETCHING (POLYMARKET) =====
                self.app.notify("📊 Fetching chart data...", severity="information")

                multi_series = MultiLineSeries(title=market.question)

                # Get current prices from metadata
                outcome_prices = extra.get("outcomePrices", [])
                if isinstance(outcome_prices, str):
                    try:
                        outcome_prices = json.loads(outcome_prices)
                    except:
                        outcome_prices = []

                if outcome_prices and len(outcome_prices) >= 2:
                    # Use current prices from metadata (these are live prices)
                    current_price = float(outcome_prices[0])
                    
                    # Try to get last trade price for additional context
                    try:
                        token_ids = json.loads(extra.get("clobTokenIds", "[]"))
                        if token_ids:
                            last_trade = self.app.poly.client.get_last_trade_price(token_ids[0])
                            if last_trade and 'price' in last_trade:
                                current_price = float(last_trade['price'])
                    except Exception as e:
                        logger.warning("Could not fetch last trade price", error=str(e))

                    # Create a price history using current price
                    # Note: Polymarket does NOT provide a public historical trade data API
                    # We're using the current price as a single data point
                    import time
                    series = PriceSeries(
                        name="Yes",
                        color="#2ecc71",
                        points=[
                            PricePoint(t=time.time() - 3600, p=current_price),
                            PricePoint(t=time.time(), p=current_price),
                        ],
                        max_size=1000,
                    )
                    multi_series.add_trace(series)
                    self.app.notify(
                        f"✓ Current price loaded: ${current_price:.3f}",
                        severity="information",
                    )

                    metadata = {
                        "volume_24h": market.metadata.get("volume24hr", 0),
                        "liquidity": market.metadata.get("liquidityNum", 0),
                        "end_date": market.metadata.get("endDateIso")
                        or market.metadata.get("endDate"),
                        "description": market.question,
                        "is_watched": market.id in self.app.watchlist,
                        "token_id": market.id,
                    }
                    ChartManager().plot(multi_series, metadata=metadata)
                else:
                    self.app.notify("⚠ No chart data available", severity="warning")

            # Update title to show success
            self.query_one("#detail_title", Label).update(f"📊 {market.question}")
            logger.info("Market setup complete", market_id=market.id)

        except Exception as e:
            logger.error(
                "Market setup failed",
                error=str(e),
                market_id=market.id,
                provider=market.provider,
            )
            self.app.notify(f"Failed to load market: {str(e)}", severity="error")
            self.query_one("#detail_title", Label).update(f"❌ Error loading market")

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
            timestamp=0.0,
        )

    async def on_k_trade(self, trade: Dict) -> None:
        if self.parent:
            tape = self.app.query_one("#tape_view", TimeAndSales)
            if tape:
                tape.add_trade(trade)


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
        table.add_row(
            ts,
            f"${trade.get('price', 0):.2f}",
            str(trade.get("size", 0)),
            f"[{side_color}]{trade.get('side', 'N/A').upper()}[/]",
            at=0,
        )
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

    def on_mount(self) -> None:
        self.query_one("#positions_table", DataTable).add_columns(
            "Symbol", "Size", "Entry", "PnL", "Prov"
        )
        self.query_one("#orders_table", DataTable).add_columns(
            "ID", "Symbol", "Side", "Px", "Size", "Status"
        )
        self.load_data()

    @work(exclusive=True)
    async def load_data(self) -> None:
        try:
            pos_tasks = [self.app.poly.get_positions(), self.app.kalshi.get_positions()]
            order_tasks = [self.app.poly.get_orders(), self.app.kalshi.get_orders()]

            p_results = await asyncio.gather(*pos_tasks, return_exceptions=True)
            o_results = await asyncio.gather(*order_tasks, return_exceptions=True)

            pt = self.query_one("#positions_table", DataTable)
            pt.clear()
            for res in p_results:
                if isinstance(res, list):
                    for p in res:
                        pt.add_row(
                            p.market_id,
                            str(p.size),
                            f"${p.avg_price:.2f}",
                            f"${p.realized_pnl:.2f}",
                            "K" if p.market_id.startswith("KX") else "P",
                        )

            ot = self.query_one("#orders_table", DataTable)
            ot.clear()
            for res in o_results:
                if isinstance(res, list):
                    for o in res:
                        ot.add_row(
                            o.id[:8],
                            o.market_id,
                            o.side.value.upper(),
                            f"${o.price:.2f}",
                            str(o.size),
                            o.status.value.upper(),
                        )
        except Exception as e:
            self.app.notify(f"Load error: {e}", severity="error")


class DashboardApp(App):
    """PolyCLI Bloomberg Terminal"""

    markets_cache: Dict[str, Market] = {}
    watchlist: Set[str] = set()
    selected_provider: reactive[str] = reactive("polymarket")
    agent_mode: reactive[str] = reactive("manual") # manual, auto-approval, full-auto

    CSS_PATH = "tui.css"
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
        ("m", "cycle_agent_mode", "Agent Mode"),
        ("escape", "escape", "Back/Cancel"),
        ("enter", "enter", "Send Command"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redis_store = RedisStore(prefix="polycli:")
        self.sqlite_store = SQLiteStore(":memory:")
        self.poly = PolyProvider()
        self.kalshi = KalshiProvider()
        
        # Determine initial provider for supervisor
        initial_prov = self.poly # Default
        
        self.supervisor = SupervisorAgent(
            redis_store=self.redis_store, 
            sqlite_store=self.sqlite_store,
            provider=initial_prov
        )
        self.ws_client = PolymarketWebSocket()
        self.kalshi_ws = KalshiWebSocket()
        self.auto_loop_task = None

    def action_cycle_agent_mode(self) -> None:
        modes = ["manual", "auto-approval", "full-auto"]
        idx = modes.index(self.agent_mode)
        self.agent_mode = modes[(idx + 1) % len(modes)]
        self.notify(f"Agent Mode: {self.agent_mode.upper()}")

    def on_mount(self) -> None:
        self.ws_client.start()
        self.call_later(self.kalshi_ws.connect)
        
        # Start background agent loop
        self.auto_loop_task = asyncio.create_task(self._agent_background_loop())

        mlist = self.query_one("#market_list", DataTable)
        mlist.add_columns("Market", "Px", "Src")
        mlist.cursor_type = "row"
        self.update_markets()

    async def _agent_background_loop(self):
        """Background loop to tick agents when in autonomous modes"""
        while True:
            try:
                if self.agent_mode in ["auto-approval", "full-auto"]:
                    import structlog
                    logger = structlog.get_logger()
                    logger.info("Background Loop: Ticking TraderAgent")
                    
                    # Run the ONE_BEST_TRADE strategy
                    # Using route_command so it publishes to TUI
                    await self.supervisor.route_command("AUTO_TICK", {"input": "Find the best trade"})
                
                # Sleep for 5 minutes between ticks
                await asyncio.sleep(300)
            except Exception as e:
                await asyncio.sleep(60)
        yield Header()
        with Horizontal():
            # Left column (30%) - Controls & Agents
            with Vertical(id="left_column", classes="left-panel"):
                yield Label("Market Source", classes="section_title")
                with Horizontal(id="provider_radios_container"):
                    with RadioSet(id="provider_radios"):
                        yield RadioButton("Polymarket", id="p_poly", value=True)
                        yield RadioButton("Kalshi", id="p_kalshi")
                        yield RadioButton("Both", id="p_both")

                yield Label("Search", classes="section_title")
                yield Input(
                    placeholder="Search markets...",
                    id="search_box",
                    classes="search-input",
                )

                yield Label("Market List", classes="section_title")
                yield DataTable(id="market_list")

                yield Label("Agent Session", classes="section_title")
                yield AgentChatInterface(
                    id="chat_interface",
                    redis_store=self.redis_store,
                    supervisor=self.supervisor,
                )

            # Right column (70%) - Data & Details
            with Vertical(id="right_column", classes="right-panel"):
                yield Label("Market Focus", classes="section_title")
                yield MarketDetail(id="market_focus", classes="market-detail")

        yield Footer()

    def on_mount(self) -> None:
        self.ws_client.start()
        self.call_later(self.kalshi_ws.connect)

        mlist = self.query_one("#market_list", DataTable)
        mlist.add_columns("Market", "Px", "Src")
        mlist.cursor_type = "row"
        self.update_markets()

    @work(exclusive=True)
    async def update_markets(self) -> None:
        try:
            table = self.query_one("#market_list", DataTable)
            table.clear()
            table.add_row("Searching...", "", "")

            query = ""
            try:
                query = self.query_one("#search_box", Input).value.strip()
            except Exception:
                pass

            tasks = []
            if self.selected_provider in ["polymarket", "all"]:
                if query:
                    tasks.append(self.poly.search(query))
                else:
                    tasks.append(self.poly.get_markets())
            if self.selected_provider in ["kalshi", "all"]:
                if query:
                    tasks.append(self.kalshi.search(query))
                else:
                    tasks.append(self.kalshi.get_markets())

            results = await asyncio.gather(*tasks, return_exceptions=True)
            table.clear()

            self.markets_cache.clear()
            found_any = False
            for res in results:
                if isinstance(res, list):
                    for m in res:
                        found_any = True
                        table.add_row(
                            m.question[:40], "0.50", m.provider.upper()[:4], key=m.id
                        )
                        self.markets_cache[m.id] = m
                elif isinstance(res, Exception):
                    self.notify(f"Provider Error: {res}", severity="error")

            if not found_any:
                table.add_row("No results found", "", "")

        except Exception as e:
            self.notify(str(e))
            try:
                self.query_one("#market_list", DataTable).clear()
            except:
                pass

    @on(Input.Submitted, "#search_box")
    def on_search_submit(self):
        self.update_markets()

    @on(RadioSet.Changed, "#provider_radios")
    def on_provider_change(self, event: RadioSet.Changed):
        if event.pressed.id == "p_poly":
            self.selected_provider = "polymarket"
            self.supervisor.provider = self.poly
            self.supervisor.executor.provider = self.poly
            self.supervisor.trader.provider = self.poly
            self.supervisor.creator.provider = self.poly
        elif event.pressed.id == "p_kalshi":
            self.selected_provider = "kalshi"
            self.supervisor.provider = self.kalshi
            self.supervisor.executor.provider = self.kalshi
            self.supervisor.trader.provider = self.kalshi
            self.supervisor.creator.provider = self.kalshi
        elif event.pressed.id == "p_both":
            self.selected_provider = "all"
            # Keep previous provider for agents as 'all' isn't supported yet
        self.update_markets()

    def action_show_portfolio(self) -> None:
        self.query_one("#switcher").current = "portfolio"

    def action_show_dash(self) -> None:
        self.query_one("#switcher").current = "dashboard"

    def action_show_arb(self) -> None:
        self.notify("Arbitrage Scanner coming soon")

    def action_refresh(self) -> None:
        self.update_markets()

    def action_focus_search(self) -> None:
        self.query_one("#search_box").focus()

    def action_buy(self) -> None:
        m = self.query_one("#market_focus", MarketDetail).market
        if m:
            self.push_screen(QuickOrderModal(m, Side.BUY), self.handle_order)

    def action_sell(self) -> None:
        m = self.query_one("#market_focus", MarketDetail).market
        if m:
            self.push_screen(QuickOrderModal(m, Side.SELL), self.handle_order)

    def action_toggle_watchlist(self) -> None:
        m = self.query_one("#market_focus", MarketDetail).market
        if m:
            if m.id in self.watchlist:
                self.watchlist.remove(m.id)
                self.notify("Removed")
            else:
                self.watchlist.add(m.id)
                self.notify("Added")

    async def handle_order(self, order_data: Optional[Dict]) -> None:
        if order_data:
            m = self.query_one("#market_focus", MarketDetail).market
            if not m:
                return
            try:
                prov = self.kalshi if m.provider == "kalshi" else self.poly
                res = await prov.place_order(
                    market_id=m.id,
                    side=order_data["side"],
                    size=order_data["amount"],
                    price=0.50,
                )
                self.notify(f"Order Sent: {res.id[:8]}")
            except Exception as e:
                self.notify(f"Order Fail: {e}", severity="error")

    @on(DataTable.RowSelected, "#market_list")
    def select_market(self, event: DataTable.RowSelected) -> None:
        m = self.markets_cache.get(event.row_key)
        if m:
            self.query_one("#market_focus", MarketDetail).market = m


if __name__ == "__main__":
    app = DashboardApp()
    app.run()
