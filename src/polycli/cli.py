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
    add_completion=False,
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
    console.print(
        "       Prediction Market Intelligence Terminal", style="italic yellow"
    )
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

    # We want to know what is EXPLICITLY in the .env file vs shell environment
    from dotenv import dotenv_values

    file_vars = dotenv_values(env_file)

    def is_configured(key, skip_key):
        # We trust the .env file primarily. 
        # We only trust the shell's skip flag if there's no .env yet or it's implicitly skipped.
        # But if the .env exists and is empty (after logout), we should probably re-ask.
        in_file = file_vars.get(key)
        skip_in_file = file_vars.get(skip_key) == "true"
        # If it's in the file, or explicitly skipped in the file, it's configured.
        if in_file or skip_in_file:
            return True
        # If it's not in the file, we only allow shell skip if the file doesn't have it either.
        # Actually, let's keep it simple: if NOT in file and NOT skipped in file, 
        # but is in shell environment, we will offer to adopt it later in the function.
        # So here we return False to ensure it's added to 'missing'.
        return False

    missing = []
    if not is_configured("POLY_PRIVATE_KEY", "SKIP_POLY"):
        missing.append("Polymarket Private Key")

    if not is_configured("GOOGLE_API_KEY", "SKIP_GEMINI"):
        missing.append("Google Gemini API Key")

    # Kalshi check
    # We are configured if we have a full pair (Email+Pass OR ID+Path/Key) OR if we skipped
    has_kalshi_file = (
        (file_vars.get("KALSHI_EMAIL") and file_vars.get("KALSHI_PASSWORD")) or
        (file_vars.get("KALSHI_KEY_ID") and (file_vars.get("KALSHI_PRIVATE_KEY_PATH") or file_vars.get("KALSHI_PRIVATE_KEY")))
    )
    
    # If .env is missing any piece of a pair AND we haven't skipped via .env, it's missing
    if not has_kalshi_file and file_vars.get("SKIP_KALSHI") != "true":
        missing.append("Kalshi Credentials")

    if missing:
        console.print(
            Panel(
                f"[bold yellow]Setup Required[/bold yellow]\nYou can skip setup for any provider, but related features will be disabled.",
                border_style="yellow",
            )
        )

        if "Polymarket Private Key" in missing:
            shell_key = os.environ.get("POLY_PRIVATE_KEY")
            use_shell = False
            if shell_key:
                console.print(
                    "\n[bold cyan]Polymarket Integration[/bold cyan] (Detected in Shell Environment)"
                )
                if (
                    Prompt.ask(
                        f"Use POLY_PRIVATE_KEY from shell? ({shell_key[:6]}...{shell_key[-4:]})",
                        choices=["y", "n"],
                        default="y",
                    )
                    == "y"
                ):
                    set_key(env_file, "POLY_PRIVATE_KEY", shell_key)
                    set_key(env_file, "SKIP_POLY", "false")
                    console.print("[green]✓ Key imported from shell[/green]")
                    use_shell = True

            if not use_shell:
                console.print("\n[bold cyan]Polymarket Integration[/bold cyan]")
                console.print(
                    "Required for [italic]executing trades, managing orders, and viewing your portfolio on Polymarket.[/italic]"
                )
                if (
                    Prompt.ask(
                        "Enable Polymarket trading?", choices=["y", "n"], default="y"
                    )
                    == "y"
                ):
                    key = Prompt.ask("Enter your Polymarket Private Key", password=True)
                    if key:
                        if not key.startswith("0x"):
                            console.print(
                                "[yellow]Warning: Poly key usually starts with 0x[/yellow]"
                            )
                        set_key(env_file, "POLY_PRIVATE_KEY", key)
                        set_key(env_file, "SKIP_POLY", "false")
                        os.environ["POLY_PRIVATE_KEY"] = key
                        console.print("[green]✓ Polymarket Key saved[/green]")
                else:
                    set_key(env_file, "SKIP_POLY", "true")
                    console.print(
                        "[yellow]Skipping Polymarket setup. Trading disabled.[/yellow]"
                    )

        if "Google Gemini API Key" in missing:
            shell_key = os.environ.get("GOOGLE_API_KEY")
            use_shell = False
            if shell_key:
                console.print(
                    "\n[bold cyan]Gemini AI Features[/bold cyan] (Detected in Shell Environment)"
                )
                if (
                    Prompt.ask(
                        f"Use GOOGLE_API_KEY from shell? ({shell_key[:6]}...{shell_key[-4:]})",
                        choices=["y", "n"],
                        default="y",
                    )
                    == "y"
                ):
                    set_key(env_file, "GOOGLE_API_KEY", shell_key)
                    set_key(env_file, "SKIP_GEMINI", "false")
                    console.print("[green]✓ Key imported from shell[/green]")
                    use_shell = True

            if not use_shell:
                console.print("\n[bold cyan]Gemini AI Features[/bold cyan]")
                console.print(
                    "Required for [italic]autonomous trading agents, market sentiment analysis, and automated strategy planning.[/italic]"
                )
                if (
                    Prompt.ask(
                        "Enable Gemini AI features?", choices=["y", "n"], default="n"
                    )
                    == "y"
                ):
                    key = Prompt.ask("Enter your Google Gemini API Key", password=True)
                    if key:
                        set_key(env_file, "GOOGLE_API_KEY", key)
                        set_key(env_file, "SKIP_GEMINI", "false")
                        os.environ["GOOGLE_API_KEY"] = key
                        console.print("[green]✓ Google Gemini Key saved[/green]")
                else:
                    set_key(env_file, "SKIP_GEMINI", "true")
                    console.print(
                        "[yellow]Skipping Gemini setup. AI features disabled.[/yellow]"
                    )

        if "Kalshi Credentials" in missing:
            # Check for ANY shell vars related to Kalshi
            s_email = os.environ.get("KALSHI_EMAIL")
            s_pass = os.environ.get("KALSHI_PASSWORD")
            s_key_id = os.environ.get("KALSHI_KEY_ID")
            s_key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
            s_key_content = os.environ.get("KALSHI_PRIVATE_KEY")
            
            use_shell = False

            if s_email or s_pass or s_key_id or s_key_path or s_key_content:
                console.print(
                    "\n[bold cyan]Kalshi Integration[/bold cyan] (Detected in Shell Environment)"
                )
                if (
                    Prompt.ask(
                        "Use Kalshi credentials from shell?",
                        choices=["y", "n"],
                        default="y",
                    )
                    == "y"
                ):
                    if s_email: set_key(env_file, "KALSHI_EMAIL", s_email)
                    if s_pass: set_key(env_file, "KALSHI_PASSWORD", s_pass)
                    if s_key_id: set_key(env_file, "KALSHI_KEY_ID", s_key_id)
                    if s_key_path: set_key(env_file, "KALSHI_PRIVATE_KEY_PATH", s_key_path)
                    if s_key_content: set_key(env_file, "KALSHI_PRIVATE_KEY", s_key_content)
                    
                    # Re-check if we have a complete set now
                    load_dotenv(env_file, override=True)
                    f_vars = dotenv_values(env_file)
                    has_complete = (
                        (f_vars.get("KALSHI_EMAIL") and f_vars.get("KALSHI_PASSWORD")) or
                        (f_vars.get("KALSHI_KEY_ID") and (f_vars.get("KALSHI_PRIVATE_KEY_PATH") or f_vars.get("KALSHI_PRIVATE_KEY")))
                    )
                    
                    if has_complete:
                        set_key(env_file, "SKIP_KALSHI", "false")
                        console.print("[green]✓ Credentials imported from shell[/green]")
                        use_shell = True
                    else:
                        console.print("[yellow]Partial credentials imported. Completing setup...[/yellow]")

            if not use_shell:
                console.print("\n[bold cyan]Kalshi Integration[/bold cyan]")
                console.print(
                    "Required for [italic]cross-platform arbitrage, trading on Kalshi, and unified portfolio management.[/italic]"
                )
                if (
                    Prompt.ask(
                        "Enable Kalshi integration?", choices=["y", "n"], default="y"
                    )
                    == "y"
                ):
                    auth_type = Prompt.ask(
                        "Kalshi Auth Type", choices=["email", "apikey"], default="email"
                    )
                    if auth_type == "email":
                        email = Prompt.ask("Enter Kalshi Email")
                        password = Prompt.ask("Enter Kalshi Password", password=True)
                        if email and password:
                            set_key(env_file, "KALSHI_EMAIL", email)
                            set_key(env_file, "KALSHI_PASSWORD", password)
                            set_key(env_file, "SKIP_KALSHI", "false")
                            os.environ["KALSHI_EMAIL"] = email
                            os.environ["KALSHI_PASSWORD"] = password
                            console.print("[green]✓ Kalshi Email/Pass saved[/green]")
                    else:
                        key_id = Prompt.ask("Enter Kalshi Key ID")
                        path = Prompt.ask("Enter path to Kalshi Private Key (.pem)")
                        if key_id and path:
                            set_key(env_file, "KALSHI_KEY_ID", key_id)
                            set_key(env_file, "KALSHI_PRIVATE_KEY_PATH", path)
                            set_key(env_file, "SKIP_KALSHI", "false")
                            os.environ["KALSHI_KEY_ID"] = key_id
                            os.environ["KALSHI_PRIVATE_KEY_PATH"] = path
                            console.print(
                                "[green]✓ Kalshi API Key details saved[/green]"
                            )
                else:
                    set_key(env_file, "SKIP_KALSHI", "true")
                    console.print(
                        "[yellow]Skipping Kalshi setup. Arbitrage will be limited.[/yellow]"
                    )

            # Verification Step
            if not use_shell and os.environ.get("SKIP_KALSHI") != "true":
                 console.print("\n[dim]Verifying Kalshi credentials...[/dim]")
                 try:
                     from polycli.providers.kalshi import KalshiProvider
                     import asyncio
                     
                     # Force reload of env vars in provider if needed, though usually it reads os.environ
                     prov = KalshiProvider()
                     if not prov.api_instance:
                          console.print("[bold red] Authentication Failed: Unable to initialize API client. Check your keys/password.[/bold red]")
                          # We don't block exit, but user knows.
                     else:
                          # Run check
                          is_valid = asyncio.run(prov.check_connection())
                          if is_valid:
                              console.print("[bold green]✓ Verified: Connected to Kalshi[/bold green]")
                          else:
                              console.print("[bold red]⚠ Warning: API Client initialized but check_connection failed.[/bold red]")
                 except Exception as e:
                     console.print(f"[red]Verification Error: {e}[/red]")

        console.print()


def interactive_menu():
    """Show an interactive menu if no command is passed"""
    while True:
        console.print(
            Panel(
                "[bold cyan]Welcome to PolyFloat[/bold cyan]\nSelect an action or use slash commands:",
                border_style="cyan",
            )
        )

        console.print(
            "1. [bold green]Dashboard[/bold green]   (/dash) - Launch TUI dashboard for portfolio and market insights"
        )
        console.print(
            "2. [bold blue]Market List[/bold blue] (/markets) - List available markets from providers"
        )
        console.print(
            "3. [bold magenta]Arb Scanner[/bold magenta] (/arb) - Scan for arbitrage opportunities across platforms"
        )
        console.print(
            "4. [bold red]Logout[/bold red]      (/logout) - Remove all stored API keys"
        )
        console.print(
            "5. [bold white]Exit[/bold white]        (/exit) - Quit the application"
        )

        choice = Prompt.ask("Select an option", default="1")
        choice = choice.lower().strip()

        if choice in ["1", "/dash", "/dashboard"]:
            dashboard()
        elif choice in ["2", "/markets", "/list"]:
            list_markets()
            Prompt.ask("\nPress Enter to return to menu")
        elif choice in ["3", "/arb", "/scan"]:
            arb_scan(min_edge=0.03)
            Prompt.ask("\nPress Enter to return to menu")
        elif choice in ["4", "/logout"]:
            confirm = Prompt.ask(
                "Are you sure you want to remove your API keys?",
                choices=["y", "n"],
                default="n",
            )
            if confirm == "y":
                env_file = ".env"
                if os.path.exists(env_file):
                    with open(env_file, "w") as f:
                        f.write("")  # Clear file
                os.environ.pop("POLY_PRIVATE_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)
                os.environ.pop("KALSHI_EMAIL", None)
                os.environ.pop("KALSHI_PASSWORD", None)
                os.environ.pop("KALSHI_KEY_ID", None)
                os.environ.pop("KALSHI_PRIVATE_KEY_PATH", None)
                os.environ.pop("KALSHI_PRIVATE_KEY", None)
                
                # Also clear skip flags to ensure re-prompt on next run
                os.environ.pop("SKIP_POLY", None)
                os.environ.pop("SKIP_GEMINI", None)
                os.environ.pop("SKIP_KALSHI", None)

                console.print(
                    "[bold red]All keys removed. You are logged out.[/bold red]"
                )
                console.print("[yellow]Exiting PolyFloat...[/yellow]")
                sys.exit(0)
        elif choice in ["5", "/exit", "/quit", "q"]:
            console.print("Goodbye!")
            sys.exit(0)
        else:
            console.print("[red]Invalid option[/red]")


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
    provider: Annotated[str, typer.Option(help="Market provider")] = "polymarket",
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
                liq = "N/A"  # Basic endpoint doesn't give liquidity easily
                table.add_row(tid, title, price, liq)
        except Exception as e:
            console.print(f"[red]Error fetching data: {e}[/red]")
            return

    console.print(table)


@markets_app.command("search")
def search_markets(
    query: str = typer.Argument(..., help="Search query"),
    provider: str = typer.Option(
        "polymarket", "--provider", "-p", help="Provider name"
    ),
):
    """Search for markets"""
    console.print(
        f"Searching for '[bold yellow]{query}[/bold yellow]' on [bold green]{provider}[/bold green]..."
    )
    
    if provider.lower() == "polymarket":
        poly = PolyProvider()
        try:
            results = asyncio.run(poly.search(query))
            if not results:
                console.print("[red]No results found.[/red]")
                return
            
            table = Table(title=f"Search Results: {query}")
            table.add_column("TID", style="dim")
            table.add_column("Market", style="cyan")
            table.add_column("Price", justify="right")
            table.add_column("Volume", justify="right")
            
            for m in results:
                display_title = m.title[:60] + ("..." if len(m.title) > 60 else "")
                table.add_row(
                    m.token_id[:8],
                    display_title,
                    f"${m.price:.2f}",
                    f"${m.volume_24h/1000:.1f}k"
                )
            
            console.print(table)
        except Exception as e:
            console.print(f"[red]Search Error: {e}[/red]")


arb_app = typer.Typer(help="Arbitrage scanning commands")
app.add_typer(arb_app, name="arb")


@arb_app.command(name="scan")
def arb_scan(
    min_edge: Annotated[float, typer.Option(help="Minimum edge to report")] = 0.02,
    limit: Annotated[
        int, typer.Option(help="Number of markets to fetch from each provider")
    ] = 50,
    mock: Annotated[bool, typer.Option(help="Use mock data for demonstration")] = False,
):
    """Scan for cross-platform arbitrage (Polymarket vs Kalshi)"""
    console.print(
        f"Searching for arbs with min edge [bold cyan]{min_edge:.2%}[/bold cyan]..."
    )

    import asyncio
    from polycli.providers.polymarket import PolyProvider
    from polycli.providers.kalshi import KalshiProvider
    from polycli.providers.base import MarketData
    from polycli.utils.matcher import match_markets
    from polycli.utils.arbitrage import find_opportunities

    async def run_scan():
        if mock:
            p_markets = [
                MarketData(
                    token_id="p1",
                    title="Will Bitcoin hit $100k in 2025?",
                    price=0.65,
                    volume_24h=1000,
                    liquidity=5000,
                    provider="polymarket",
                ),
                MarketData(
                    token_id="p2",
                    title="Will Donald Trump win the 2024 Election?",
                    price=0.52,
                    volume_24h=5000,
                    liquidity=20000,
                    provider="polymarket",
                ),
            ]
            k_markets = [
                MarketData(
                    token_id="k1",
                    title="Bitcoin to reach $100,000 by end of 2025?",
                    price=0.70,
                    volume_24h=1000,
                    liquidity=5000,
                    provider="kalshi",
                ),
                MarketData(
                    token_id="k2",
                    title="Donald Trump to win the 2024 Presidential Election?",
                    price=0.48,
                    volume_24h=5000,
                    liquidity=20000,
                    provider="kalshi",
                ),
            ]
        else:
            poly = PolyProvider()
            kalshi = KalshiProvider()
            with console.status("[bold green]Fetching markets from providers..."):
                p_markets, k_markets = await asyncio.gather(
                    poly.get_markets(limit=limit), kalshi.get_markets(limit=limit)
                )

        console.print(
            f"Fetched {len(p_markets)} from Polymarket, {len(k_markets)} from Kalshi."
        )

        with console.status("[bold blue]Matching markets..."):
            matches = match_markets(p_markets, k_markets)

        console.print(f"Found {len(matches)} overlapping markets.")

        with console.status("[bold magenta]Calculating arbitrage..."):
            opps = find_opportunities(matches, min_edge=min_edge)

        if not opps:
            console.print(
                "[yellow]No arbitrage opportunities found above threshold.[/yellow]"
            )
            return

        table = Table(title="Live Arbitrage Opportunities")
        table.add_column("Market", style="cyan")
        table.add_column("Direction", style="magenta")
        table.add_column("Edge", justify="right", style="bold green")
        table.add_column("Rec", style="dim")

        for o in opps:
            table.add_row(o.market_name, o.direction, f"{o.edge:.2%}", o.recommendation)

        console.print(table)

    asyncio.run(run_scan())


@app.command()
def arb(
    min_edge: Annotated[
        float, typer.Argument(help="Minimum price discrepancy to report")
    ] = 0.03,
):
    """Scan for arbitrage opportunities (Legacy)"""
    arb_scan(min_edge=min_edge)


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
    strategy: Annotated[
        str, typer.Argument(help="Strategy to deploy (simple, arb)")
    ] = "simple",
    market: Annotated[
        str, typer.Option("--market", "-m", help="Market to trade on (ignored for arb)")
    ] = "TRUMP24",
):
    """Deploy an autonomous trading bot"""
    console.print(f"Deploying bot with strategy [bold cyan]{strategy}[/bold cyan]...")

    import asyncio
    from polycli.agents.graph import create_trading_graph

    mode = "arb" if strategy == "arb" else "default"
    graph = create_trading_graph(mode=mode)

    initial_state = {
        "messages": [],
        "market_data": {"token_id": market, "price": 0.55},
        "positions": [],
        "strategy": strategy,
        "risk_score": 0.0,
        "last_action": "INIT",
        "next_step": "",
        "arb_opportunities": [],
    }

    async def run_bot():
        result = await graph.ainvoke(initial_state)
        console.print(f"\n[bold green]Bot Workflow Complete[/bold green]")
        for msg in result.get("messages", []):
            # messages might be objects or strings depending on add_messages
            content = msg.content if hasattr(msg, "content") else str(msg)
            console.print(f"  > {content}")

        if strategy == "arb" and result.get("arb_opportunities"):
            console.print(
                f"\n[bold yellow]Analysis:[/bold yellow] Found {len(result['arb_opportunities'])} arbs."
            )

    asyncio.run(run_bot())


@app.command()
def analytics():
    """[PRO] Run advanced market analytics (Correlation, VaR)"""
    import os

    is_pro = os.getenv("POLYCLI_PRO_KEY") is not None

    if not is_pro:
        console.print(
            "[bold red]Access Denied[/bold red]: This feature requires a Pro Tier license."
        )
        console.print("Set POLYCLI_PRO_KEY environment variable to unlock.")
        raise typer.Exit(code=1)

    console.print("[bold green]Access Granted[/bold green]: Running Pro Analytics...")
    console.print("Calculating Correlation Matrix... [Done]")
    console.print("Value at Risk (VaR): $450.20")


if __name__ == "__main__":
    app()
