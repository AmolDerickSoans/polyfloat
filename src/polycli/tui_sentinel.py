"""
Sentinel Agent TUI Widget.

A simple, explanatory panel for market monitoring and trade proposals.
"""

from decimal import Decimal
from typing import Any, Callable, List, Optional
import asyncio

from rich.panel import Panel
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Static,
    Select,
    Rule,
    Markdown,
)
from textual.message import Message
import structlog

from polycli.sentinel import (
    SentinelAgent,
    SentinelConfig,
    SentinelProposal,
    TriggerCondition,
    TriggerType,
    WatchedMarket,
    ProposalStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Help Modal
# =============================================================================

SENTINEL_HELP = """
# What is Sentinel?

Sentinel is your **market watchdog**. It monitors markets you care about and 
alerts you when specific conditions are met.

## How it works

1. **Select a market** from the market list (left panel)
2. **Add a trigger** - e.g., "alert me when price drops below $0.45"
3. **Start Sentinel** - it watches continuously in the background
4. **Get proposals** - when conditions fire, you see actionable proposals
5. **You decide** - approve to trade, or reject/ignore

## Key Concepts

| Term | Meaning |
|------|---------|
| **Trigger** | A condition like "price below $0.45" |
| **Proposal** | A suggestion to trade when a trigger fires |
| **Cooldown** | Wait time between proposals (prevents spam) |

## Trigger Types

- **Price Below/Above** - Alert when price crosses a threshold
- **Spread Wide/Narrow** - Alert on liquidity changes  
- **Volume Spike** - Alert on unusual trading activity

## Important

- Sentinel **never trades automatically**
- You always approve or reject proposals
- Proposals expire after 2 minutes if not acted on

---
*Press Escape or click outside to close*
"""


class HelpModal(ModalScreen):
    """Modal showing Sentinel help/explanation."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Markdown(SENTINEL_HELP, id="help-content")
            yield Button("Got it!", id="close-help", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-help":
            self.dismiss()


# =============================================================================
# Configuration Modal
# =============================================================================


class ConfigModal(ModalScreen):
    """Modal for Sentinel configuration."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, config: Optional[SentinelConfig] = None, **kwargs):
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="config-container"):
            yield Label("[bold]Sentinel Configuration[/bold]", id="config-title")
            yield Rule()

            # Global settings
            yield Label("Global Settings", classes="config-section")

            with Horizontal(classes="config-row"):
                yield Label("Cooldown between proposals:")
                yield Input(
                    value=str(
                        self._config.global_cooldown_seconds if self._config else 60
                    ),
                    id="cooldown_input",
                    type="integer",
                )
                yield Label("seconds")

            with Horizontal(classes="config-row"):
                yield Label("Max proposals per hour:")
                yield Input(
                    value=str(
                        self._config.max_proposals_per_hour if self._config else 10
                    ),
                    id="max_proposals_input",
                    type="integer",
                )

            with Horizontal(classes="config-row"):
                yield Label("Poll interval:")
                yield Input(
                    value=str(
                        self._config.poll_interval_seconds if self._config else 5.0
                    ),
                    id="poll_interval_input",
                    type="number",
                )
                yield Label("seconds")

            yield Rule()

            # Watched markets list
            yield Label("Watched Markets", classes="config-section")
            yield DataTable(id="watched_markets_table")

            yield Rule()

            with Horizontal(classes="config-buttons"):
                yield Button("Save", id="save-config", variant="success")
                yield Button("Cancel", id="cancel-config", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#watched_markets_table", DataTable)
        table.add_columns("Market", "Provider", "Triggers", "Cooldown")

        if self._config:
            for wm in self._config.watched_markets:
                triggers_str = ", ".join(
                    f"{t.trigger_type.value} {t.threshold}" for t in wm.triggers
                )
                table.add_row(
                    wm.market_id[:20] + "...",
                    wm.provider,
                    triggers_str[:30],
                    f"{wm.cooldown_seconds}s",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-config":
            self.dismiss(None)
        elif event.button.id == "save-config":
            # Collect values and return new config
            try:
                cooldown = int(self.query_one("#cooldown_input", Input).value)
                max_proposals = int(self.query_one("#max_proposals_input", Input).value)
                poll_interval = float(
                    self.query_one("#poll_interval_input", Input).value
                )

                # Keep existing watched markets, just update global settings
                new_config = SentinelConfig.create(
                    watched_markets=list(self._config.watched_markets)
                    if self._config
                    else [],
                    global_cooldown_seconds=cooldown,
                    max_proposals_per_hour=max_proposals,
                    poll_interval_seconds=poll_interval,
                )
                self.dismiss(new_config)
            except ValueError:
                self.notify("Invalid values", severity="error")


# =============================================================================
# Proposal Widget
# =============================================================================


class ProposalWidget(Static):
    """Displays a single proposal with approve/reject buttons."""

    class Decided(Message):
        """Emitted when user makes a decision."""

        def __init__(self, proposal_id: str, approved: bool) -> None:
            self.proposal_id = proposal_id
            self.approved = approved
            super().__init__()

    def __init__(self, proposal: SentinelProposal, **kwargs):
        super().__init__(**kwargs)
        self.proposal = proposal

    def compose(self) -> ComposeResult:
        with Horizontal(classes="proposal-buttons"):
            yield Button(
                "✓ Approve", id=f"approve_{self.proposal.id}", variant="success"
            )
            yield Button("✗ Reject", id=f"reject_{self.proposal.id}", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id.startswith("approve_"):
            self.post_message(self.Decided(self.proposal.id, approved=True))
        elif event.button.id.startswith("reject_"):
            self.post_message(self.Decided(self.proposal.id, approved=False))

    def render(self) -> Panel:
        p = self.proposal

        if not p.is_valid():
            status_style = {
                ProposalStatus.APPROVED: "green",
                ProposalStatus.REJECTED: "red",
                ProposalStatus.EXPIRED: "dim",
            }.get(p.status, "dim")
            return Panel(
                f"[{status_style}]#{p.id} - {p.status.value.upper()}[/{status_style}]",
                border_style="dim",
            )

        remaining = p.time_remaining()
        mins, secs = divmod(int(remaining.total_seconds()), 60)
        timer_color = "green" if mins > 0 else ("yellow" if secs > 30 else "red blink")

        ms = p.market_snapshot
        market_info = f"{ms.question[:45]}..." if ms else "Unknown market"
        price_info = f"Bid ${ms.best_bid:.2f} | Ask ${ms.best_ask:.2f}" if ms else ""

        content = f"""[bold cyan]{p.trigger_description}[/bold cyan]

[dim]{market_info}[/dim]
{price_info}

{p.risk_summary}

[bold yellow]→ {p.suggested_side}[/bold yellow] [dim](you decide size)[/dim]

[{timer_color}]⏱ {mins}:{secs:02d}[/{timer_color}]"""

        return Panel(content, title=f"Proposal #{p.id}", border_style="cyan")


# =============================================================================
# Main Sentinel Panel
# =============================================================================


class SentinelPanel(Static):
    """Main Sentinel control panel."""

    BINDINGS = [
        Binding("?", "show_help", "Help"),
        Binding("a", "approve_first", "Approve"),
        Binding("r", "reject_first", "Reject"),
    ]

    # Reactive state
    sentinel_running: reactive[bool] = reactive(False)
    selected_market_id: reactive[str] = reactive("")
    selected_market_question: reactive[str] = reactive("")

    def __init__(
        self,
        risk_guard: Any = None,
        get_market_state: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._risk_guard = risk_guard
        self._get_market_state = get_market_state
        self._sentinel: Optional[SentinelAgent] = None
        self._proposals: List[SentinelProposal] = []
        self._config: Optional[SentinelConfig] = None
        self._watched_markets: List[WatchedMarket] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="sentinel-main"):
            # Header with help button
            with Horizontal(classes="sentinel-header"):
                yield Label(
                    "[bold cyan]🔭 SENTINEL[/bold cyan]", classes="sentinel-title"
                )
                yield Static("", classes="spacer")
                yield Button("?", id="help-btn", classes="help-button")

            yield Static(
                "[dim]Watch markets. Get alerts. You decide.[/dim]",
                classes="sentinel-tagline",
            )

            yield Rule()

            # Status section
            with Horizontal(classes="status-bar"):
                yield Static("Status:", classes="status-label")
                yield Static("[yellow]● Stopped[/yellow]", id="status-indicator")
                yield Static("", classes="spacer")
                yield Static("Watching:", classes="status-label")
                yield Static("0 markets", id="watch-count")

            # Control buttons
            with Horizontal(classes="control-buttons"):
                yield Button("▶ Start", id="start-btn", variant="success")
                yield Button("■ Stop", id="stop-btn", variant="error", disabled=True)
                yield Button("⚙ Config", id="config-btn", variant="default")

            yield Rule()

            # Add Watch section
            yield Label("[bold]Add Watch[/bold]", classes="section-label")

            # Selected market display
            with Horizontal(classes="selected-market"):
                yield Static("Selected:", classes="field-label")
                yield Static(
                    "[dim]← Select a market from the list[/dim]",
                    id="selected-market-display",
                )

            # Trigger configuration
            with Horizontal(classes="trigger-row"):
                yield Label("When", classes="trigger-label")
                yield Select(
                    [
                        ("price_below", "Price drops below"),
                        ("price_above", "Price rises above"),
                        ("spread_above", "Spread widens above"),
                        ("spread_below", "Spread narrows below"),
                    ],
                    id="trigger-type",
                    prompt="condition...",
                )
                yield Input(
                    placeholder="0.45", id="threshold-input", classes="threshold-field"
                )
                yield Label("then suggest", classes="trigger-label")
                yield Select(
                    [("BUY", "BUY"), ("SELL", "SELL")],
                    id="side-select",
                    prompt="side",
                )

            yield Button(
                "+ Add Watch", id="add-watch-btn", variant="primary", classes="add-btn"
            )

            yield Rule()

            # Watched markets table
            yield Label("[bold]Watched Markets[/bold]", classes="section-label")
            yield DataTable(id="watched-table", classes="watched-table")

            yield Rule()

            # Proposals section
            yield Label("[bold]Proposals[/bold]", classes="section-label")
            with ScrollableContainer(
                id="proposals-area", classes="proposals-container"
            ):
                yield Static(
                    "[dim]No proposals yet.\nAdd markets and start Sentinel.[/dim]",
                    id="no-proposals-msg",
                )

    def on_mount(self) -> None:
        # Setup watched markets table
        table = self.query_one("#watched-table", DataTable)
        table.add_columns("Market", "Trigger", "Side", "")
        table.cursor_type = "row"

        # Start refresh timer
        self.set_interval(1, self._refresh_ui)

    def _refresh_ui(self) -> None:
        """Periodic UI refresh."""
        if self._sentinel:
            self._proposals = self._sentinel.get_pending_proposals()
            self._update_proposals_display()

    # =========================================================================
    # Market Selection (called from parent DashboardApp)
    # =========================================================================

    def set_selected_market(
        self, market_id: str, question: str, provider: str = "polymarket"
    ) -> None:
        """Called when user selects a market in the market list."""
        self.selected_market_id = market_id
        self.selected_market_question = question
        self._selected_provider = provider

        # Update display
        display = self.query_one("#selected-market-display", Static)
        short_q = question[:50] + "..." if len(question) > 50 else question
        display.update(f"[bold]{short_q}[/bold]")

    # =========================================================================
    # UI Updates
    # =========================================================================

    def _update_status(self) -> None:
        indicator = self.query_one("#status-indicator", Static)
        start_btn = self.query_one("#start-btn", Button)
        stop_btn = self.query_one("#stop-btn", Button)
        watch_count = self.query_one("#watch-count", Static)

        if self.sentinel_running:
            indicator.update("[bold green]● Running[/bold green]")
            start_btn.disabled = True
            stop_btn.disabled = False
        else:
            indicator.update("[yellow]● Stopped[/yellow]")
            start_btn.disabled = False
            stop_btn.disabled = True

        watch_count.update(f"{len(self._watched_markets)} markets")

    def _update_watched_table(self) -> None:
        table = self.query_one("#watched-table", DataTable)
        table.clear()

        for wm in self._watched_markets:
            for trigger in wm.triggers:
                short_market = wm.market_id[:16] + "..."
                trigger_str = f"{trigger.trigger_type.value} {trigger.threshold}"
                table.add_row(short_market, trigger_str, trigger.suggested_side, "🗑")

    def _update_proposals_display(self) -> None:
        container = self.query_one("#proposals-area", ScrollableContainer)
        no_msg = self.query_one("#no-proposals-msg", Static)

        if not self._proposals:
            no_msg.display = True
            for widget in container.query(ProposalWidget):
                widget.remove()
        else:
            no_msg.display = False
            existing = {w.proposal.id for w in container.query(ProposalWidget)}

            for proposal in self._proposals:
                if proposal.id not in existing:
                    container.mount(ProposalWidget(proposal))

    def watch_sentinel_running(self) -> None:
        self._update_status()

    # =========================================================================
    # Button Handlers
    # =========================================================================

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id == "help-btn":
            self.app.push_screen(HelpModal())

        elif btn_id == "start-btn":
            await self._start_sentinel()

        elif btn_id == "stop-btn":
            await self._stop_sentinel()

        elif btn_id == "config-btn":
            self._show_config()

        elif btn_id == "add-watch-btn":
            self._add_watch()

    def _add_watch(self) -> None:
        """Add current market with trigger to watch list."""
        if not self.selected_market_id:
            self.notify("Select a market from the list first", severity="warning")
            return

        trigger_select = self.query_one("#trigger-type", Select)
        threshold_input = self.query_one("#threshold-input", Input)
        side_select = self.query_one("#side-select", Select)

        if trigger_select.value is Select.BLANK:
            self.notify("Select a trigger condition", severity="warning")
            return

        if not threshold_input.value:
            self.notify("Enter a threshold value", severity="warning")
            return

        if side_select.value is Select.BLANK:
            self.notify("Select BUY or SELL", severity="warning")
            return

        try:
            threshold = Decimal(threshold_input.value)
        except Exception:
            self.notify("Invalid threshold number", severity="error")
            return

        # Create trigger
        trigger = TriggerCondition(
            trigger_type=TriggerType(trigger_select.value),
            threshold=threshold,
            suggested_side=side_select.value,
        )

        # Check if market already watched
        existing = next(
            (
                wm
                for wm in self._watched_markets
                if wm.market_id == self.selected_market_id
            ),
            None,
        )

        if existing:
            # Add trigger to existing market
            new_triggers = list(existing.triggers) + [trigger]
            self._watched_markets.remove(existing)
            self._watched_markets.append(
                WatchedMarket.create(
                    market_id=existing.market_id,
                    provider=existing.provider,
                    triggers=new_triggers,
                )
            )
        else:
            # New watched market
            self._watched_markets.append(
                WatchedMarket.create(
                    market_id=self.selected_market_id,
                    provider=getattr(self, "_selected_provider", "polymarket"),
                    triggers=[trigger],
                )
            )

        # Update config
        self._rebuild_config()

        # Clear inputs
        threshold_input.value = ""

        # Update UI
        self._update_watched_table()
        self._update_status()

        self.notify(
            f"Added watch: {trigger.trigger_type.value} {threshold}",
            severity="information",
        )

    def _rebuild_config(self) -> None:
        """Rebuild config from watched markets."""
        self._config = SentinelConfig.create(
            watched_markets=self._watched_markets,
            global_cooldown_seconds=self._config.global_cooldown_seconds
            if self._config
            else 60,
            max_proposals_per_hour=self._config.max_proposals_per_hour
            if self._config
            else 10,
        )

    def _show_config(self) -> None:
        """Show configuration modal."""

        def handle_config(new_config: Optional[SentinelConfig]) -> None:
            if new_config:
                self._config = new_config
                self.notify("Configuration saved", severity="information")

        self.app.push_screen(ConfigModal(self._config), handle_config)

    async def _start_sentinel(self) -> None:
        """Start the Sentinel agent."""
        if not self._watched_markets:
            self.notify("Add at least one market to watch first", severity="warning")
            return

        self._rebuild_config()

        self._sentinel = SentinelAgent(
            config=self._config,
            risk_guard=self._risk_guard,
            get_market_state=self._get_market_state,
            on_proposal=self._on_proposal,
        )

        await self._sentinel.start()
        self.sentinel_running = True
        self.notify("Sentinel is now watching your markets", severity="information")

    async def _stop_sentinel(self) -> None:
        """Stop the Sentinel agent."""
        if self._sentinel:
            await self._sentinel.stop()
            self._sentinel = None
        self.sentinel_running = False
        self.notify("Sentinel stopped", severity="warning")

    def _on_proposal(self, proposal: SentinelProposal) -> None:
        """Called when Sentinel generates a proposal."""
        self.notify(
            f"🔔 {proposal.trigger_description}",
            severity="information",
            timeout=15,
        )
        self._refresh_ui()

    # =========================================================================
    # Proposal Handling
    # =========================================================================

    async def on_proposal_widget_decided(self, event: ProposalWidget.Decided) -> None:
        if not self._sentinel:
            return

        if event.approved:
            proposal = self._sentinel.approve_proposal(event.proposal_id)
            if proposal:
                self.notify(
                    f"✓ Approved #{event.proposal_id} - Execute your {proposal.suggested_side}!",
                    severity="information",
                )
        else:
            self._sentinel.reject_proposal(event.proposal_id)
            self.notify(f"✗ Rejected #{event.proposal_id}", severity="warning")

        self._refresh_ui()

    def action_show_help(self) -> None:
        """Show help modal."""
        self.app.push_screen(HelpModal())

    def action_approve_first(self) -> None:
        """Keyboard shortcut to approve first proposal."""
        if self._proposals:
            asyncio.create_task(
                self.on_proposal_widget_decided(
                    ProposalWidget.Decided(self._proposals[0].id, approved=True)
                )
            )

    def action_reject_first(self) -> None:
        """Keyboard shortcut to reject first proposal."""
        if self._proposals:
            asyncio.create_task(
                self.on_proposal_widget_decided(
                    ProposalWidget.Decided(self._proposals[0].id, approved=False)
                )
            )
