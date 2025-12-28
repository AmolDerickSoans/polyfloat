from textual.widgets import Label, Button, Static
from textual.containers import Vertical, Horizontal
from textual import work
from typing import List, Dict, Any
import asyncio

logger = None


class NewsWidget(Vertical):
    """
    Simple News Widget for right panel
    """

    news_items: List[Any] = []
    current_filters: Dict[str, Any] = {}
    is_loading: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.news_api_client = None

    def compose(self):
        """Compose news widget"""
        yield Static("[bold cyan]📰 NEWS[/bold cyan]", id="news_header")

        with Horizontal(id="news_controls"):
            yield Button("Refresh", id="refresh_news", variant="primary")

        yield Static(id="news_items_display")

        with Horizontal(id="news_footer", classes="news-footer"):
            yield Static(id="filter_indicator")
            yield Static(id="stats_display")

    def on_mount(self):
        """Initialize widget on mount"""
        self.update_news_display()

    def set_api_client(self, api_client):
        """Set News API client"""
        self.news_api_client = api_client

    @work(exclusive=True)
    async def refresh_news(self):
        """Refresh news with current filters"""
        if self.is_loading:
            return

        self.is_loading = True

        display = self.query_one("#news_items_display", Static)
        display.update("[dim]Refreshing news...[/dim]")

        try:
            if not self.news_api_client:
                display.update("[dim]News API not configured[/dim]")
                self.is_loading = False
                return

            filters = self.current_filters

            params = {"limit": 10}
            if filters.get("category"):
                params["category"] = filters["category"]
            if filters.get("min_impact"):
                params["min_impact"] = filters["min_impact"]
            if filters.get("ticker"):
                params["ticker"] = filters["ticker"]

            result = await self.news_api_client.get_news(**params)

            if result.get("success"):
                self.news_items = result["items"]
                self.update_news_display()
                print(f"[cyan]Refreshed {len(self.news_items)} news items[/cyan]")
            else:
                display.update(f"[red]Error: {result.get('error', 'Unknown')}[/red]")

        except Exception as e:
            display.update(f"[red]Error: {str(e)}[/red]")

        finally:
            self.is_loading = False

    def apply_filters(self, filters: Dict[str, Any]):
        """Apply filters to news"""
        self.current_filters = filters
        asyncio.create_task(self.refresh_news())

    def on_market_changed(self, market):
        """Auto-filter news when market is selected"""
        try:
            question = getattr(market, "question", "")

            tickers = []
            people = []
            keywords = []

            crypto_tickers = ["BTC", "ETH", "SOL", "ADA", "DOGE", "MATIC", "AVAX"]
            for ticker in crypto_tickers:
                if ticker.upper() in question.upper():
                    tickers.append(ticker)

            people_names = [
                "Trump",
                "Biden",
                "Harris",
                "Obama",
                "Bush",
                "Clinton",
                "Powell",
                "Yellen",
                "Bernanke",
                "Musk",
                "Vitalik",
            ]
            for person in people_names:
                if person.lower() in question.lower():
                    people.append(person)

            keywords_lower = [
                "election",
                "fed",
                "rate",
                "inflation",
                "crypto",
                "bitcoin",
                "ethereum",
                "price",
                "market",
                "trade",
                "president",
                "congress",
                "senate",
                "politics",
            ]
            for kw in keywords_lower:
                if kw in question.lower():
                    keywords.append(kw)

            if tickers or people or keywords:
                filters = {}
                if tickers:
                    filters["ticker"] = tickers[0]
                if people:
                    filters["person"] = people[0]
                if keywords:
                    filters["keywords"] = ",".join(keywords[:3])

                self.apply_filters(filters)
                filter_indicator = self.query_one("#filter_indicator", Static)
                filter_indicator.update(
                    f"[cyan]🔍 Filtered for: {question[:30]}[/cyan]"
                )

        except Exception as e:
            print(f"[red]Failed to auto-filter news: {str(e)}[/red]")

    def clear_filters(self):
        """Clear all filters"""
        self.current_filters = {}
        asyncio.create_task(self.refresh_news())
        filter_indicator = self.query_one("#filter_indicator", Static)
        filter_indicator.update("[dim]Filters: All news[/dim]")

    def update_news_display(self):
        """Update news text display"""
        display = self.query_one("#news_items_display", Static)

        if not self.news_items:
            display.update("[dim]No news - Press Refresh[/dim]")
            return

        lines = []

        for item in self.news_items[:5]:
            impact = item.get("impact_score", 0)

            if impact >= 80:
                impact_label = "[red]HIGH[/red]"
            elif impact >= 60:
                impact_label = "[yellow]MED[/yellow]"
            else:
                impact_label = "[green]LOW[/green]"

            headline = item.get("title", item.get("content", ""))[:45]
            source_badge = (
                "[blue]𝕐[/blue]"
                if item.get("source") == "nitter"
                else "[yellow]📰[/yellow]"
            )

            lines.append(
                f"{impact_label} [{impact:.0f}]  " f"{source_badge} {headline}\n"
            )

        display.update("\n".join(lines))
        self.update_stats()

    def update_stats(self):
        """Update statistics display"""
        stats_display = self.query_one("#stats_display", Static)

        total = len(self.news_items)

        if total == 0:
            stats_display.update("[dim]Stats: 0 items[/dim]")
            return

        high_impact = sum(
            1 for item in self.news_items if item.get("impact_score", 0) >= 80
        )
        avg_impact = (
            sum(item.get("impact_score", 0) for item in self.news_items) / total
        )

        stats_display.update(
            f"[dim]Stats: {total} items | High: {high_impact} | Avg: {avg_impact:.1f}[/dim]"
        )

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button press"""
        if event.button.id == "refresh_news":
            asyncio.create_task(self.refresh_news())
