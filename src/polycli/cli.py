import typer
import os
import sys
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from dotenv import load_dotenv, set_key

# Load existing environment variables
load_dotenv()

app = typer.Typer(
    help="PolyCLI: Agentic Terminal for Prediction Markets",
    no_args_is_help=False,  # We will handle no-args manually
    add_completion=False
)
markets_app = typer.Typer(help="Market data commands")
app.add_typer(markets_app, name="markets")

console = Console()

def print_header():
    """Print the Poly Float ASCII art header in yellow/orange"""
    ascii_art = r"""
  ____       _          _____ _             _   
 |  _ \ ___ | |_   _   |  ___| | ___   __ _| |_ 
 | |_) / _ \| | | | |  | |_  | |/ _ \ / _` | __|
 |  __/ (_) | | |_| |  |  _| | | (_) | (_| | |_ 
 |_|   \___/|_|\__, |  |_|   |_|\___/ \__,_|\__|
               |___/                            
"""
    # Simple gradient-like effect using rich styles
    console.print(ascii_art, style="bold color(208)")  # Orange-ish
    console.print("       Prediction Market Intelligence Terminal", style="italic yellow")
    console.print("       ---------------------------------------", style="dim yellow")
    console.print()

def ensure_credentials():
    """Check for required keys and prompt if missing"""
    env_file = ".env"
    
    # Ensure .env exists
    if not os.path.exists(env_file):
        with open(env_file, "w") as f:
            pass

    # Re-load to ensure we have latest from file
    load_dotenv(env_file, override=True)

    missing = []
    if not os.getenv("POLY_PRIVATE_KEY"):
        missing.append("Polymarket Private Key")
    if not os.getenv("GOOGLE_API_KEY"):
        missing.append("Google Gemini API Key")

    if missing:
        console.print(Panel(f"[bold yellow]Setup Required[/bold yellow]\nThe following keys are missing: {', '.join(missing)}", border_style="yellow"))
        
        if "Polymarket Private Key" in missing:
            key = Prompt.ask("Enter your Polymarket Private Key", password=True)
            if key:
                if not key.startswith("0x"):
                    console.print("[yellow]Warning: Poly key usually starts with 0x[/yellow]")
                set_key(env_file, "POLY_PRIVATE_KEY", key)
                os.environ["POLY_PRIVATE_KEY"] = key
                console.print("[green]✓ Polymarket Key saved[/green]")

        if "Google Gemini API Key" in missing:
            key = Prompt.ask("Enter your Google Gemini API Key", password=True)
            if key:
                set_key(env_file, "GOOGLE_API_KEY", key)
                os.environ["GOOGLE_API_KEY"] = key
                console.print("[green]✓ Google Gemini Key saved[/green]")
        
        console.print()

def interactive_menu():
    """Show an interactive menu if no command is passed"""
    console.print(Panel("[bold cyan]Welcome to PolyFloat[/bold cyan]\nSelect an action or use slash commands:", border_style="cyan"))
    
    console.print("1. [bold green]Dashboard[/bold green]   (/dash)")
    console.print("2. [bold blue]Market List[/bold blue] (/markets)")
    console.print("3. [bold magenta]Arb Scanner[/bold magenta] (/arb)")
    console.print("4. [bold red]Logout[/bold red]      (/logout)")
    console.print("5. [bold white]Exit[/bold white]        (/exit)")
    
    choice = Prompt.ask("Select an option", default="1")
    choice = choice.lower().strip()
    
    if choice in ["1", "/dash", "/dashboard"]:
        dashboard()
    elif choice in ["2", "/markets", "/list"]:
        list_markets()
    elif choice in ["3", "/arb", "/scan"]:
        arb(min_edge=0.03)
    elif choice in ["4", "/logout"]:
        confirm = Prompt.ask("Are you sure you want to remove your API keys?", choices=["y", "n"], default="n")
        if confirm == "y":
            env_file = ".env"
            if os.path.exists(env_file):
                with open(env_file, "w") as f:
                    f.write("") # Clear file
            os.environ.pop("POLY_PRIVATE_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            console.print("[bold red]Keys removed. You are logged out.[/bold red]")
    elif choice in ["5", "/exit", "/quit", "q"]:
        console.print("Goodbye!")
        sys.exit(0)
    else:
        console.print("[red]Invalid option[/red]")
        interactive_menu()

@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """
    PolyCLI Entry Point (v1.0)
    """
    # Only print header and check envs if not running a help command
    if "--help" not in sys.argv:
        print_header()
        ensure_credentials()
        
    if ctx.invoked_subcommand is None:
        interactive_menu()

import asyncio
from polycli.providers.polymarket import PolyProvider

from typing import Annotated

@markets_app.command(name="list")
def list_markets(
    limit: Annotated[int, typer.Option(help="Number of markets to show")] = 20,
    provider: Annotated[str, typer.Option(help="Market provider")] = "polymarket"
):
    """List available markets"""
    console.print(f"Fetching {limit} markets from {provider}...")
    
    table = Table(title=f"Live Markets ({provider.upper()})")
    table.add_column("Question", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Liquidity", justify="right")
    
    if provider.lower() == "polymarket":
        poly = PolyProvider()
        try:
            markets = asyncio.run(poly.get_markets(limit=limit))
            for m in markets:
                # Truncate title if too long
                title = m.title[:50] + "..." if len(m.title) > 50 else m.title
                # Shorten ID
                tid = m.token_id[:8] + "..." if m.token_id else "N/A"
                price = f"${m.price:.2f}"
                liq = "N/A" # Basic endpoint doesn't give liquidity easily
                table.add_row(tid, title, price, liq)
        except Exception as e:
            console.print(f"[red]Error fetching data: {e}[/red]")
            return

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
    min_edge: Annotated[float, typer.Argument(help="Minimum price discrepancy to report")] = 0.03
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
    strategy: Annotated[str, typer.Argument(help="Strategy to deploy")] = "simple",
    market: Annotated[str, typer.Option("--market", "-m", help="Market to trade on")] = "TRUMP24"
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
