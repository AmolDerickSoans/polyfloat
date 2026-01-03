import asyncio
import json
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any
from textual.widgets import Static, Input, Collapsible
from textual.containers import Vertical, Container, VerticalScroll
from textual.binding import Binding
from rich.table import Table

from polycli.telemetry import TelemetryEvent, get_session_id
from polycli.telemetry.store import TelemetryStore


PROPOSAL_TTL_SECONDS = 300  # 5 minutes


class AgentChatInterface(Container):
    """Single-line text input for agent interaction"""

    can_focus = True
    BINDINGS = [
        Binding("a", "approve_proposal", "Approve Trade"),
        Binding("c", "cancel_proposal", "Cancel Trade"),
    ]

    def __init__(self, redis_store, supervisor, **kwargs):
        super().__init__(**kwargs)
        self.redis = redis_store
        self.supervisor = supervisor
        self.conversation_history = []
        self.input_history = []
        self.history_index = 0
        self.pubsub_task = None
        self.showing_history = False
        self.current_agent = None
        self.current_proposal: Optional[Dict[str, Any]] = None
        self._proposal_widget = None

    def compose(self):
        """Compose chat interface"""
        with Vertical(id="chat_container"):
            with VerticalScroll(id="conversation_scroll"):
                yield Static(
                    "[dim italic]> Type natural language commands... (Enter to send)[/dim italic]",
                    id="initial_prompt",
                )

            yield Input(
                id="chat_input",
                classes="chat-input",
                placeholder="Message Supervisor...",
            )

    def on_mount(self) -> None:
        """Subscribe to command results on mount"""
        self.pubsub_task = asyncio.create_task(self._subscribe_command_results())

        # Check for API Key
        if not os.environ.get("GOOGLE_API_KEY"):
            self._add_conversation_message(
                "system",
                "[bold red]⚠️ SETUP REQUIRED:[/bold red] GOOGLE_API_KEY not found.\n"
                "Please set GOOGLE_API_KEY in your .env file or environment variables to enable agents.",
            )

    async def _subscribe_command_results(self):
        """Subscribe to Redis for command execution results"""
        try:
            pubsub = await self.redis.subscribe("command:results")

            async for msg in pubsub.listen():
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    if self.showing_history:
                        continue

                    # Remove "Thinking..." block if exists
                    self._remove_thinking_block()

                    result = data.get("result")

                    # Check if it's a structured trade proposal
                    if (
                        isinstance(result, dict)
                        and result.get("strategy") == "one_best_trade"
                    ):
                        self._add_trade_proposal(result)
                    else:
                        self._add_conversation_message(
                            "agent", str(result or "Command processed")
                        )
        except Exception:
            pass

    def _add_trade_proposal(self, proposal: dict) -> None:
        """Render a trade proposal card using Collapsible and Table"""
        self._remove_thinking_block()
        self.current_proposal = proposal

        market = proposal.get("question", "Unknown Market")
        plan = proposal.get("trade_plan", "No details")
        execution = proposal.get("execution", {})
        generated_at = execution.get("generated_at", time.time())
        age_seconds = time.time() - generated_at
        age_formatted = self._format_duration(age_seconds)

        is_stale = age_seconds > PROPOSAL_TTL_SECONDS
        staleness_warning = ""
        if is_stale:
            staleness_warning = f"\n[bold red]⚠ PROPOSAL STALE ({age_formatted})[/bold red]\nPrice may have changed significantly!"

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold yellow]Market:[/bold yellow]", market)
        table.add_row("[bold yellow]Proposal:[/bold yellow]", plan)
        if execution:
            side = execution.get("side", "N/A")
            amount = execution.get("amount", 0)
            token_id = (
                execution.get("token_id", "")[:20] + "..."
                if len(execution.get("token_id", "")) > 20
                else execution.get("token_id", "")
            )
            table.add_row(
                "[bold yellow]Trade:[/bold yellow]",
                f"[green]{side}[/green] ${amount:.2f} [{token_id}]",
            )
        table.add_row(
            "[bold cyan]Action:[/bold yellow]",
            f"Press A to Approve or C to Cancel{staleness_warning}",
        )

        self._proposal_widget = Collapsible(
            Static(table),
            title=f"PROPOSAL: {market[:30]}... (Age: {age_formatted})",
            collapsed=False,
        )
        self.query_one("#conversation_scroll").mount(self._proposal_widget)
        self._proposal_widget.scroll_visible()

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"

    def _is_proposal_stale(self) -> bool:
        """Check if current proposal has expired based on TTL."""
        if not self.current_proposal:
            return True
        execution = self.current_proposal.get("execution", {})
        if not execution:
            return True
        generated_at = execution.get("generated_at")
        if not generated_at:
            return True
        return (time.time() - generated_at) > PROPOSAL_TTL_SECONDS

    def _add_conversation_message(self, role, content) -> None:
        """Add message to conversation history and mount widget"""
        self._remove_thinking_block()
        scroll = self.query_one("#conversation_scroll")

        # Remove initial prompt if it's the first message
        try:
            self.query_one("#initial_prompt").remove()
        except Exception:
            pass

        timestamp = datetime.now().strftime("%H:%M:%S")

        if role == "user":
            msg = Static(f"[dim]{timestamp}[/dim] [bold cyan]>[/bold cyan] {content}")
            scroll.mount(msg)
        elif role == "agent":
            collapsible = Collapsible(
                Static(content), title=f"AGENT ({timestamp})", collapsed=False
            )
            scroll.mount(collapsible)
        else:  # system
            msg = Static(
                f"[dim]{timestamp}[/dim] [italic yellow]{content}[/italic yellow]"
            )
            scroll.mount(msg)

        scroll.scroll_end(animate=False)

    def _remove_thinking_block(self) -> None:
        """Safely remove the thinking indicator if it exists"""
        try:
            self.query_one("#thinking_block").remove()
        except Exception:
            pass

    def _append_to_display(self, text) -> None:
        """Append text directly to current display."""
        try:
            scroll = self.query_one("#conversation_scroll")
            msg = Static(text)
            scroll.mount(msg)
            scroll.scroll_end()
        except Exception:
            pass

    async def on_key(self, event) -> None:
        """Handle keyboard navigation"""
        if event.key == "escape":
            if self.showing_history:
                self.return_to_chat()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key submission from Input widget"""
        self.action_submit_chat()

    def action_submit_chat(self) -> None:
        """Send current input to supervisor"""
        chat_input = self.query_one("#chat_input", Input)
        if chat_input:
            input_text = str(chat_input.value).strip()
            if not input_text:
                return

            if input_text not in self.input_history:
                self.input_history.append(input_text)
            self.history_index = len(self.input_history)

            self._add_conversation_message("user", input_text)
            chat_input.value = ""

            # Add "Thinking..." block (only if not already there)
            scroll = self.query_one("#conversation_scroll")
            if not self.query("#thinking_block"):
                thinking = Static(
                    "[italic dim]Thinking...[/italic dim]", id="thinking_block"
                )
                scroll.mount(thinking)
                scroll.scroll_end()

            asyncio.create_task(self._route_command(input_text))

    async def _route_command(self, input_text):
        """Parse and route command to supervisor"""
        try:
            result = await self.supervisor.route_command(
                command="CHAT",
                args={"input": input_text, "agent_id": self.current_agent},
            )

            if not result:
                self._add_conversation_message(
                    "system", "[red]Command error: Supervisor not available[/red]"
                )
        except Exception as e:
            self._add_conversation_message("system", f"[red]Error: {str(e)}[/red]")

    def set_agent_context(self, agent_id) -> None:
        """Set which agent to talk to"""
        self.current_agent = agent_id
        if agent_id:
            self._append_to_display(
                f"[cyan italic]Context set to: {agent_id}[/cyan italic]"
            )
        else:
            self._append_to_display("[cyan italic]Context: Supervisor[/cyan italic]")

    def show_agent_history(self, agent_id, tasks):
        """Show agent task history"""
        self.showing_history = True
        self.conversation_history = []

        self._append_to_display(
            f"[bold blue]=== {agent_id.upper()} - TASK HISTORY ===[/bold blue]"
        )

        for task in tasks[-20:]:
            timestamp = datetime.fromtimestamp(task.get("timestamp", 0)).strftime(
                "%H:%M:%S"
            )
            task_type = task.get("task_type", "UNKNOWN")
            status = task.get("status", "UNKNOWN")

            status_color = {
                "SUCCESS": "green",
                "FAILED": "red",
                "PENDING": "yellow",
            }.get(status, "white")

            line = "[dim]{}[/dim] [{} {} [/{}/{}]]".format(
                timestamp, status_color, status, status_color, task_type
            )

            if task.get("result"):
                result = task.get("result", "")
                line += "\n    [dim]{}[/dim]".format(result)

            self.conversation_history.append(
                {
                    "role": "system",
                    "content": line,
                    "timestamp": task.get("timestamp", 0),
                }
            )

        self._append_to_display(
            "[dim italic]Press ESC to return to chat mode[/dim italic]"
        )
        self._show_prompt()

    def return_to_chat(self) -> None:
        """Return from history view to chat mode"""
        self.showing_history = False
        self._show_prompt()

    async def on_unmount(self) -> None:
        """Clean up"""
        if self.pubsub_task:
            self.pubsub_task.cancel()

    def _show_prompt(self) -> None:
        """Show or update the chat input prompt."""
        try:
            chat_input = self.query_one("#chat_input", Input)
            chat_input.focus()
        except Exception:
            pass

    def _clear_proposal(self) -> None:
        """Clear the current proposal and remove the widget."""
        self.current_proposal = None
        if self._proposal_widget:
            try:
                self._proposal_widget.remove()
            except Exception:
                pass
            self._proposal_widget = None

    def _emit_proposal_approved_event(
        self,
        proposal_age_seconds: float,
        market_id: str,
        was_stale: bool,
    ) -> None:
        """Emit proposal_approved telemetry event."""
        try:
            store = TelemetryStore()
            if store.enabled:
                event = TelemetryEvent(
                    event_type="proposal_approved",
                    timestamp=time.time(),
                    session_id=get_session_id(),
                    payload={
                        "proposal_age_seconds": round(proposal_age_seconds, 2),
                        "market_id": market_id,
                        "was_stale": was_stale,
                    },
                )
                store.emit(event)
        except Exception:
            pass

    def _emit_proposal_rejected_event(
        self,
        proposal_age_seconds: float,
        market_id: str,
        was_stale: bool,
    ) -> None:
        """Emit proposal_rejected telemetry event."""
        try:
            store = TelemetryStore()
            if store.enabled:
                event = TelemetryEvent(
                    event_type="proposal_rejected",
                    timestamp=time.time(),
                    session_id=get_session_id(),
                    payload={
                        "proposal_age_seconds": round(proposal_age_seconds, 2),
                        "market_id": market_id,
                        "was_stale": was_stale,
                    },
                )
                store.emit(event)
        except Exception:
            pass

    async def action_approve_proposal(self) -> None:
        """Handle 'A' key press - approve and execute the trade proposal."""
        if not self.current_proposal:
            self._add_conversation_message(
                "system", "[yellow]No active proposal to approve[/yellow]"
            )
            return

        if self._is_proposal_stale():
            self._add_conversation_message(
                "system",
                "[bold red]⚠ Cannot execute: Proposal is stale (older than 5 minutes)[/bold red]\n"
                "Please request a new trade proposal.",
            )
            self._clear_proposal()
            return

        execution = self.current_proposal.get("execution", {})
        token_id = execution.get("token_id")
        side = execution.get("side", "BUY")
        amount = execution.get("amount", 0)
        provider = execution.get("provider", "polymarket")

        if not token_id:
            self._add_conversation_message(
                "system", "[red]Error: No token_id in proposal[/red]"
            )
            return

        self._add_conversation_message(
            "system",
            f"[bold cyan]Executing:[/bold cyan] {side} ${amount:.2f} on {provider}...",
        )

        execution = self.current_proposal.get("execution", {})
        generated_at = execution.get("generated_at", time.time())
        proposal_age_seconds = time.time() - generated_at
        market_id = (
            (execution.get("token_id", "")[:12] + "...")
            if len(execution.get("token_id", "")) > 12
            else execution.get("token_id", "")
        )
        was_stale = self._is_proposal_stale()

        try:
            if side == "BUY":
                result = await self.supervisor.trader.place_market_buy(
                    token_id=token_id,
                    amount=amount,
                    provider=provider,
                    agent_id="trader",
                    agent_reasoning=self.current_proposal.get("trade_plan", ""),
                )
            else:
                result = await self.supervisor.trader.place_market_sell(
                    token_id=token_id,
                    shares=amount,
                    provider=provider,
                    agent_id="trader",
                    agent_reasoning=self.current_proposal.get("trade_plan", ""),
                )

            if result.get("success"):
                order_id = result.get("order_id", "unknown")[:12]
                self._emit_proposal_approved_event(
                    proposal_age_seconds=proposal_age_seconds,
                    market_id=market_id,
                    was_stale=was_stale,
                )
                self._add_conversation_message(
                    "system",
                    f"[bold green]✅ Order Executed![/bold green]\n"
                    f"ID: {order_id} | {side} ${amount:.2f}",
                )
            else:
                self._emit_proposal_rejected_event(
                    proposal_age_seconds=proposal_age_seconds,
                    market_id=market_id,
                    was_stale=was_stale,
                )
                error_msg = result.get("error", "Unknown error")
                self._add_conversation_message(
                    "system",
                    f"[bold red]❌ Execution Failed[/bold red]\n{error_msg}",
                )
        except Exception as e:
            self._add_conversation_message(
                "system", f"[bold red]❌ Error during execution[/bold red]\n{str(e)}"
            )

        self._clear_proposal()

    def action_cancel_proposal(self) -> None:
        """Handle 'C' key press - cancel the trade proposal."""
        if not self.current_proposal:
            self._add_conversation_message(
                "system", "[yellow]No active proposal to cancel[/yellow]"
            )
            return

        execution = self.current_proposal.get("execution", {})
        generated_at = execution.get("generated_at", time.time())
        proposal_age_seconds = time.time() - generated_at
        market_id = (
            (execution.get("token_id", "")[:12] + "...")
            if len(execution.get("token_id", "")) > 12
            else execution.get("token_id", "")
        )
        was_stale = self._is_proposal_stale()

        self._emit_proposal_rejected_event(
            proposal_age_seconds=proposal_age_seconds,
            market_id=market_id,
            was_stale=was_stale,
        )

        self._add_conversation_message("system", "[dim]Proposal cancelled[/dim]")
        self._clear_proposal()
