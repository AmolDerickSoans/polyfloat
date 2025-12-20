from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual import work
import asyncio
import random

class MarketTicker(Static):
    """Widget to display market details"""
    price = reactive(0.65)
    
    def compose(self) -> ComposeResult:
        yield Label("Market: TRUMP24", classes="title")
        yield Label(f"Price: ${self.price:.2f}", id="price_label")

    def watch_price(self, old_price: float, new_price: float) -> None:
        try:
            self.query_one("#price_label", Label).update(f"Price: ${new_price:.2f}")
        except Exception:
            pass

class ArbPanel(Static):
    """Panel for displaying arbitrage opportunities"""
    def compose(self) -> ComposeResult:
        yield Label("Live Arbitrage Scanner", classes="title")
        yield DataTable(id="arb_table")

    def on_mount(self) -> None:
        table = self.query_one("#arb_table", DataTable)
        table.add_columns("Market", "Edge", "Direction")

class DashboardApp(App):
    """PolyCLI Terminal Dashboard"""
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        padding: 1;
    }
    .title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    MarketTicker, ArbPanel {
        height: 100%;
        border: solid green;
        padding: 1;
    }
    #market_table, #arb_table {
        height: 100%;
        border: solid blue;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Manual Refresh")
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield MarketTicker()
        yield ArbPanel()
        yield DataTable(id="market_table")
        yield Footer()

    def on_mount(self) -> None:
        m_table = self.query_one("#market_table", DataTable)
        m_table.add_columns("Provider", "Price", "Volume")
        m_table.add_rows([
            ("Polymarket", "0.65", "$1.2M"),
            ("Kalshi", "0.68", "$450K"),
        ])
        self.update_data()

    async def action_refresh(self) -> None:
        self.update_data()

    @work(exclusive=True)
    async def update_data(self):
        """Fetch real data for the TUI"""
        from polycli.providers.polymarket import PolyProvider
        from polycli.providers.kalshi import KalshiProvider
        from polycli.utils.matcher import match_markets
        from polycli.utils.arbitrage import find_opportunities
        
        poly = PolyProvider()
        kalshi = KalshiProvider()
        
        while True:
            try:
                # 1. Update Market Ticker with real data
                p_markets = await poly.get_markets(limit=20)
                k_markets = await kalshi.get_markets(limit=20)
                
                if p_markets:
                    self.query_one(MarketTicker).price = p_markets[0].price
                
                # 2. Update Arb Table
                arb_table = self.query_one("#arb_table", DataTable)
                if p_markets and k_markets:
                    matches = match_markets(p_markets, k_markets)
                    opps = find_opportunities(matches, min_edge=0.01)
                    arb_table.clear()
                    if not opps:
                         # No arbs found, but matching worked
                         pass
                    for o in opps:
                        arb_table.add_row(o.market_name[:20], f"{o.edge:.2%}", o.direction)
                elif p_markets and not k_markets:
                    arb_table.clear()
                    arb_table.add_row("Kalshi Auth Needed", "N/A", "Check .env")
                
                # 3. Update Market Table
                m_table = self.query_one("#market_table", DataTable)
                m_table.clear()
                for m in p_markets[:5]:
                    m_table.add_row("Poly", f"${m.price:.2f}", m.title[:20])
                for m in k_markets[:5]:
                    m_table.add_row("Kalshi", f"${m.price:.2f}", m.title[:20])
                    
            except Exception as e:
                # Log error to market table for visibility in dev
                try:
                    self.query_one("#market_table", DataTable).add_row("Error", str(e)[:10], "Check logs")
                except:
                    pass
                
            await asyncio.sleep(30)

if __name__ == "__main__":
    app = DashboardApp()
    app.run()