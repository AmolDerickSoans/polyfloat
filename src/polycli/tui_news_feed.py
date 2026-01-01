"""
Full-Screen News Feed - Bloomberg Terminal Style
Dedicated view for browsing and filtering news with full details.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Button, Input, Label, DataTable
from textual.screen import Screen
from textual.reactive import reactive
from textual import work
from typing import List, Dict, Any, Optional
import asyncio
import structlog
import time

logger = structlog.get_logger()


class NewsItemCard(Static):
    """Individual news item display with full details"""

    def __init__(self, news_item: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.news_item = news_item

    def compose(self) -> ComposeResult:
        item = self.news_item
        impact = item.get("impact_score", 0)

        # Determine impact styling
        if impact >= 80:
            impact_class = "news-item-breaking"
            impact_label = "[bold red]🔴 BREAKING[/bold red]"
        elif impact >= 60:
            impact_class = "news-item-high"
            impact_label = "[yellow]🟡 HIGH IMPACT[/yellow]"
        else:
            impact_class = "news-item-low"
            impact_label = "[dim]⚪ NORMAL[/dim]"

        self.add_class(impact_class)

        # Format time
        published = item.get("published_at", 0)
        age = self._format_age(published)

        # Source badge
        source = item.get("source", "rss")
        source_account = item.get("source_account", "Unknown")
        source_badge = (
            f"[blue]𝕏 {source_account}[/blue]"
            if source == "nitter"
            else f"[yellow]📰 RSS[/yellow]"
        )

        # Build content
        headline = item.get("title") or item.get("content", "")[:100]
        content = item.get("content", "")[:200]

        # Entities
        tickers = item.get("tickers", [])
        people = item.get("people", [])
        category = item.get("category", "other")

        yield Static(f"{impact_label}  {age}", classes="news-card-header")
        yield Static(f"[bold]{headline}[/bold]", classes="news-card-title")
        yield Static(f"[dim]{content}...[/dim]", classes="news-card-content")

        # Entity tags
        tags_line = f"{source_badge}"
        if tickers:
            tags_line += f"  [green]${' $'.join(tickers[:3])}[/green]"
        if people:
            tags_line += f"  [cyan]{', '.join(people[:3])}[/cyan]"
        tags_line += f"  [dim]#{category}[/dim]"

        yield Static(tags_line, classes="news-card-tags")

    def _format_age(self, timestamp: float) -> str:
        if not timestamp:
            return "?"
        age_seconds = time.time() - timestamp
        if age_seconds < 60:
            return f"{int(age_seconds)}s ago"
        elif age_seconds < 3600:
            return f"{int(age_seconds / 60)}m ago"
        elif age_seconds < 86400:
            return f"{int(age_seconds / 3600)}h ago"
        else:
            return f"{int(age_seconds / 86400)}d ago"


class FullScreenNewsFeed(Screen):
    """Full-screen news feed with filtering and pagination"""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("r", "refresh", "Refresh"),
        ("c", "clear_filters", "Clear Filters"),
        ("1", "filter_politics", "Politics"),
        ("2", "filter_crypto", "Crypto"),
        ("3", "filter_economics", "Economics"),
        ("4", "filter_sports", "Sports"),
        ("0", "filter_all", "All"),
    ]

    news_items: reactive[List[Dict[str, Any]]] = reactive([])
    selected_category: reactive[Optional[str]] = reactive(None)
    search_query: str = ""
    current_page: int = 0
    items_per_page: int = 20

    def __init__(self, news_api_client=None, **kwargs):
        super().__init__(**kwargs)
        self.news_api_client = news_api_client

    def compose(self) -> ComposeResult:
        yield Vertical(
            # Header
            Static(
                "[bold cyan]📰 NEWS FEED[/bold cyan]  [dim]Press ESC to close[/dim]",
                id="feed_header",
            ),
            # Filter bar
            Horizontal(
                Button("All", id="f_all", variant="primary", classes="filter-btn"),
                Button("Gov", id="f_politics", classes="filter-btn"),
                Button("Crypto", id="f_crypto", classes="filter-btn"),
                Button("Econ", id="f_economics", classes="filter-btn"),
                Button("Sports", id="f_sports", classes="filter-btn"),
                Static("  ", classes="spacer"),
                Input(
                    placeholder="Search news...",
                    id="news_search",
                    classes="search-input",
                ),
                Button("Refresh", id="refresh_feed", classes="refresh-btn"),
                id="filter_bar",
                classes="filter-bar",
            ),
            # Status bar
            Static(id="status_bar", classes="status-bar"),
            # News items container
            ScrollableContainer(
                Static(id="news_container"),
                id="news_scroll",
                classes="news-scroll",
            ),
            # Pagination
            Horizontal(
                Button("← Prev", id="prev_page", classes="page-btn"),
                Static(id="page_indicator", classes="page-indicator"),
                Button("Next →", id="next_page", classes="page-btn"),
                id="pagination",
                classes="pagination-bar",
            ),
            id="feed_layout",
            classes="feed-layout",
        )

    def on_mount(self) -> None:
        self._refresh_news()
        self._update_status()

    @work(exclusive=True)
    async def _refresh_news(self) -> None:
        """Refresh news from API"""
        try:
            container = self.query_one("#news_container", Static)
            container.update("[dim]Loading news...[/dim]")

            if not self.news_api_client:
                container.update("[red]News service not available[/red]")
                return

            params = {"limit": 50}
            if self.selected_category:
                params["category"] = self.selected_category

            items = await self.news_api_client.get_news(**params)
            self.news_items = [item.model_dump() for item in items]

            self._render_news()
            self._update_status()

        except Exception as e:
            logger.error("Failed to load news", error=str(e))
            container = self.query_one("#news_container", Static)
            container.update(f"[red]Error: {str(e)}[/red]")

    def _render_news(self) -> None:
        """Render news items to container"""
        container = self.query_one("#news_container", Static)

        if not self.news_items:
            container.update("[dim]No news available[/dim]")
            return

        # Apply search filter
        items = self.news_items
        if self.search_query:
            query = self.search_query.lower()
            items = [
                item
                for item in items
                if query in (item.get("title") or "").lower()
                or query in (item.get("content") or "").lower()
                or any(query in t.lower() for t in item.get("tickers", []))
                or any(query in p.lower() for p in item.get("people", []))
            ]

        # Pagination
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_items = items[start:end]

        # Build display
        lines = []
        for item in page_items:
            impact = item.get("impact_score", 0)

            # Impact indicator
            if impact >= 80:
                indicator = "[bold red]🔴 BREAKING[/bold red]"
            elif impact >= 60:
                indicator = "[yellow]🟡 HIGH[/yellow]"
            else:
                indicator = "[dim]⚪[/dim]"

            # Time
            published = item.get("published_at", 0)
            age = self._format_age(published)

            # Source
            source = item.get("source", "rss")
            source_badge = "[blue]𝕏[/blue]" if source == "nitter" else "[dim]📰[/dim]"

            # Headline
            headline = item.get("title") or item.get("content", "")
            headline = headline[:60] + "..." if len(headline) > 60 else headline

            # Entities
            tickers = item.get("tickers", [])
            people = item.get("people", [])
            entity_str = ""
            if tickers:
                entity_str += f" [green]${' $'.join(tickers[:2])}[/green]"
            if people:
                entity_str += f" [cyan]{people[0]}[/cyan]"

            lines.append(f"{indicator} {age:>6} {source_badge} {headline}{entity_str}")
            lines.append("")  # Blank line between items

        container.update("\n".join(lines) if lines else "[dim]No matching news[/dim]")

        # Update pagination
        total_pages = (len(items) + self.items_per_page - 1) // self.items_per_page
        page_indicator = self.query_one("#page_indicator", Static)
        page_indicator.update(f"Page {self.current_page + 1} of {total_pages}")

    def _format_age(self, timestamp: float) -> str:
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

    def _update_status(self) -> None:
        """Update status bar"""
        try:
            status = self.query_one("#status_bar", Static)
            total = len(self.news_items)
            high_impact = sum(
                1 for i in self.news_items if i.get("impact_score", 0) >= 80
            )

            cat_str = f"[cyan]{self.selected_category or 'All'}[/cyan]"
            status.update(
                f"{cat_str} | {total} items | {high_impact} breaking | {self.search_query or 'No search'}"
            )
        except Exception:
            pass

    def watch_selected_category(self, category: Optional[str]) -> None:
        """React to category change"""
        self.current_page = 0
        self._refresh_news()
        self._update_filter_buttons()

    def _update_filter_buttons(self) -> None:
        """Update filter button states"""
        mappings = {
            None: "f_all",
            "politics": "f_politics",
            "crypto": "f_crypto",
            "economics": "f_economics",
            "sports": "f_sports",
        }
        active_id = mappings.get(self.selected_category, "f_all")

        for cat, btn_id in mappings.items():
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                btn.variant = "primary" if btn_id == active_id else "default"
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        btn_id = event.button.id

        if btn_id == "f_all":
            self.selected_category = None
        elif btn_id == "f_politics":
            self.selected_category = "politics"
        elif btn_id == "f_crypto":
            self.selected_category = "crypto"
        elif btn_id == "f_economics":
            self.selected_category = "economics"
        elif btn_id == "f_sports":
            self.selected_category = "sports"
        elif btn_id == "refresh_feed":
            self._refresh_news()
        elif btn_id == "prev_page":
            if self.current_page > 0:
                self.current_page -= 1
                self._render_news()
        elif btn_id == "next_page":
            total_pages = (
                len(self.news_items) + self.items_per_page - 1
            ) // self.items_per_page
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self._render_news()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input"""
        if event.input.id == "news_search":
            self.search_query = event.value
            self.current_page = 0
            self._render_news()
            self._update_status()

    # Action handlers for key bindings
    def action_close(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self._refresh_news()

    def action_clear_filters(self) -> None:
        self.selected_category = None
        self.search_query = ""
        try:
            search_input = self.query_one("#news_search", Input)
            search_input.value = ""
        except Exception:
            pass

    def action_filter_politics(self) -> None:
        self.selected_category = "politics"

    def action_filter_crypto(self) -> None:
        self.selected_category = "crypto"

    def action_filter_economics(self) -> None:
        self.selected_category = "economics"

    def action_filter_sports(self) -> None:
        self.selected_category = "sports"

    def action_filter_all(self) -> None:
        self.selected_category = None
