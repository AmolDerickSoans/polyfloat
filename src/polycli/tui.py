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
    edge = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Label("Live Arbitrage Scanner", classes="title")
        yield Label(f"Current Edge: {self.edge:.2%}", id="edge_label")

    def watch_edge(self, old_edge: float, new_edge: float) -> None:
        try:
            self.query_one("#edge_label", Label).update(f"Current Edge: {new_edge:.2%}")
        except Exception:
            pass

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
        font-weight: bold;
        color: cyan;
        margin-bottom: 1;
    }
    MarketTicker, ArbPanel {
        height: 100%;
        border: solid green;
        padding: 1;
    }
    DataTable {
        height: 100%;
        border: solid blue;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield MarketTicker()
        yield ArbPanel()
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Provider", "Price", "Volume")
        table.add_rows([
            ("Polymarket", "0.65", "$1.2M"),
            ("Kalshi", "0.68", "$450K"),
        ])
        self.simulate_updates()

    @work(exclusive=True)
    async def simulate_updates(self):
        """Simulate live data updates for the TUI"""
        while True:
            await asyncio.sleep(2)
            new_price = 0.60 + (random.random() * 0.1)
            self.query_one(MarketTicker).price = new_price
            self.query_one(ArbPanel).edge = abs(new_price - 0.68)

if __name__ == "__main__":
    app = DashboardApp()
    app.run()