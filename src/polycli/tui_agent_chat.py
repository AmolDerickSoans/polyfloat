import asyncio
import json
import os
from datetime import datetime
from textual.widgets import Static, Input, Collapsible
from textual.containers import Vertical, Container, VerticalScroll
from textual.binding import Binding
from textual import events
from rich.table import Table


class AgentChatInterface(Container):
    """Single-line text input for agent interaction"""
    
    can_focus = True

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

    def compose(self):
        """Compose chat interface"""
        with Vertical(id="chat_container"):
            with VerticalScroll(id="conversation_scroll"):
                yield Static("[dim italic]> Type natural language commands... (Enter to send)[/dim italic]", id="initial_prompt")
            
            yield Input(
                id="chat_input",
                classes="chat-input",
                placeholder="Message Supervisor..."
            )

    def on_mount(self) -> None:
        """Subscribe to command results on mount"""
        self.pubsub_task = asyncio.create_task(self._subscribe_command_results())
        
        # Check for API Key
        if not os.environ.get("GOOGLE_API_KEY"):
            self._add_conversation_message(
                "system", 
                "[bold red]⚠️ SETUP REQUIRED:[/bold red] GOOGLE_API_KEY not found.\n"
                "Please set GOOGLE_API_KEY in your .env file or environment variables to enable agents."
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
                    if isinstance(result, dict) and result.get("strategy") == "one_best_trade":
                        self._add_trade_proposal(result)
                    else:
                        self._add_conversation_message("agent", str(result or "Command processed"))
        except Exception as e:
            pass

    def _add_trade_proposal(self, proposal: dict) -> None:
        """Render a trade proposal card using Collapsible and Table"""
        self._remove_thinking_block()
        market = proposal.get("question", "Unknown Market")
        plan = proposal.get("trade_plan", "No details")
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold yellow]Market:[/bold yellow]", market)
        table.add_row("[bold yellow]Proposal:[/bold yellow]", plan)
        table.add_row("[bold cyan]Action:[/bold cyan]", "Press A to Approve or C to Cancel")
        
        collapsible = Collapsible(
            Static(table),
            title=f"PROPOSAL: {market[:30]}...",
            collapsed=False
        )
        self.query_one("#conversation_scroll").mount(collapsible)
        collapsible.scroll_visible()

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
                Static(content),
                title=f"AGENT ({timestamp})",
                collapsed=False
            )
            scroll.mount(collapsible)
        else: # system
            msg = Static(f"[dim]{timestamp}[/dim] [italic yellow]{content}[/italic yellow]")
            scroll.mount(msg)
            
        scroll.scroll_end(animate=False)

    def _remove_thinking_block(self) -> None:
        """Safely remove the thinking indicator if it exists"""
        try:
            self.query_one("#thinking_block").remove()
        except Exception:
            pass

    def _append_to_display(self, text) -> None:
        """Append text directly to current display"""
        display = self.query_one("#conversation_display")
        if display:
            current = display.renderable
            if current:
                display.update(str(current) + "\n" + text)
        else:
            display.update(text)

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
                thinking = Static("[italic dim]Thinking...[/italic dim]", id="thinking_block")
                scroll.mount(thinking)
                scroll.scroll_end()
            
            asyncio.create_task(self._route_command(input_text))

    async def _route_command(self, input_text):
        """Parse and route command to supervisor"""
        try:
            result = await self.supervisor.route_command(
                command="CHAT",
                args={"input": input_text, "agent_id": self.current_agent}
            )
            
            if not result:
                self._add_conversation_message("system", "[red]Command error: Supervisor not available[/red]")
        except Exception as e:
            self._add_conversation_message("system", f"[red]Error: {str(e)}[/red]")

    def set_agent_context(self, agent_id) -> None:
        """Set which agent to talk to"""
        self.current_agent = agent_id
        if agent_id:
            self._append_to_display(f"[cyan italic]Context set to: {agent_id}[/cyan italic]")
        else:
            self._append_to_display("[cyan italic]Context: Supervisor[/cyan italic]")

    def show_agent_history(self, agent_id, tasks):
        """Show agent task history"""
        self.showing_history = True
        self.conversation_history = []
        
        self._append_to_display(f"[bold blue]=== {agent_id.upper()} - TASK HISTORY ===[/bold blue]")
        
        for task in tasks[-20:]:
            timestamp = datetime.fromtimestamp(task.get("timestamp", 0)).strftime("%H:%M:%S")
            task_type = task.get("task_type", "UNKNOWN")
            status = task.get("status", "UNKNOWN")
            
            status_color = {
                "SUCCESS": "green",
                "FAILED": "red",
                "PENDING": "yellow",
            }.get(status, "white")
            
            line = "[dim]{}[/dim] [{} {} [/{}/{}]".format(
                timestamp,
                status_color + status + "[/" + status_color,
                task_type
            )
            
            if task.get("result"):
                result = task.get("result", "")
                line += "\n    [dim]{}[/dim]".format(result)
            
            self.conversation_history.append({
                "role": "system",
                "content": line,
                "timestamp": task.get("timestamp", 0)
            })
            
        self._append_to_display("[dim italic]Press ESC to return to chat mode[/dim italic]")
        self._show_prompt()

    def return_to_chat(self) -> None:
        """Return from history view to chat mode"""
        self.showing_history = False
        self._show_prompt()

    async def on_unmount(self) -> None:
        """Clean up"""
        if self.pubsub_task:
            self.pubsub_task.cancel()
