import asyncio
import json
from datetime import datetime
from textual.widgets import Static, TextArea
from textual.containers import Vertical

class AgentChatInterface(Static):
    """Large multi-line text input for agent interaction"""

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
            yield Static(id="conversation_display", classes="conversation-box")
            
            yield TextArea(
                id="chat_input",
                classes="chat-input",
                show_line_numbers=False
            )

    def on_mount(self) -> None:
        """Subscribe to command results on mount"""
        self.pubsub_task = asyncio.create_task(self._subscribe_command_results())
        self._show_prompt()

    async def _subscribe_command_results(self):
        """Subscribe to Redis for command execution results"""
        try:
            pubsub = await self.redis.subscribe("command:results")
            
            async for msg in pubsub.listen():
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    if self.showing_history:
                        return
                    self._add_conversation_message("agent", data.get("result", "Command processed"))
        except Exception as e:
            pass

    def _show_prompt(self) -> None:
        """Show conversation or prompt based on mode"""
        if not self.conversation_history and not self.showing_history:
            self.update("[dim italic]> Type natural language commands or questions to interact with agents...[/dim italic]")
        else:
            content = self._format_conversation()
            self.update(content)

    def _format_conversation(self) -> str:
        """Format conversation as text"""
        lines = []
        if self.showing_history:
            lines.append("[bold blue]=== AGENT TASK HISTORY ===[/bold blue]")
        
        for msg in self.conversation_history[-50:]:
            timestamp = datetime.fromtimestamp(msg.get("timestamp", 0)).strftime("%H:%M:%S")
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "user":
                line = "[dim]{}[/dim] [bold cyan]>[/bold cyan] {}".format(timestamp, content)
            else:
                line = "[dim]{}[/dim] [bold green]<[/bold green] {}".format(timestamp, content)
            
            lines.append(line)
        
        return "\n".join(lines)

    def _add_conversation_message(self, role, content) -> None:
        """Add message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().timestamp()
        })
        self._show_prompt()

    def _append_to_display(self, text) -> None:
        """Append text directly to current display"""
        display = self.query_one("#conversation_display")
        if display:
            current = display.renderable
            if current:
                self.update(str(current) + "\n" + text)
        else:
            self.update(text)

    async def on_key(self, event) -> None:
        """Handle keyboard navigation"""
        if event.key == "escape":
            if self.showing_history:
                self.return_to_chat()

    def on_button_press(self, event) -> None:
        """Handle button presses"""
        if event.button.id == "send":
            self._send_input()

    def _send_input(self) -> None:
        """Send current input to supervisor"""
        text_area = self.query_one("#chat_input")
        if text_area:
            input_text = str(text_area.text).strip()
            if not input_text:
                return

            if input_text not in self.input_history:
                self.input_history.append(input_text)
            self.history_index = len(self.input_history)
            
            self._add_conversation_message("user", input_text)
            text_area.text = ""
            
            asyncio.create_task(self._route_command(input_text))

    async def _route_command(self, input_text):
        """Parse and route command to supervisor"""
        try:
            result = await self.supervisor.route_command(
                command="CHAT",
                args={"input": input_text, "agent_id": self.current_agent}
            )
            
            if result:
                self._add_conversation_message("agent", result.get("result", "Command processed"))
            else:
                self._append_to_display("[red]Command error: Supervisor not available[/red]")
        except Exception as e:
            self._append_to_display(f"[red]Error: {str(e)}[/red]")

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
