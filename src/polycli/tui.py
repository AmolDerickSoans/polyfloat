from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label, Button
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual import work
from polycli.providers.polymarket_ws import PolymarketWebSocket
import asyncio

class MarketTicker(Static):
    """Widget to display market details"""
    price = reactive(0.0)
    
    def compose(self) -> ComposeResult:
        yield Label("Market: TRUMP24")
        yield Label(f"Price: ${self.price:.2f}", id="price")

class OrderbookWidget(Static):
    """Widget to display orderbook"""
    def compose(self) -> ComposeResult:
        yield Label("Orderbook")
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Price", "Size", "Total")
        # Placeholder data
        table.add_rows([
            ("0.65", "100", "65.00"),
            ("0.64", "250", "160.00"),
        ])

class DashboardApp(App):
    """PolyCLI Terminal Dashboard"""
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        padding: 1;
    }
    MarketTicker {
        height: 10;
        border: solid green;
    }
    OrderbookWidget {
        height: 10;
        border: solid blue;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield MarketTicker()
        yield OrderbookWidget()
        yield Footer()

    def on_mount(self) -> None:
        self.ws = PolymarketWebSocket()
        self.start_ws()

    @work(exclusive=True)
    async def start_ws(self):
        # In a real app, we'd start the WS loop here
        # await self.ws.start()
        # Simulating updates for now
        while True:
            await asyncio.sleep(1)
            # self.query_one(MarketTicker).price += 0.01
            pass

if __name__ == "__main__":
    app = DashboardApp()
    app.run()
