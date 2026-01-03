import typer
import os
import sys
import asyncio
import time
import hashlib
from pathlib import Path
from typing import Optional
from functools import wraps
from decimal import Decimal
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from dotenv import load_dotenv, set_key
from polycli.utils.config import get_paper_mode, set_paper_mode
from polycli.setup import SetupWizard
from polycli.telemetry import get_session_id, TelemetryEvent

# Load existing environment variables
load_dotenv(override=True)

app = typer.Typer(
    help="PolyCLI: Agentic Terminal for Prediction Markets",
    no_args_is_help=False,
    add_completion=False,
)
markets_app = typer.Typer(help="Market data commands")
app.add_typer(markets_app, name="markets")

paper_app = typer.Typer(help="Paper trading commands")
app.add_typer(paper_app, name="paper")

risk_app = typer.Typer(help="Risk management commands")
app.add_typer(risk_app, name="risk")

console = Console()


def get_telemetry_store():
    """Get or create the telemetry store instance."""
    from polycli.telemetry.store import TelemetryStore

    return TelemetryStore()


def track_command(func):
    """Decorator to emit command_invoked telemetry events."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            args_str = str(args) + str(kwargs)
            args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:16]
        except Exception:
            args_hash = "hash_error"

        try:
            store = get_telemetry_store()
            if store.enabled:
                event = TelemetryEvent(
                    event_type="command_invoked",
                    timestamp=time.time(),
                    session_id=get_session_id(),
                    payload={
                        "command": func.__name__,
                        "args_hash": args_hash,
                        "paper_mode": get_paper_mode(),
                    },
                )
                store.emit(event)
        except Exception:
            pass

        return func(*args, **kwargs)

    return wrapper


def setup_update_commands():
    from polycli.update import update_app

    app.add_typer(update_app, name="update")


setup_update_commands()


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
    # Check for both private key AND funder address for Polymarket
    if not is_configured("POLY_PRIVATE_KEY", "SKIP_POLY") or not is_configured(
        "POLY_FUNDER_ADDRESS", "SKIP_POLY"
    ):
        missing.append("Polymarket Credentials")

    if not is_configured("GOOGLE_API_KEY", "SKIP_GEMINI"):
        missing.append("Google Gemini API Key")

    # Kalshi check
    # We are configured if we have a full pair (Email+Pass OR ID+Path/Key) OR if we skipped
    has_kalshi_file = (
        file_vars.get("KALSHI_EMAIL") and file_vars.get("KALSHI_PASSWORD")
    ) or (
        file_vars.get("KALSHI_KEY_ID")
        and (
            file_vars.get("KALSHI_PRIVATE_KEY_PATH")
            or file_vars.get("KALSHI_PRIVATE_KEY")
        )
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

        if "Polymarket Credentials" in missing:
            shell_key = os.environ.get("POLY_PRIVATE_KEY")
            shell_funder = os.environ.get("POLY_FUNDER_ADDRESS")
            use_shell = False
            if shell_key and shell_funder:
                console.print(
                    "\n[bold cyan]Polymarket Integration[/bold cyan] (Detected in Shell Environment)"
                )
                if (
                    Prompt.ask(
                        f"Use POLY_PRIVATE_KEY and POLY_FUNDER_ADDRESS from shell? (Key: {shell_key[:6]}...{shell_key[-4:]}, Funder: {shell_funder[:6]}...{shell_funder[-4:]})",
                        choices=["y", "n"],
                        default="y",
                    )
                    == "y"
                ):
                    set_key(env_file, "POLY_PRIVATE_KEY", shell_key)
                    set_key(env_file, "POLY_FUNDER_ADDRESS", shell_funder)
                    set_key(env_file, "SKIP_POLY", "false")
                    load_dotenv(env_file, override=True)
                    console.print("[green]✓ Credentials imported from shell[/green]")
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

                        # Also collect funder address
                        console.print(
                            "\n[dim]Your funder address is the wallet address that holds your USDC.[/dim]"
                        )
                        funder = Prompt.ask(
                            "Enter your Polymarket Funder Address (wallet address)"
                        )

                        if funder:
                            if not funder.startswith("0x"):
                                console.print(
                                    "[yellow]Warning: Address usually starts with 0x[/yellow]"
                                )

                            set_key(env_file, "POLY_PRIVATE_KEY", key)
                            set_key(env_file, "POLY_FUNDER_ADDRESS", funder)
                            set_key(env_file, "SKIP_POLY", "false")
                            load_dotenv(env_file, override=True)
                            os.environ["POLY_PRIVATE_KEY"] = key
                            os.environ["POLY_FUNDER_ADDRESS"] = funder
                            console.print(
                                "[green]✓ Polymarket credentials saved[/green]"
                            )
                        else:
                            console.print(
                                "[yellow]Funder address required for wallet balance. Setup incomplete.[/yellow]"
                            )
                else:
                    set_key(env_file, "SKIP_POLY", "true")
                    load_dotenv(env_file, override=True)
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
                    load_dotenv(env_file, override=True)
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
                        load_dotenv(env_file, override=True)
                        os.environ["GOOGLE_API_KEY"] = key
                        console.print("[green]✓ Google Gemini Key saved[/green]")
                else:
                    set_key(env_file, "SKIP_GEMINI", "true")
                    load_dotenv(env_file, override=True)
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
                    if s_email:
                        set_key(env_file, "KALSHI_EMAIL", s_email)
                    if s_pass:
                        set_key(env_file, "KALSHI_PASSWORD", s_pass)
                    if s_key_id:
                        set_key(env_file, "KALSHI_KEY_ID", s_key_id)
                    if s_key_path:
                        set_key(env_file, "KALSHI_PRIVATE_KEY_PATH", s_key_path)
                    if s_key_content:
                        set_key(env_file, "KALSHI_PRIVATE_KEY", s_key_content)

                    # Re-check if we have a complete set now
                    load_dotenv(env_file, override=True)
                    f_vars = dotenv_values(env_file)
                    has_complete = (
                        f_vars.get("KALSHI_EMAIL") and f_vars.get("KALSHI_PASSWORD")
                    ) or (
                        f_vars.get("KALSHI_KEY_ID")
                        and (
                            f_vars.get("KALSHI_PRIVATE_KEY_PATH")
                            or f_vars.get("KALSHI_PRIVATE_KEY")
                        )
                    )

                    if has_complete:
                        set_key(env_file, "SKIP_KALSHI", "false")
                        load_dotenv(env_file, override=True)
                        console.print(
                            "[green]✓ Credentials imported from shell[/green]"
                        )
                        use_shell = True
                    else:
                        console.print(
                            "[yellow]Partial credentials imported. Completing setup...[/yellow]"
                        )

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
                            load_dotenv(env_file, override=True)
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
                            load_dotenv(env_file, override=True)
                            os.environ["KALSHI_KEY_ID"] = key_id
                            os.environ["KALSHI_PRIVATE_KEY_PATH"] = path
                            console.print(
                                "[green]✓ Kalshi API Key details saved[/green]"
                            )
                else:
                    set_key(env_file, "SKIP_KALSHI", "true")
                    load_dotenv(env_file, override=True)
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
                        console.print(
                            "[bold red] Authentication Failed: Unable to initialize API client. Check your keys/password.[/bold red]"
                        )
                        # We don't block exit, but user knows.
                    else:
                        # Run check
                        is_valid = asyncio.run(prov.check_connection())
                        if is_valid:
                            console.print(
                                "[bold green]✓ Verified: Connected to Kalshi[/bold green]"
                            )
                        else:
                            console.print(
                                "[bold red]⚠ Warning: API Client initialized but check_connection failed.[/bold red]"
                            )

                        # Cleanup
                        # prov.close() - Removed to avoid shutting down shared pool
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
            "4. [bold yellow]Sentinel[/bold yellow]    (/sentinel) - Launch Sentinel market monitor"
        )
        console.print(
            "5. [bold red]Logout[/bold red]      (/logout) - Remove all stored API keys"
        )
        console.print(
            "6. [bold white]Exit[/bold white]        (/exit) - Quit the application"
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
        elif choice in ["4", "/sentinel", "/watch"]:
            # Launch dashboard with Sentinel panel focused
            console.print("[yellow]Launching Sentinel in Dashboard...[/yellow]")
            console.print("[dim]Press 't' in Dashboard to access Sentinel panel[/dim]")
            dashboard()
        elif choice in ["5", "/logout"]:
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
        elif choice in ["6", "/exit", "/quit", "q"]:
            console.print("Goodbye!")
            sys.exit(0)
        else:
            console.print("[red]Invalid option[/red]")


@app.command("setup")
@track_command
def setup_wizard():
    """Run interactive setup wizard."""
    from polycli.setup import SetupWizard

    wizard = SetupWizard()
    result = wizard.run()

    if result == "launch_dashboard":
        # Launch dashboard after setup
        from polycli.tui import DashboardApp

        app = DashboardApp()
        app.run()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    poly_key: Optional[str] = typer.Option(
        None, "--poly-key", help="Polymarket Private Key"
    ),
    gemini_key: Optional[str] = typer.Option(
        None, "--gemini-key", help="Gemini API Key"
    ),
    kalshi_email: Optional[str] = typer.Option(
        None, "--kalshi-email", help="Kalshi Email"
    ),
    kalshi_pass: Optional[str] = typer.Option(
        None, "--kalshi-pass", help="Kalshi Password"
    ),
    kalshi_key_id: Optional[str] = typer.Option(
        None, "--kalshi-key-id", help="Kalshi Key ID"
    ),
    kalshi_pem: Optional[str] = typer.Option(
        None, "--kalshi-pem", help="Kalshi Private Key Path"
    ),
    paper: bool = typer.Option(
        False, "--paper", "-p", help="Enable paper trading mode"
    ),
    save: bool = typer.Option(False, "--save", help="Persist credentials to .env"),
    check_updates: bool = typer.Option(
        False, "--check-updates", help="Check for updates"
    ),
    update: bool = typer.Option(False, "--update", help="Update to latest version"),
):
    """
    PolyCLI Entry Point (v1.0)
    """
    # Inject Flags into Env (Ephemeral Mode)
    if poly_key:
        os.environ["POLY_PRIVATE_KEY"] = poly_key
    if gemini_key:
        os.environ["GOOGLE_API_KEY"] = gemini_key
    if kalshi_email:
        os.environ["KALSHI_EMAIL"] = kalshi_email
    if kalshi_pass:
        os.environ["KALSHI_PASSWORD"] = kalshi_pass
    if kalshi_key_id:
        os.environ["KALSHI_KEY_ID"] = kalshi_key_id
    if kalshi_pem:
        os.environ["KALSHI_PRIVATE_KEY_PATH"] = kalshi_pem

    if save:
        env_file = ".env"
        if not os.path.exists(env_file):
            with open(env_file, "w") as f:
                pass

        if poly_key:
            set_key(env_file, "POLY_PRIVATE_KEY", poly_key)
        if gemini_key:
            set_key(env_file, "GOOGLE_API_KEY", gemini_key)
        if kalshi_email:
            set_key(env_file, "KALSHI_EMAIL", kalshi_email)
        if kalshi_pass:
            set_key(env_file, "KALSHI_PASSWORD", kalshi_pass)
        if kalshi_key_id:
            set_key(env_file, "KALSHI_KEY_ID", kalshi_key_id)
        if kalshi_pem:
            set_key(env_file, "KALSHI_PRIVATE_KEY_PATH", kalshi_pem)

        # Also mark them as NOT skipped so ensure_credentials doesn't complain
        if poly_key:
            set_key(env_file, "SKIP_POLY", "false")
        if gemini_key:
            set_key(env_file, "SKIP_GEMINI", "false")
        if kalshi_email or kalshi_key_id:
            set_key(env_file, "SKIP_KALSHI", "false")

        load_dotenv(env_file, override=True)

    # Handle paper mode
    if paper:
        set_paper_mode(True)

    # Only print header and check envs if not running a help command
    if "--help" not in sys.argv:
        print_header()
        if get_paper_mode():
            console.print(
                Panel(
                    "[bold yellow]⚠ PAPER TRADING MODE ENABLED[/bold yellow]\n"
                    "All trades are simulated - No real money will be used!",
                    border_style="yellow",
                )
            )

        # Check for first run and auto-trigger setup wizard
        config_path = Path.home() / ".polycli" / "config.yaml"
        if not config_path.exists() and ctx.invoked_subcommand != "setup":
            console.print(
                "[yellow]First run detected - launching setup wizard...[/yellow]"
            )
            wizard = SetupWizard()
            result = wizard.run()

            if result == "launch_dashboard":
                # Launch dashboard after setup
                from polycli.tui import DashboardApp

                dashboard_app = DashboardApp()
                dashboard_app.run()
            return

        ensure_credentials()

        if "--help" not in sys.argv:
            from polycli.utils.update_checker import UpdateChecker

            checker = UpdateChecker()
            info = asyncio.run(checker.check_update())
            if info:
                from polycli.utils.update_checker import format_update_notification

                console.print(format_update_notification(info))

        if check_updates:
            from polycli.utils.update_checker import UpdateChecker

            checker = UpdateChecker()
            info = asyncio.run(checker.check_update(force=True))
            if info:
                from polycli.utils.update_checker import format_update_notification

                console.print(format_update_notification(info))
            else:
                console.print(
                    "[bold green]You are running the latest version[/bold green]"
                )
            sys.exit(0)

        if update:
            from polycli.utils.update_checker import UpdateChecker

            checker = UpdateChecker()
            result = asyncio.run(checker.perform_update(mode="auto"))
            if result.success:
                from polycli.utils.update_checker import format_update_success

                console.print(format_update_success(result))
            else:
                from polycli.utils.update_checker import format_update_failure

                console.print(format_update_failure(result))
            sys.exit(0)

    if ctx.invoked_subcommand is None:
        interactive_menu()


import asyncio
from polycli.providers.polymarket import PolyProvider

from typing import Annotated


@markets_app.command(name="list")
@track_command
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
@track_command
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
                    f"${m.volume_24h/1000:.1f}k",
                )

            console.print(table)
        except Exception as e:
            console.print(f"[red]Search Error: {e}[/red]")


arb_app = typer.Typer(help="Arbitrage scanning commands")
app.add_typer(arb_app, name="arb")


@paper_app.command(name="status")
@track_command
def paper_status():
    """Show paper trading balance and P&L"""
    console.print("[bold cyan]Paper Trading Account Status[/bold cyan]")

    try:
        from polycli.paper.provider import PaperTradingProvider

        provider = PaperTradingProvider(PolyProvider())
        balance = asyncio.run(provider.get_balance())
        positions = asyncio.run(provider.get_positions())

        console.print()
        console.print(f"[bold]Balance:[/bold] ${balance['balance']:.2f}")
        console.print(f"[bold]Positions:[/bold] {len(positions)}")

        if positions:
            console.print()
            table = Table(title="Open Positions")
            table.add_column("Market", style="cyan")
            table.add_column("Side", style="magenta")
            table.add_column("Size", justify="right")
            table.add_column("Avg Price", justify="right")

            for pos in positions:
                table.add_row(
                    pos.get("market_id", "N/A"),
                    pos.get("outcome", "N/A"),
                    f"{pos.get('size', 0):.2f}",
                    f"${pos.get('avg_price', 0):.2f}",
                )

            console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@paper_app.command(name="reset")
def paper_reset(
    balance: float = typer.Option(10000.0, "--balance", "-b", help="Starting balance")
):
    """Reset paper trading account"""
    console.print(
        f"[bold yellow]Resetting paper account to ${balance:.2f}[/bold yellow]"
    )

    try:
        from polycli.paper.provider import PaperTradingProvider

        provider = PaperTradingProvider(PolyProvider())
        asyncio.run(provider.reset(balance))
        console.print("[bold green]✓ Account reset successfully[/bold green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@paper_app.command(name="history")
def paper_history(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of trades to show")
):
    """Show paper trading trade history"""
    console.print(f"[bold cyan]Paper Trading History (Last {limit} trades)[/bold cyan]")

    try:
        from polycli.paper.provider import PaperTradingProvider

        provider = PaperTradingProvider(PolyProvider())
        trades = asyncio.run(provider.get_trades(limit=limit))

        if not trades:
            console.print("[yellow]No trades found[/yellow]")
            return

        table = Table(title="Trade History")
        table.add_column("Time", style="dim")
        table.add_column("Market", style="cyan")
        table.add_column("Side", style="magenta")
        table.add_column("Size", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Fee", justify="right")
        table.add_column("Total", justify="right")

        for trade in trades:
            table.add_row(
                trade.get("executed_at", "N/A"),
                trade.get("market_id", "N/A"),
                trade.get("side", "N/A"),
                f"{trade.get('size', 0):.2f}",
                f"${trade.get('price', 0):.2f}",
                f"${trade.get('fee', 0):.2f}",
                f"${trade.get('total', 0):.2f}",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@risk_app.command("status")
@track_command
def risk_status():
    """Show current risk status and metrics."""
    try:
        from polycli.risk import RiskGuard, RiskConfig

        console.print("[bold cyan]Risk Management Status[/bold cyan]")
        console.print()

        guard = RiskGuard()
        config = RiskConfig.load()

        console.print("[bold]Configuration:[/bold]")
        console.print(
            f"  Max Position Size: [cyan]${config.max_position_size_usd:.2f}[/cyan]"
        )
        console.print(
            f"  Daily Loss Limit: [cyan]${config.daily_loss_limit_usd:.2f}[/cyan]"
        )
        console.print(
            f"  Trading Enabled: [green]Yes[/green]"
            if config.trading_enabled
            else "  Trading Enabled: [red]No[/red]"
        )
        console.print()

        status = guard.get_status()
        console.print("[bold]Current Status:[/bold]")
        console.print(
            f"  Circuit Breaker: [red]TRIGGERED[/red]"
            if status.get("circuit_breaker_active", False)
            else "  Circuit Breaker: [green]OK[/green]"
        )
        console.print(
            f"  Today's Loss: [cyan]${status.get('daily_loss_usd', 0):.2f}[/cyan]"
        )
        console.print(
            f"  Open Positions: [cyan]{status.get('position_count', 0)}[/cyan]"
        )
        console.print(
            f"  Total Exposure: [cyan]${status.get('total_exposure_usd', 0):.2f}[/cyan]"
        )
    except Exception as e:
        console.print(f"[red]Error fetching risk status: {e}[/red]")


@risk_app.command("config")
def risk_config(
    max_position: Optional[float] = typer.Option(None, help="Max position size in USD"),
    daily_loss_limit: Optional[float] = typer.Option(
        None, help="Max daily loss in USD"
    ),
    trading_enabled: Optional[bool] = typer.Option(None, help="Enable/disable trading"),
):
    """Configure risk parameters."""
    try:
        from polycli.risk import RiskConfig

        config = RiskConfig.load()
        if max_position is not None:
            config.max_position_size_usd = Decimal(str(max_position))
        if daily_loss_limit is not None:
            config.daily_loss_limit_usd = Decimal(str(daily_loss_limit))
        if trading_enabled is not None:
            config.trading_enabled = trading_enabled
        config.save()
        console.print("[green]Risk config updated[/green]")
    except Exception as e:
        console.print(f"[red]Error updating config: {e}[/red]")


@risk_app.command("pause")
def risk_pause(minutes: int = typer.Option(60, help="Cooldown minutes")):
    """Trigger circuit breaker to pause all trading."""
    try:
        from polycli.risk import RiskGuard

        guard = RiskGuard()
        guard.trigger_circuit_breaker("Manual pause via CLI", minutes)
        console.print(f"[yellow]Trading paused for {minutes} minutes[/yellow]")
    except Exception as e:
        console.print(f"[red]Error pausing trading: {e}[/red]")


@risk_app.command("resume")
def risk_resume():
    """Resume trading (reset circuit breaker)."""
    try:
        from polycli.risk import RiskGuard

        guard = RiskGuard()
        guard.reset_circuit_breaker()
        console.print("[green]Trading resumed[/green]")
    except Exception as e:
        console.print(f"[red]Error resuming trading: {e}[/red]")


@risk_app.command("blocked")
def risk_blocked(limit: int = typer.Option(20, help="Number of entries")):
    """Show recently blocked trades."""
    try:
        from polycli.risk import RiskAuditStore

        store = RiskAuditStore()
        blocked = store.get_rejected_trades(limit)

        if not blocked:
            console.print("[yellow]No blocked trades found[/yellow]")
            return

        table = Table(title=f"Blocked Trades (Last {limit})")
        table.add_column("Time", style="dim")
        table.add_column("Market", style="cyan")
        table.add_column("Reason", style="red")
        table.add_column("Amount", justify="right")
        table.add_column("Exposure", justify="right")

        for trade in blocked:
            table.add_row(
                trade.get("timestamp", "N/A"),
                trade.get("market_id", "N/A"),
                trade.get("rejection_reason", "Unknown"),
                f"${trade.get('trade_amount_usd', 0):.2f}",
                f"${trade.get('current_exposure_usd', 0):.2f}",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error fetching blocked trades: {e}[/red]")


@arb_app.command(name="scan")
@track_command
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
            with PolyProvider() as poly, KalshiProvider() as kalshi:
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
@track_command
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
    """Deploy an autonomous trading bot [DEPRECATED: Use TradingTools instead]"""
    console.print(
        f"[yellow]Warning:[/yellow] Legacy graph-based trading is deprecated."
    )
    console.print(f"Use TradingTools for agentic trading execution.")
    return


analytics_app = typer.Typer(help="Trading analytics commands")
app.add_typer(analytics_app, name="analytics")


@analytics_app.command("summary")
@track_command
def analytics_summary(
    days: int = typer.Option(30, help="Number of days to analyze"),
    provider: str = typer.Option("polymarket", help="Provider to analyze"),
):
    """Show performance summary."""
    import asyncio
    from polycli.analytics import PerformanceCalculator

    async def run():
        calc = PerformanceCalculator()
        metrics = await calc.calculate_metrics(provider, days)

        console.print(f"\n[bold]Performance Summary ({days} days)[/bold]")
        console.print(f"Total P&L: ${metrics.total_pnl:+.2f}")
        console.print(f"Win Rate: {metrics.win_rate:.1%}")
        console.print(f"Total Trades: {metrics.total_trades}")
        console.print(f"Profit Factor: {metrics.profit_factor:.2f}")
        console.print(f"Max Drawdown: {metrics.max_drawdown_pct:.1%}")

    asyncio.run(run())


@analytics_app.command("export")
def analytics_export(
    output: Path = typer.Option(Path("trades.csv"), help="Output file"),
    days: int = typer.Option(30, help="Days to export"),
):
    """Export trade history to CSV."""
    from polycli.analytics import AnalyticsStore
    import csv

    store = AnalyticsStore()
    from datetime import datetime, timedelta

    trades = store.get_trades(start_date=datetime.utcnow() - timedelta(days=days))

    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Date", "Market", "Side", "Size", "Price", "Total", "Fee", "P&L"]
        )
        for t in trades:
            writer.writerow(
                [
                    t.timestamp.isoformat(),
                    t.market_name,
                    t.side,
                    t.size,
                    t.price,
                    t.total,
                    t.fee,
                    t.pnl or "",
                ]
            )

    console.print(f"[green]Exported {len(trades)} trades to {output}[/green]")


@app.command("stop")
@track_command
def emergency_stop(
    cancel_orders: bool = typer.Option(True, help="Cancel all pending orders"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    Trigger emergency stop - halt all agents and optionally cancel orders
    """
    import asyncio
    from polycli.emergency import EmergencyStopController, StopReason

    if not force:
        confirm = typer.confirm(
            "This will halt all agents and cancel pending orders. Continue?", abort=True
        )

    async def do_stop():
        controller = EmergencyStopController()
        event = await controller.trigger_stop(
            reason=StopReason.USER_INITIATED, cancel_orders=cancel_orders
        )
        return event

    event = asyncio.run(do_stop())

    console.print("[bold red]EMERGENCY STOP ACTIVATED[/bold red]")
    console.print(f"  Event ID: {event.id}")
    console.print(f"  Orders cancelled: {event.orders_cancelled}")
    console.print(f"  WebSockets closed: {event.websockets_closed}")
    console.print("\n[yellow]Use 'poly resume' to restart trading[/yellow]")


@app.command("resume")
def resume_trading():
    """Resume trading after emergency stop"""
    import asyncio
    from polycli.emergency import EmergencyStopController

    controller = EmergencyStopController()

    if not controller.is_stopped:
        console.print("[green]System is not stopped, nothing to resume[/green]")
        return

    asyncio.run(controller.resume(resumed_by="cli"))
    console.print("[green]Trading resumed[/green]")


@app.command("status")
def system_status():
    """Show system status including emergency stop state"""
    from polycli.emergency import EmergencyStopController

    controller = EmergencyStopController()

    if controller.is_stopped:
        event = controller.current_event
        console.print("[bold red]SYSTEM STOPPED[/bold red]")
        if event:
            console.print(f"  Reason: {event.reason.value}")
            console.print(f"  Time: {event.timestamp}")
            console.print(f"  Description: {event.description}")
    else:
        console.print("[green]System running normally[/green]")


@app.command()
def stats(
    days: int = typer.Option(7, help="Number of days to analyze"),
    command: str = typer.Option(
        "summary", help="summary|funnel|errors|recent|sessions"
    ),
):
    """View usage telemetry and statistics."""
    from polycli.telemetry.store import TelemetryStore
    from polycli.telemetry.formatters import (
        _show_summary,
        _show_funnel,
        _show_errors,
        _show_recent,
        _show_sessions,
    )

    since = time.time() - (days * 86400)
    store = TelemetryStore()

    if command == "summary":
        _show_summary(store, since)
    elif command == "funnel":
        _show_funnel(store, since)
    elif command == "errors":
        _show_errors(store, since)
    elif command == "recent":
        _show_recent(store, 20)
    elif command == "sessions":
        _show_sessions(store, since)


if __name__ == "__main__":
    app()
