from textual.app import App, ComposeResult, Binding
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
from decimal import Decimal
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
from polycli.news.websocket_client import NewsWebSocketClient
from polycli.news.api_client import NewsAPIClient
from polycli.news.news_widget import NewsPanel
from polycli.news.alerts import NewsAlertManager, AlertConfig, DEFAULT_TERMINAL_CONFIG
from polycli.tui_news_feed import FullScreenNewsFeed
from polycli.utils.config import get_paper_mode
from polycli.emergency import EmergencyStopController, StopReason
import structlog
from polycli.analytics.widget import PerformanceDashboardWidget
from polycli.analytics.calculator import PerformanceCalculator

logger = structlog.get_logger()


class NewsTicker(Static):
    """Scrolling news ticker with real-time updates from polyfloat-news API"""

    MAX_ITEMS = 20  # Keep last 20 news items

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.news_items: List[Dict[str, Any]] = []
        self.current_index = 0
        self._fallback_items = [
            {"content": "Connecting to news service...", "impact_score": 50, "source": "system"},
        ]

    def on_mount(self) -> None:
        self._start_rotation()

    @work
    async def _start_rotation(self) -> None:
        """Rotate through news items"""
        while True:
            items = self.news_items if self.news_items else self._fallback_items
            if items:
                item = items[self.current_index % len(items)]
                self._render_item(item)
                self.current_index += 1
            await asyncio.sleep(5)

    def _render_item(self, item: Dict[str, Any]) -> None:
        """Render a single news item with impact coloring"""
        impact = item.get("impact_score", 50)
        content = item.get("title") or item.get("content", "")[:80]
        source = item.get("source", "news")

        # Color code by impact
        if impact >= 80:
            impact_tag = "[bold red]🔴 BREAKING[/bold red]"
        elif impact >= 60:
            impact_tag = "[bold yellow]🟡 HIGH[/bold yellow]"
        else:
            impact_tag = "[dim]⚪[/dim]"

        # Source badge
        source_badge = "[blue]𝕏[/blue]" if source == "nitter" else "[yellow]📰[/yellow]"

        self.update(f"{impact_tag} {source_badge} {content}")

    def add_news(self, news_data: Dict[str, Any]) -> None:
        """Add a new news item from WebSocket (called by DashboardApp)"""
        # Insert at beginning (newest first)
        self.news_items.insert(0, news_data)
        # Trim to max items
        if len(self.news_items) > self.MAX_ITEMS:
            self.news_items = self.news_items[:self.MAX_ITEMS]
        # Reset index to show new item immediately
        self.current_index = 0
        self._render_item(news_data)

    def set_unavailable(self) -> None:
        """Show unavailable message when news API is down"""
        self._fallback_items = [
            {"content": "News service unavailable - running offline", "impact_score": 30, "source": "system"},
        ]




class PaperModeIndicator(Static):
    """Visual indicator for paper trading mode"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._update_display()
    
    def _update_display(self) -> None:
        if get_paper_mode():
            self.update(
                Panel(
                    "[bold yellow]PAPER TRADING MODE[/bold yellow]\n[dim]No real money at risk[/dim]",
                    border_style="yellow",
                    padding=(0, 2)
                )
            )
        else:
            self.update("")
    
    def render(self) -> RenderableType:
        if get_paper_mode():
            return Panel(
                "[bold yellow]PAPER TRADING MODE[/bold yellow]\n[dim]No real money at risk[/dim]",
                border_style="yellow",
                padding=(0, 2)
            )
        return ""


class WalletStatus(Static):
    """Display wallet balance and trading status"""
    
    balance: reactive[str] = reactive("Loading...")
    
    def __init__(self, poly_provider: PolyProvider, **kwargs):
        super().__init__(**kwargs)
        self.poly_provider = poly_provider
    
    def render(self) -> RenderableType:
        is_paper = get_paper_mode()
        table = Table(show_header=False, expand=True, box=None, padding=(0, 1))
        table.add_column("Label", style="dim", width=12)
        table.add_column("Value", style="bold white")
        
        balance_label = "Balance (Paper)" if is_paper else "USDC Balance"
        table.add_row(balance_label, self.balance)
        
        title = "Paper Wallet" if is_paper else "Wallet"
        border_style = "yellow" if is_paper else "green"
        
        return Panel(table, title=title, border_style=border_style, height=4)
    
    def on_mount(self) -> None:
        """Start balance refresh loop"""
        self._start_balance_refresh()
    
    @work
    async def _start_balance_refresh(self) -> None:
        """Periodically refresh balance"""
        while True:
            await self._update_balance()
            await asyncio.sleep(30)
    
    async def _update_balance(self) -> None:
        """Fetch and update balance"""
        try:
            balance_info = await self.poly_provider.get_balance()
            if "error" not in balance_info:
                balance_val = float(balance_info.get("balance", 0))
                self.balance = f"${balance_val:,.2f}"
            else:
                self.balance = "Not configured"
        except Exception as e:
            logger.error("Failed to fetch balance", error=str(e))
            self.balance = "Error"


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

            # Update news panel to filter by market entities (Phase 4: Market-News Linking)
            try:
                news_panel = self.app.query_one("#news_panel", NewsPanel)
                news_panel.filter_by_market(market)
            except Exception:
                pass  # News panel may not be mounted or available

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

                # Get token IDs for price history API (reuse ctids parsed earlier)
                token_ids = ctids if ctids else []

                if token_ids:
                    # Fetch ALL intervals in parallel for instant switching in UI
                    intervals = ["1h", "6h", "1d", "1w", "max"]
                    fidelity_map = {"1h": 1, "6h": 5, "1d": 15, "1w": 60, "max": 60}

                    # Create tasks for Yes token (all intervals)
                    yes_tasks = [
                        self.app.poly.get_prices_history(
                            token_id=token_ids[0],
                            interval=iv,
                            fidelity=fidelity_map[iv]
                        )
                        for iv in intervals
                    ]

                    # Create tasks for No token if available
                    no_tasks = []
                    if len(token_ids) > 1:
                        no_tasks = [
                            self.app.poly.get_prices_history(
                                token_id=token_ids[1],
                                interval=iv,
                                fidelity=fidelity_map[iv]
                            )
                            for iv in intervals
                        ]

                    # Fetch all in parallel
                    import asyncio
                    all_tasks = yes_tasks + no_tasks
                    results = await asyncio.gather(*all_tasks, return_exceptions=True)

                    yes_results = results[:len(intervals)]
                    no_results = results[len(intervals):] if no_tasks else []

                    # Build interval data structure
                    interval_data = {}
                    total_points = 0

                    for i, iv in enumerate(intervals):
                        yes_points = yes_results[i] if not isinstance(yes_results[i], Exception) else []
                        no_points = no_results[i] if no_results and not isinstance(no_results[i], Exception) else []

                        traces = []
                        if yes_points:
                            traces.append({
                                "x": [p.t for p in yes_points],
                                "y": [p.p for p in yes_points],
                                "name": "Yes",
                                "color": "#2ecc71"
                            })
                            total_points += len(yes_points)
                        if no_points:
                            traces.append({
                                "x": [p.t for p in no_points],
                                "y": [p.p for p in no_points],
                                "name": "No",
                                "color": "#e74c3c"
                            })

                        if traces:
                            interval_data[iv] = {"traces": traces}

                    if interval_data:
                        self.app.notify(
                            f"✓ Loaded {total_points} points across {len(interval_data)} intervals",
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

                        # Use new multi-interval plot method
                        ChartManager().plot_intervals(
                            title=market.question,
                            interval_data=interval_data,
                            default_interval="1d",
                            metadata=metadata
                        )
                    else:
                        self.app.notify("⚠ No chart data available", severity="warning")
                else:
                    self.app.notify("⚠ No token ID available for chart", severity="warning")

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


class TradeHistoryView(Container):
    """Trade history and order tracking"""
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("TRADE HISTORY", classes="p_title")
            yield DataTable(id="trades_table")
            yield Label("ORDER HISTORY", classes="p_title")
            yield DataTable(id="order_history_table")
            with Horizontal(id="h_controls"):
                yield Button("Refresh", id="h_refresh")
                yield Button("Export CSV", id="h_export")
    
    def on_mount(self) -> None:
        # Setup trades table
        self.query_one("#trades_table", DataTable).add_columns(
            "Time", "Market", "Side", "Price", "Size", "Total", "Prov"
        )
        # Setup order history table  
        self.query_one("#order_history_table", DataTable).add_columns(
            "Time", "ID", "Market", "Side", "Price", "Size", "Status", "Prov"
        )
        self.load_history()
    
    @work(exclusive=True)
    async def load_history(self) -> None:
        """Load trade and order history from providers"""
        try:
            # Fetch trades from both providers
            poly_trades = await self.app.poly.get_trades()
            kalshi_trades = await self.app.kalshi.get_trades()
            
            # Fetch order history (using get_orders for now)
            poly_orders = await self.app.poly.get_orders()
            kalshi_orders = await self.app.kalshi.get_orders()
            
            # Populate trades table
            trades_table = self.query_one("#trades_table", DataTable)
            trades_table.clear()
            
            all_trades = poly_trades + kalshi_trades
            # Sort by timestamp (newest first)
            all_trades.sort(key=lambda t: t.timestamp, reverse=True)
            
            for trade in all_trades[:100]:  # Show last 100 trades
                from datetime import datetime
                time_str = datetime.fromtimestamp(trade.timestamp).strftime("%m-%d %H:%M") if trade.timestamp else "N/A"
                total = trade.price * trade.size
                provider = "P" if hasattr(self.app.poly, 'client') else "K"
                
                trades_table.add_row(
                    time_str,
                    trade.market_id[:20],
                    f"[green]{trade.side.value}[/]" if trade.side == Side.BUY else f"[red]{trade.side.value}[/]",
                    f"${trade.price:.3f}",
                    f"{trade.size:.2f}",
                    f"${total:.2f}",
                    provider
                )
            
            # Populate order history table
            orders_table = self.query_one("#order_history_table", DataTable)
            orders_table.clear()
            
            all_orders = poly_orders + kalshi_orders
            # Sort by most recent
            for order in all_orders[:100]:
                from datetime import datetime
                time_str = datetime.fromtimestamp(order.timestamp).strftime("%m-%d %H:%M") if order.timestamp else "N/A"
                provider = "P" if order.market_id.startswith("0x") else "K"
                
                status_color = "green" if order.status == OrderStatus.FILLED else "yellow" if order.status == OrderStatus.OPEN else "dim"
                
                orders_table.add_row(
                    time_str,
                    order.id[:12],
                    order.market_id[:20],
                    f"[green]{order.side.value}[/]" if order.side == Side.BUY else f"[red]{order.side.value}[/]",
                    f"${order.price:.3f}",
                    f"{order.size:.2f}",
                    f"[{status_color}]{order.status.value}[/]",
                    provider
                )
                
        except Exception as e:
            logger.error("Failed to load trade history", error=str(e))
            self.app.notify(f"History load error: {str(e)}", severity="error")
    
    @on(Button.Pressed, "#h_refresh")
    def refresh_history(self) -> None:
        """Refresh history data"""
        self.load_history()
        self.app.notify("Refreshing history...", severity="information")
    
    @on(Button.Pressed, "#h_export")
    def export_csv(self) -> None:
        """Export trade history to CSV"""
        self.app.notify("CSV export coming soon!", severity="information")


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
        Binding("a", "show_analytics", "Analytics"),
        ("d", "show_dash", "Dashboard"),
        ("p", "show_portfolio", "Portfolio"),
        ("h", "show_history", "Trade History"),
        ("n", "show_news", "News Feed"),
        ("m", "cycle_agent_mode", "Agent Mode"),
        ("escape", "escape", "Back/Cancel"),
        ("enter", "enter", "Send Command"),
        Binding("ctrl+x", "emergency_stop", "EMERGENCY STOP", priority=True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redis_store = RedisStore(prefix="polycli:")
        self.sqlite_store = SQLiteStore(":memory:")
        
        # Initialize providers
        real_poly = PolyProvider()
        if get_paper_mode():
            from polycli.paper.provider import PaperTradingProvider
            self.poly = PaperTradingProvider(real_poly)
            # Ensure paper provider is initialized (sync wrapper or await later)
            # Since __init__ is sync, we can't await. 
            # PaperTradingProvider initializes lazily or via explicit init. 
            # We'll let it init lazily or in on_mount.
        else:
            self.poly = real_poly
            
        self.kalshi = KalshiProvider()
        
        # News clients (polyfloat-news integration) - initialized first for agent access
        self.news_ws_client = NewsWebSocketClient()
        self.news_api_client = NewsAPIClient()
        self.news_available = False  # Set to True when connected
        
        # News alert manager for real-time notifications (Phase 6)
        # Note: ws_client callback is added later, alert callback registered in on_mount
        self.news_alert_manager = NewsAlertManager(
            ws_client=None,  # Connect later to avoid timing issues
            api_client=self.news_api_client
        )
        self.news_alert_manager.add_config(DEFAULT_TERMINAL_CONFIG)

        # Determine initial provider for supervisor
        initial_prov = self.poly # Default
        
        # Initialize supervisor with news client for agent context injection
        self.supervisor = SupervisorAgent(
            redis_store=self.redis_store, 
            sqlite_store=self.sqlite_store,
            provider=initial_prov,
            news_api_client=self.news_api_client
        )
        self.ws_client = PolymarketWebSocket()
        self.kalshi_ws = KalshiWebSocket()
        self.auto_loop_task = None

        self._emergency_controller = EmergencyStopController(
            cancel_orders_fn=self._cancel_all_orders,
            close_websockets_fn=self._close_all_websockets
        )

    def action_cycle_agent_mode(self) -> None:
        modes = ["manual", "auto-approval", "full-auto"]
        idx = modes.index(self.agent_mode)
        self.agent_mode = modes[(idx + 1) % len(modes)]
        self.notify(f"Agent Mode: {self.agent_mode.upper()}")

    def action_show_news(self) -> None:
        """Show full-screen news feed"""
        news_feed = FullScreenNewsFeed(news_api_client=self.news_api_client)
        self.push_screen(news_feed)

    async def _on_news_alert(self, user_id: str, alert) -> None:
        """Handle news alerts - show notification in TUI"""
        try:
            # Format alert message
            formatted = self.news_alert_manager.format_alert(alert)
            
            # Show notification based on priority
            if alert.priority.value == "breaking":
                self.notify(f"[red]{formatted}[/red]", title="🔴 BREAKING NEWS", severity="error")
            elif alert.priority.value == "high":
                self.notify(f"[yellow]{formatted}[/yellow]", title="🟡 HIGH IMPACT", severity="warning")
            else:
                self.notify(formatted, title="📰 News Alert", severity="information")
            
            logger.debug("News alert displayed", priority=alert.priority.value)
        except Exception as e:
            logger.error("Failed to display news alert", error=str(e))

    def on_mount(self) -> None:
        self.ws_client.start()
        self.call_later(self.kalshi_ws.connect)

        # Start background agent loop
        self.auto_loop_task = asyncio.create_task(self._agent_background_loop())

        # Register news alert callback (done here to ensure method exists)
        self.news_alert_manager.add_callback(self._on_news_alert)
        # Connect WebSocket to alert manager
        self.news_ws_client.add_callback("news_item", self.news_alert_manager._on_news_item)

        # Connect to news service (graceful fallback if unavailable)
        asyncio.create_task(self._connect_news_service())

        mlist = self.query_one("#market_list", DataTable)
        mlist.add_columns("Market", "Px", "Src")
        mlist.cursor_type = "row"
        self.update_markets()

    async def _connect_news_service(self) -> None:
        """Connect to polyfloat-news WebSocket with graceful fallback"""
        try:
            # Register callback for incoming news
            self.news_ws_client.add_callback("news_item", self._on_news_item)

            # Connect with timeout
            await asyncio.wait_for(
                self.news_ws_client.connect(user_id="terminal_user"),
                timeout=5.0
            )
            self.news_available = True
            logger.info("News service connected")

            # Wire up NewsPanel with clients
            try:
                news_panel = self.query_one("#news_panel", NewsPanel)
                news_panel.set_clients(self.news_api_client, self.news_ws_client)
            except Exception:
                pass  # Panel may not be mounted yet

            # Load initial news via REST API
            await self._load_initial_news()

        except asyncio.TimeoutError:
            logger.warning("News service connection timeout - running without news")
            self.news_available = False
            self._mark_news_unavailable()
        except Exception as e:
            logger.warning("News service unavailable", error=str(e))
            self.news_available = False
            self._mark_news_unavailable()

    async def _load_initial_news(self) -> None:
        """Load initial news items via REST API"""
        try:
            news_items = await self.news_api_client.get_news(limit=10)
            ticker = self.query_one(NewsTicker)
            for item in reversed(news_items):  # Add oldest first so newest is on top
                ticker.add_news(item.model_dump())
            logger.info("Loaded initial news", count=len(news_items))
        except Exception as e:
            logger.warning("Failed to load initial news", error=str(e))

    async def _on_news_item(self, news_data: Dict[str, Any]) -> None:
        """Handle incoming news from WebSocket"""
        try:
            ticker = self.query_one(NewsTicker)
            ticker.add_news(news_data)

            # Show notification for high-impact news
            impact = news_data.get("impact_score", 0)
            if impact >= 80:
                content = news_data.get("title") or news_data.get("content", "")[:50]
                self.notify(f"🔴 BREAKING: {content}", severity="warning", timeout=10)
        except Exception as e:
            logger.error("Error handling news item", error=str(e))

    def _mark_news_unavailable(self) -> None:
        """Mark news as unavailable in UI"""
        try:
            ticker = self.query_one(NewsTicker)
            ticker.set_unavailable()
        except Exception:
            pass  # Ticker may not be mounted yet

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

    async def _get_balance(self, provider: str) -> Dict[str, Any]:
        """Get balance for provider."""
        if provider == "kalshi":
            return await self.kalshi.get_balance()
        return await self.poly.get_balance()

    async def _get_positions(self, provider: str) -> List[Dict[str, Any]]:
        """Get positions for provider."""
        prov = self.kalshi if provider == "kalshi" else self.poly
        positions = await prov.get_positions()
        # Convert Pydantic models to dicts
        return [p.model_dump() for p in positions]

    async def _get_price(self, market_id: str) -> Decimal:
        """Get current price for market."""
        # Simple implementation - in real app would cache/optimize
        return Decimal("0.50")

    def compose(self) -> ComposeResult:
        yield Header()
        
        if get_paper_mode():
            yield PaperModeIndicator(id="paper_mode_indicator")
        
        yield NewsTicker(id="news_ticker")
        
        # Initialize calculator with callbacks
        self.calculator = PerformanceCalculator(
            get_balance_fn=self._get_balance,
            get_positions_fn=self._get_positions,
            get_price_fn=self._get_price
        )

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

                yield Label("Wallet", classes="section_title")
                yield WalletStatus(poly_provider=self.poly, id="wallet_status")
                
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
                with ContentSwitcher(id="switcher", initial="dashboard"):
                    with Vertical(id="dashboard"):
                        yield Label("Market Focus", classes="section_title")
                        yield MarketDetail(id="market_focus", classes="market-detail")
                        # News Panel (30% of right column)
                        yield NewsPanel(id="news_panel", classes="news-panel")
                    yield PerformanceDashboardWidget(calculator=self.calculator, id="analytics")
                    yield PortfolioView(id="portfolio")

        yield Footer()



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

    def action_show_history(self) -> None:
        """Show trade history screen"""
        self.push_screen(TradeHistoryView())

    def action_show_dash(self) -> None:
        self.query_one("#switcher").current = "dashboard"

    async def action_show_analytics(self) -> None:
        self.query_one("#switcher").current = "analytics"
        try:
            await self.query_one("#analytics", PerformanceDashboardWidget).refresh_data()
        except Exception:
            pass

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
                side = order_data["side"]
                amount = order_data["amount"]
                
                # Check balance before placing order (for Polymarket only, for now)
                if m.provider == "polymarket" and side == Side.BUY:
                    balance_info = await self.poly.get_balance()
                    if "error" not in balance_info:
                        balance = float(balance_info.get("balance", 0))
                        if amount > balance:
                            self.notify(
                                f"Insufficient balance! Have: ${balance:.2f}, Need: ${amount:.2f}",
                                severity="error"
                            )
                            return
                    else:
                        self.notify("Warning: Could not verify balance", severity="warning")
                
                # Use market order for Polymarket
                if m.provider == "polymarket":
                    # Get token ID from market metadata
                    extra = m.metadata or {}
                    ctids = extra.get("clobTokenIds", [])
                    if isinstance(ctids, str):
                        import json
                        ctids = json.loads(ctids)
                    
                    if not ctids:
                        self.notify("No token ID found for this market", severity="error")
                        return
                    
                    token_id = ctids[0]  # Use YES token
                    res = await self.poly.place_market_order(
                        token_id=token_id,
                        side=side,
                        amount=amount
                    )
                    self.notify(f"Market Order Executed: {res.id[:8]}")
                else:
                    # Kalshi - use regular limit order
                    res = await prov.place_order(
                        market_id=m.id,
                        side=side,
                        size=amount,
                        price=0.50,  # TODO: Get from orderbook
                    )
                    self.notify(f"Order Sent: {res.id[:8]}")
                
                # Refresh wallet balance
                try:
                    wallet_status = self.query_one("#wallet_status", WalletStatus)
                    await wallet_status._update_balance()
                except Exception:
                    pass
                    
            except Exception as e:
                logger.error("Order placement failed", error=str(e))
                self.notify(f"Order Fail: {str(e)[:50]}", severity="error")

    async def action_emergency_stop(self) -> None:
        confirmed = await self.push_screen(EmergencyStopConfirmScreen(), wait_for_dismiss=True)

        if confirmed:
            event = await self._emergency_controller.trigger_stop(reason=StopReason.USER_INITIATED, description="User triggered emergency stop via TUI")

            self.notify(f"EMERGENCY STOP ACTIVATED\nOrders cancelled: {event.orders_cancelled}\nWebSockets closed: {event.websockets_closed}", severity="error")

    async def _cancel_all_orders(self) -> int:
        from polycli.emergency.order_canceller import OrderCanceller
        canceller = OrderCanceller(self.poly, self.kalshi)
        return await canceller.cancel_all_orders()

    async def _close_all_websockets(self) -> int:
        closed = 0
        if hasattr(self, '_poly_ws') and self._poly_ws is not None:
            await self._poly_ws.close()
            closed += 1
        if hasattr(self, '_kalshi_ws') and self._kalshi_ws is not None:
            await self._kalshi_ws.close()
            closed += 1
        return closed

    @on(DataTable.RowSelected, "#market_list")
    def select_market(self, event: DataTable.RowSelected) -> None:
        m = self.markets_cache.get(event.row_key)
        if m:
            self.query_one("#market_focus", MarketDetail).market = m


class EmergencyStopConfirmScreen(ModalScreen):
    BINDINGS = [
        ("y", "confirm", "Yes, STOP"),
        ("n", "cancel", "No, Cancel"),
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="emergency_stop_dialog"):
            yield Static("[bold red]EMERGENCY STOP[/]", id="title")
            yield Static(
                "This will:\n"
                "- Halt all agent activity\n"
                "- Cancel all pending orders\n"
                "- Close all WebSocket connections\n\n"
                "Are you sure?",
                id="message"
            )
            with Horizontal():
                yield Button("Yes, STOP [Y]", variant="error", id="confirm")
                yield Button("Cancel [N]", variant="primary", id="cancel")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


if __name__ == "__main__":
    app = DashboardApp()
    app.run()
