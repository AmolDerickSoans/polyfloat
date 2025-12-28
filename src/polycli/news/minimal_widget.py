from textual.widgets import Label, Button, Static
from textual.containers import Vertical, Horizontal
from textual import work, on
from typing import List, Dict, Any
import asyncio

class NewsWidget(Vertical):
    """Minimal News Widget"""
    
    news_items: List[Any] = []
    current_filters: Dict[str, Any] = {}
    is_loading: bool = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.news_api_client = None
    
    def compose(self):
        """Compose news widget"""
        yield Static(
            "[bold cyan]NEWS[/bold cyan]",
            id="news_header"
        )
        
        with Horizontal():
            yield Button("Refresh", id="refresh_news")
        
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
        display.update("[dim]Refreshing...[/dim]")
        
        try:
            if not self.news_api_client:
                display.update("[dim]API not configured[/dim]")
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
                self.update_filter_indicator()
            else:
                display.update(f"[red]Error: {result.get('error', 'Unknown')}[/red]")
        
        except Exception as e:
            display.update(f"[red]Error: {str(e)}[/red]")
        
        finally:
            self.is_loading = False
    
    def on_market_changed(self, market):
        """Auto-filter news when market is selected"""
        question = getattr(market, "question", "")
        
        tickers = []
        people = []
        keywords = []
        
        crypto_tickers = ["BTC", "ETH", "SOL", "ADA"]
        for ticker in crypto_tickers:
            if ticker.upper() in question.upper():
                tickers.append(ticker)
        
        people_names = ["Trump", "Biden", "Harris", "Powell"]
        for person in people_names:
            if person.lower() in question.lower():
                people.append(person)
        
        kw_list = ["election", "fed", "rate", "crypto", "bitcoin", "ethereum"]
        for kw in kw_list:
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
            filter_indicator.update(f"[cyan]Filtered for: {question[:30]}[/cyan]")
    
    def clear_filters(self):
        """Clear all filters"""
        self.current_filters = {}
        asyncio.create_task(self.refresh_news())
    
    def update_news_display(self):
        """Update news text display"""
        display = self.query_one("#news_items_display", Static)
        
        if not self.news_items:
            display.update("[dim]No news - Press Refresh[/dim]")
            self.update_stats()
            return
        
        lines = []
        
        for i, item in enumerate(self.news_items[:5]):
            impact = item.get("impact_score", 0)
            
            if impact >= 80:
                impact_label = "[red]HIGH[/red]"
            elif impact >= 60:
                impact_label = "[yellow]MED[/yellow]"
            else:
                impact_label = "[green]LOW[/green]"
            
            headline = item.get("title", item.get("content", ""))[:45]
            age = self._format_age(item.get("published_at", 0))
            
            source_icon = "[blue]🐦[/blue]" if item.get("source") == "nitter" else "[green]📰[/green]"
            
            lines.append(
                f"{impact_label} [{impact:.0f}]  {source_icon}  {headline}\n"
                f"     [dim]{age}[/dim]"
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
        
        high_impact = sum(1 for item in self.news_items if item.get("impact_score", 0) >= 80)
        avg_impact = sum(item.get("impact_score", 0) for item in self.news_items) / total
        
        stats_display.update(f"[dim]Stats: {total} items | High: {high_impact} | Avg: {avg_impact:.1f}[/dim]")
    
    def update_filter_indicator(self):
        """Update filter indicator"""
        filter_indicator = self.query_one("#filter_indicator", Static)
        filters = self.current_filters
        
        if not filters:
            filter_indicator.update("[dim]All news[/dim]")
            return
        
        parts = []
        if filters.get("category"):
            parts.append(f"cat:{filters['category']}")
        if filters.get("ticker"):
            parts.append(f"ticker:{filters['ticker']}")
        if filters.get("person"):
            parts.append(f"person:{filters['person']}")
        if filters.get("keywords"):
            parts.append(f"kw:{filters['keywords']}")
        
        if parts:
            filter_indicator.update(f"[cyan]Filters: {' | '.join(parts)}[/cyan][/dim]")
    
    def _format_age(self, timestamp: float) -> str:
        """Format timestamp as relative age"""
        import time
        delta = time.time() - timestamp
        
        if delta < 3600:
            return f"{int(delta/60)}m ago"
        elif delta < 86400:
            hours = int(delta/3600)
            return f"{hours}h ago"
        elif delta < 172800:
            days = int(delta/86400)
            return f"{days}d ago"
        else:
            return "Old"
    
    def on_button_pressed(self, event: Button.Pressed):
        """Handle button press"""
        if event.button.id == "refresh_news":
            asyncio.create_task(self.refresh_news())
