"""Agent status panel for Bloomberg-style terminal display"""
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from typing import Dict, Optional
import json
import asyncio
from datetime import datetime
from rich.table import Table


class AgentStatusPanel(Static):
    """Compact agent monitoring panel with status, tasks, and health metrics"""

    def __init__(self, redis_store, id: Optional[str] = None, **kwargs):
        super().__init__(id=id, **kwargs)
        self.redis = redis_store
        self.agent_data = {}
        self.pubsub_task = None
        self.ticker_task = None
        self.last_status = {}
        self.expanded = True
        self.pulse_state = False
        self.ticker_messages = []  # Last 5 status updates

    def on_mount(self) -> None:
        """Subscribe to agent health updates on mount"""
        self.pubsub_task = asyncio.create_task(self._subscribe_agent_health())
        self.ticker_task = asyncio.create_task(self._subscribe_agent_ticker())
        self.set_interval(0.8, self._toggle_pulse)

    def _toggle_pulse(self) -> None:
        """Toggle pulse state for running agents"""
        self.pulse_state = not self.pulse_state
        self._render_agent_table()

    async def _subscribe_agent_ticker(self):
        """Subscribe to specific agent status updates for the ticker"""
        try:
            pubsub = await self.redis.subscribe("agent:status:updates")
            async for msg in pubsub.listen():
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    self.ticker_messages.insert(0, data)
                    self.ticker_messages = self.ticker_messages[:5]
                    self._render_agent_table()
        except Exception:
            pass

    async def _subscribe_agent_health(self):
        """Subscribe to Redis for real-time agent health updates"""
        try:
            pubsub = await self.redis.subscribe("agent:health")
            
            async for msg in pubsub.listen():
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    await self._update_agent(data)
        except Exception as e:
            self.update("[red]Redis subscription error: {}[/red]".format(e))

    async def _update_agent(self, data: dict) -> None:
        """Update agent data only if changed (efficient rendering)"""
        agent_id = data.get("agent_id")
        if not agent_id:
            return

        current_status = data.get("status")
        # Only rebuild if status actually changed
        if self.last_status.get(agent_id) != current_status:
            self.agent_data[agent_id] = data
            self.last_status[agent_id] = current_status
            self._render_agent_table()

    def _render_agent_table(self) -> None:
        """Render compact agent table"""
        if not self.agent_data:
            self.update("[dim]No agents registered[/dim]")
            return

        table = Table(show_header=True, expand=True)
        table.add_column("AGT", width=3, justify="left")
        table.add_column("STS", width=3, justify="center")
        table.add_column("TASK", width=20, justify="left")

        # Sort: RUNNING first, then IDLE, then ERROR, then STOPPED
        status_order = {"RUNNING": 0, "IDLE": 1, "ERROR": 2, "STOPPED": 3}
        sorted_agents = sorted(
            self.agent_data.items(),
            key=lambda x: status_order.get(x[1].get("status", "STOPPED"), 3)
        )

        for agent_id, data in sorted_agents:
            status = data.get("status", "UNKNOWN")
            icon = self._get_status_icon(status)
            queue_depth = data.get("queue_depth") or 0
            task_str = data.get("current_task", f"Queue: {queue_depth}")
            
            # Color code based on status
            color = self._get_status_color(status)
            table.add_row(
                "[{0}]{1}[/{0}]".format(color, self._shorten_id(agent_id)),
                "[{0}]{1}[/{0}]".format(color, icon),
                "[{0}]{1}[/{0}]".format(color, str(task_str)[:20])
            )

        # Build panel content
        content_str = self._table_to_string(table)
        
        # Add Live Ticker
        ticker_str = "\n[bold cyan]─ LIVE TICKER ─[/bold cyan]\n"
        if not self.ticker_messages:
            ticker_str += "[dim]Waiting for updates...[/dim]"
        else:
            for msg in self.ticker_messages:
                ts = datetime.fromtimestamp(msg.get("timestamp", 0)).strftime("%H:%M:%S")
                agent = self._shorten_id(msg.get("agent_id", "???"))
                text = msg.get("message", "")[:25]
                ticker_str += f"[dim]{ts}[/dim] [cyan]{agent}:[/cyan] {text}\n"

        # Add hide/expand button
        hide_text = "[-] Hide" if self.expanded else "[+] Expand"
        
        full_content = content_str + ticker_str + "\n" + hide_text
        self.update(full_content)

    def _table_to_string(self, table) -> str:
        """Convert table to string for rendering"""
        from rich.console import Console
        console = Console()
        with console.capture() as capture:
            console.print(table)
        return capture.get()

    def _get_status_icon(self, status: str) -> str:
        """Get icon for status"""
        if status == "RUNNING":
            return "●" if self.pulse_state else "○"
        
        icons = {
            "IDLE": "○",
            "ERROR": "✗",
            "STOPPED": "■",
        }
        return icons.get(status, "?")

    def _get_status_color(self, status: str) -> str:
        """Get color for status"""
        colors = {
            "RUNNING": "green",
            "IDLE": "yellow",
            "ERROR": "red",
            "STOPPED": "gray",
        }
        return colors.get(status, "white")

    def _shorten_id(self, agent_id: str) -> str:
        """Shorten agent ID for compact display"""
        abbreviations = {
            "market_observer": "OBS",
            "alert_manager": "ALT",
            "risk_manager": "RSC",
            "execution_agent": "EXE",
            "supervisor": "SUP",
            "arb_scout": "ARB",
            "researcher": "RSC",
        }
        return abbreviations.get(agent_id, agent_id[:3].upper())

    def toggle_expanded(self) -> None:
        """Toggle panel visibility"""
        self.expanded = not self.expanded
        self._render_agent_table()

    def get_agent_data(self, agent_id: str) -> Optional[dict]:
        """Get data for specific agent (for click handlers)"""
        return self.agent_data.get(agent_id)

    async def on_unmount(self) -> None:
        """Clean up Redis subscription on unmount"""
        if self.pubsub_task:
            self.pubsub_task.cancel()
        if self.ticker_task:
            self.ticker_task.cancel()
