import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="PolyCLI: Agentic Terminal for Prediction Markets")
markets_app = typer.Typer(help="Market data commands")
app.add_typer(markets_app, name="markets")

console = Console()

@markets_app.command("list")
def list_markets(
    provider: str = typer.Option("polymarket", "--provider", "-p", help="Provider name"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of markets to show")
):
    """List available markets"""
    console.print(f"Fetching [bold cyan]{limit}[/bold cyan] markets from [bold green]{provider}[/bold green]...")
    
    table = Table(title=f"Top {limit} Markets on {provider}")
    table.add_column("Token ID", style="dim")
    table.add_column("Title")
    table.add_column("Price", justify="right")
    table.add_column("Liquidity", justify="right")

    # Placeholder data for demonstration
    table.add_row("TRUMP24", "Will Trump win 2024?", "$0.65", "$1.2M")
    table.add_row("BTC100K", "Will BTC reach $100K by end of year?", "$0.45", "$800K")
    
    console.print(table)

@markets_app.command("search")
def search_markets(
    query: str = typer.Argument(..., help="Search query"),
    provider: str = typer.Option("polymarket", "--provider", "-p", help="Provider name")
):
    """Search for markets"""
    console.print(f"Searching for '[bold yellow]{query}[/bold yellow]' on [bold green]{provider}[/bold green]...")

@app.command()
def version():
    """Show version information"""
    console.print("PolyCLI v0.1.0-foundation")

@app.command()
def dashboard():
    """Launch the TUI Dashboard"""
    from polycli.tui import DashboardApp
    app = DashboardApp()
    app.run()

if __name__ == "__main__":
    app()
