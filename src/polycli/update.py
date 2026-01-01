"""Update commands for PolyFloat CLI."""
import asyncio
import typer
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from polycli.utils.update_checker import (
    UpdateChecker,
    format_update_notification,
    format_update_success,
    format_update_failure,
)

console = Console()
update_app = typer.Typer(help="Update and version management commands")


@update_app.command("check")
def check_updates(
    force: bool = typer.Option(
        False, "--force", "-f", help="Force check even if cached"
    ),
):
    """Check for available updates."""

    async def _check():
        checker = UpdateChecker()
        info = await checker.check_update(force=force)

        if not info:
            console.print(
                Panel(
                    Text("✅ You are running the latest version", style="bold green"),
                    title="No Updates",
                    border_style="green",
                )
            )
            return

        console.print(format_update_notification(info))

    asyncio.run(_check())


@update_app.command("install")
def update_install(
    channel: str = typer.Option(
        "stable", "--channel", "-c", help="Update channel (stable, beta, latest)"
    ),
    mode: str = typer.Option(
        "auto", "--mode", "-m", help="Update mode (auto, notify, disabled)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force update even if no new version"
    ),
):
    """Update PolyFloat to the latest version."""

    async def _update():
        checker = UpdateChecker()

        if mode == "notify":
            info = await checker.check_update(force=True)
            if info:
                console.print(format_update_notification(info))
            else:
                console.print(
                    Panel(
                        Text(
                            "✅ You are running the latest version", style="bold green"
                        ),
                        title="No Updates",
                        border_style="green",
                    )
                )
            return

        if not force:
            info = await checker.check_update(force=True)
            if not info:
                console.print(
                    Panel(
                        Text(
                            "✅ You are running the latest version", style="bold green"
                        ),
                        title="No Updates",
                        border_style="green",
                    )
                )
                return

        result = await checker.perform_update(channel=channel, mode=mode)

        if result.success:
            console.print(format_update_success(result))
        else:
            console.print(format_update_failure(result))

    asyncio.run(_update())
