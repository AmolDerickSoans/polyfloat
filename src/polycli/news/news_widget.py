from textual.widgets import Label, Button, Static
from textual.containers import Vertical, Horizontal
from textual import work
from textual.reactive import reactive
from typing import List, Dict, Any, Optional
import asyncio
import structlog
import time

logger = structlog.get_logger()


class NewsPanel(Vertical):
    """
    Bloomberg-style News Panel for the TUI right panel.
    Displays news with impact indicators, category filters, and auto-updates.
    """

    news_items: reactive[List[Dict[str, Any]]] = reactive([])
    current_filters: Dict[str, Any] = {}
    is_loading: bool = False
    selected_category: reactive[Optional[str]] = reactive(None)

    def __init__(self, news_api_client=None, news_ws_client=None, **kwargs):
        super().__init__(**kwargs)
        self.news_api_client = news_api_client
        self.news_ws_client = news_ws_client
        self._last_refresh = 0

    def compose(self):
        """Compose news panel"""
        yield Static("[bold cyan]📰 NEWS[/bold cyan]", id="news_header")

        # Category filter buttons
        with Horizontal(id="news_filters", classes="news-filters"):
            yield Button("All", id="cat_all", variant="primary", classes="cat-btn active")
            yield Button("🏛️", id="cat_politics", classes="cat-btn")
            yield Button("₿", id="cat_crypto", classes="cat-btn")
            yield Button("📈", id="cat_economics", classes="cat-btn")
            yield Button("🏀", id="cat_sports", classes="cat-btn")

        # News items display
        yield Static(id="news_items_display", classes="news-display")

        # Footer with filter info and stats
        with Horizontal(id="news_footer", classes="news-footer"):
            yield Static(id="filter_indicator", classes="filter-info")
            yield Button("↻", id="refresh_news", classes="refresh-btn")

    def on_mount(self):
        """Initialize widget on mount"""
        self._update_display()
        # Auto-refresh every 60 seconds
        self.set_interval(60, self._auto_refresh)

    def set_clients(self, api_client, ws_client=None):
        """Set API and WebSocket clients"""
        self.news_api_client = api_client
        self.news_ws_client = ws_client
        if ws_client:
            ws_client.add_callback("news_item", self._on_ws_news)

    async def _on_ws_news(self, news_data: Dict[str, Any]):
        """Handle incoming WebSocket news"""
        # Check if matches current filter
        if self._matches_filter(news_data):
            # Insert at beginning
            current = list(self.news_items)
            current.insert(0, news_data)
            self.news_items = current[:10]  # Keep max 10

    def _matches_filter(self, news_data: Dict[str, Any]) -> bool:
        """Check if news item matches current filter"""
        if not self.selected_category:
            return True
        return news_data.get("category") == self.selected_category

    def watch_news_items(self, items: List[Dict[str, Any]]):
        """React to news items change"""
        self._update_display()

    def watch_selected_category(self, category: Optional[str]):
        """React to category filter change"""
        self._refresh_news()  # @work decorator handles background execution

    @work(exclusive=True)
    async def _refresh_news(self):
        """Refresh news with current filters"""
        if self.is_loading:
            return

        self.is_loading = True
        display = self.query_one("#news_items_display", Static)
        display.update("[dim]Loading...[/dim]")

        try:
            if not self.news_api_client:
                display.update("[dim]News service unavailable[/dim]")
                return

            params = {"limit": 10}
            if self.selected_category:
                params["category"] = self.selected_category
            if self.current_filters.get("ticker"):
                params["ticker"] = self.current_filters["ticker"]
            if self.current_filters.get("person"):
                params["person"] = self.current_filters["person"]

            items = await self.news_api_client.get_news(**params)
            self.news_items = [item.model_dump() for item in items]
            self._last_refresh = time.time()
            logger.debug("News refreshed", count=len(self.news_items))

        except Exception as e:
            logger.error("News refresh failed", error=str(e))
            display.update(f"[red]Error loading news[/red]")

        finally:
            self.is_loading = False

    def _auto_refresh(self):
        """Auto-refresh if not recently refreshed"""
        if time.time() - self._last_refresh > 30:
            self._refresh_news()  # @work decorator handles background execution

    def _update_display(self):
        """Update news display"""
        try:
            display = self.query_one("#news_items_display", Static)
        except Exception:
            return  # Widget not mounted yet

        if not self.news_items:
            display.update("[dim]No news available[/dim]")
            return

        lines = []
        for item in self.news_items[:7]:  # Show max 7 items
            impact = item.get("impact_score", 0)

            # Time ago
            published = item.get("published_at", 0)
            age = self._format_age(published)

            # Impact indicator
            if impact >= 80:
                indicator = "[bold red]🔴[/bold red]"
            elif impact >= 60:
                indicator = "[yellow]🟡[/yellow]"
            else:
                indicator = "[dim]⚪[/dim]"

            # Source badge
            source = item.get("source", "rss")
            source_badge = "[blue]𝕏[/blue]" if source == "nitter" else "[dim]📰[/dim]"

            # Headline
            headline = item.get("title") or item.get("content", "")
            headline = headline[:40] + "..." if len(headline) > 40 else headline

            lines.append(f"{indicator} {age:>4} {source_badge} {headline}")

        display.update("\n".join(lines))
        self._update_filter_indicator()

    def _format_age(self, timestamp: float) -> str:
        """Format timestamp as relative age"""
        if not timestamp:
            return "?"
        age_seconds = time.time() - timestamp
        if age_seconds < 60:
            return f"{int(age_seconds)}s"
        elif age_seconds < 3600:
            return f"{int(age_seconds / 60)}m"
        elif age_seconds < 86400:
            return f"{int(age_seconds / 3600)}h"
        else:
            return f"{int(age_seconds / 86400)}d"

    def _update_filter_indicator(self):
        """Update filter indicator"""
        try:
            indicator = self.query_one("#filter_indicator", Static)
            parts = []
            if self.selected_category:
                parts.append(f"[cyan]{self.selected_category}[/cyan]")
            if self.current_filters.get("ticker"):
                parts.append(f"[green]${self.current_filters['ticker']}[/green]")
            if self.current_filters.get("person"):
                parts.append(f"[yellow]{self.current_filters['person']}[/yellow]")

            if parts:
                indicator.update(" ".join(parts))
            else:
                indicator.update("[dim]All news[/dim]")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "refresh_news":
            self._refresh_news()  # @work decorator handles background execution
        elif button_id == "cat_all":
            self.selected_category = None
            self._update_button_states(button_id)
        elif button_id == "cat_politics":
            self.selected_category = "politics"
            self._update_button_states(button_id)
        elif button_id == "cat_crypto":
            self.selected_category = "crypto"
            self._update_button_states(button_id)
        elif button_id == "cat_economics":
            self.selected_category = "economics"
            self._update_button_states(button_id)
        elif button_id == "cat_sports":
            self.selected_category = "sports"
            self._update_button_states(button_id)

    def _update_button_states(self, active_id: str):
        """Update category button visual states"""
        for btn_id in ["cat_all", "cat_politics", "cat_crypto", "cat_economics", "cat_sports"]:
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                if btn_id == active_id:
                    btn.variant = "primary"
                else:
                    btn.variant = "default"
            except Exception:
                pass

    def filter_by_market(self, market):
        """Auto-filter news based on selected market"""
        if not market:
            return

        question = getattr(market, "question", "")
        filters = {}

        # Extract entities from market question
        crypto_tickers = ["BTC", "ETH", "SOL", "ADA", "DOGE", "MATIC", "AVAX", "XRP", "BNB"]
        for ticker in crypto_tickers:
            if ticker.upper() in question.upper():
                filters["ticker"] = ticker
                break

        people_names = [
            "Trump", "Biden", "Harris", "Obama", "Powell", "Yellen",
            "Musk", "Vitalik", "Buterin", "Zuckerberg", "Altman"
        ]
        for person in people_names:
            if person.lower() in question.lower():
                filters["person"] = person
                break

        if filters:
            self.current_filters = filters
            self._refresh_news()  # @work decorator handles background execution

    def clear_market_filter(self):
        """Clear market-specific filter"""
        self.current_filters = {}
        self._refresh_news()  # @work decorator handles background execution

    def add_news(self, news_data: Dict[str, Any]):
        """Add a single news item (for WebSocket updates)"""
        if self._matches_filter(news_data):
            current = list(self.news_items)
            current.insert(0, news_data)
            self.news_items = current[:10]


# Keep old class for backwards compatibility
class NewsWidget(NewsPanel):
    """Alias for backwards compatibility"""
    pass
