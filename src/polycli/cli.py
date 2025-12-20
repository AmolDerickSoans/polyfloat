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
def arb(
    min_edge: float = typer.Argument(0.03, help="Minimum price discrepancy to report")
):
    """Scan for arbitrage opportunities between Polymarket and Kalshi"""
    console.print(f"Scanning for arbitrage with min edge [bold cyan]{min_edge:.2%}[/bold cyan]...")
    
    # Mock detection
    from polycli.utils.arbitrage import calculate_arbitrage
    opp = calculate_arbitrage(0.65, 0.70, threshold=min_edge)
    
    if opp:
        console.print(f"[bold green]Opportunity Found![/bold green]")
        console.print(f"Market: {opp.market_name}")
        console.print(f"Poly: ${opp.poly_price} | Kalshi: ${opp.kalshi_price}")
        console.print(f"Edge: [bold yellow]{opp.edge:.2%}[/bold yellow]")
        console.print(f"Action: [bold cyan]{opp.recommendation}[/bold cyan]")
    else:
        console.print("No opportunities found above threshold.")

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

bot_app = typer.Typer(help="Agent and bot management")
app.add_typer(bot_app, name="bot")

@bot_app.command("deploy")
def deploy_bot(
    strategy: str = typer.Argument("simple", help="Strategy to deploy"),
    market: str = typer.Option("TRUMP24", "--market", "-m")
):
    """Deploy an autonomous trading bot"""
    console.print(f"Deploying bot with strategy [bold cyan]{strategy}[/bold cyan] on market [bold yellow]{market}[/bold yellow]...")
    
    import asyncio
    from polycli.agents.graph import create_trading_graph
    
    graph = create_trading_graph()
    initial_state = {
        "messages": [],
        "market_data": {"token_id": market, "price": 0.55},
        "positions": [],
        "strategy": strategy,
        "risk_score": 0.0,
        "last_action": "INIT",
        "next_step": "trader"
    }
    
    async def run_bot():
        result = await graph.ainvoke(initial_state)
        console.print(f"Bot Action: [bold green]{result['last_action']}[/bold green]")
        for msg in result["messages"]:
            console.print(f"  > {msg}")

    asyncio.run(run_bot())

@app.command()
def analytics():
    """[PRO] Run advanced market analytics (Correlation, VaR)"""
    import os
    is_pro = os.getenv("POLYCLI_PRO_KEY") is not None
    
    if not is_pro:
        console.print("[bold red]Access Denied[/bold red]: This feature requires a Pro Tier license.")
        console.print("Set POLYCLI_PRO_KEY environment variable to unlock.")
        raise typer.Exit(code=1)
        
    console.print("[bold green]Access Granted[/bold green]: Running Pro Analytics...")
    console.print("Calculating Correlation Matrix... [Done]")
    console.print("Value at Risk (VaR): $450.20")

if __name__ == "__main__":
    app()
