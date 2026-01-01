from textual.app import ComposeResult
from textual.widgets import DataTable, Button, Label, Static, Header, Footer
from textual.containers import Container, Vertical, Horizontal
from textual import work, on
from textual.reactive import reactive
import asyncio

from polycli.arbitrage.discovery import DiscoveryClient
from polycli.arbitrage.detector import ArbDetector
from polycli.arbitrage.models import ArbOpportunity

class ArbitrageScanner(Container):
    """
    Arbitrage Scanner Widget
    """
    detected_arbs: reactive[list[ArbOpportunity]] = reactive([])
    
    def compose(self) -> ComposeResult:
        with Header():
            yield Label("ARBITRAGE SCANNER", id="arb_header")
        
        with Horizontal(id="arb_controls"):
            yield Button("Scan NBA", id="scan_nba", variant="primary")
            yield Button("Scan EPL", id="scan_epl", variant="primary")
            yield Button("Scan All", id="scan_all", variant="warning")
            yield Label("", id="status_label")
            
        yield DataTable(id="arb_table")
        
    def on_mount(self) -> None:
        table = self.query_one("#arb_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Event", "Strategy", "Profit", "Cost", "Poly Px", "Kalshi Px")
        
    @on(Button.Pressed)
    def handle_scan(self, event: Button.Pressed) -> None:
        leagues = []
        if event.button.id == "scan_nba":
            leagues = ["nba"]
        elif event.button.id == "scan_epl":
            leagues = ["epl"]
            
        self.run_scan(leagues)

    @work(exclusive=True)
    async def run_scan(self, leagues: list[str]) -> None:
        status = self.query_one("#status_label", Label)
        table = self.query_one("#arb_table", DataTable)
        
        status.update("Discovering markets...")
        client = DiscoveryClient()
        detector = ArbDetector()
        
        try:
            pairs = await client.discover_all(leagues)
            status.update(f"Checking {len(pairs)} pairs for arbs...")
            
            # Check for arbs
            # Limit concurrency
            sem = asyncio.Semaphore(10)
            opportunities = []
            
            async def check(p):
                async with sem:
                    return await detector.check_pair(p)

            tasks = [check(p) for p in pairs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            table.clear()
            count = 0
            for res in results:
                if isinstance(res, ArbOpportunity) and res.is_profitable():
                    opportunities.append(res)
                    strategy = res.best_strategy()
                    profit = res.max_profit() * 100 # cents
                    
                    # Determine prices based on strategy
                    # If PolyYes/KalshiNo:
                    if res.profit_poly_yes_kalshi_no > res.profit_kalshi_yes_poly_no:
                        poly_px = res.poly_yes_price
                        kalshi_px = res.kalshi_no_price
                    else:
                        poly_px = res.poly_no_price
                        kalshi_px = res.kalshi_yes_price

                    table.add_row(
                        res.pair_id,
                        strategy,
                        f"[green]${profit:.2f}[/]",
                        f"${(1.0 - res.max_profit()):.2f}",
                        f"{poly_px:.2f}",
                        f"{kalshi_px:.2f}",
                        key=res.pair_id
                    )
                    count += 1
            
            status.update(f"Found {count} opportunities")
            if count == 0:
                self.app.notify("No arbitrage opportunities found", severity="warning")
            else:
                self.app.notify(f"Found {count} Arbs!", severity="information")
                
        except Exception as e:
            status.update(f"Error: {e}")
            self.app.notify(f"Scan failed: {e}", severity="error")
