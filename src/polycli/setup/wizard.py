"""Main setup wizard TUI application."""
from pathlib import Path
from typing import Optional
from datetime import datetime
import yaml

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Header, Input, Label, 
    ProgressBar, RadioButton, RadioSet, Static, Switch
)
import structlog

from .models import SetupState, SetupStepStatus
from .validators import PolymarketValidator, KalshiValidator, NewsApiValidator, GoogleValidator

logger = structlog.get_logger()


class SetupWizard(App):
    """Interactive setup wizard application."""
    
    CSS = """
    Screen {
        align: center middle;
    }
    
    #wizard-container {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    
    #step-title {
        text-align: center;
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    
    #step-indicator {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    
    .input-label {
        margin-top: 1;
        color: $text;
    }
    
    .input-field {
        margin-bottom: 1;
    }
    
    .hint-text {
        color: $text-muted;
        text-style: italic;
    }
    
    #button-row {
        margin-top: 2;
        align: center middle;
    }
    
    #button-row Button {
        margin: 0 1;
    }
    
    .success-text {
        color: $success;
    }
    
    .error-text {
        color: $error;
    }
    
    .warning-text {
        color: $warning;
    }
    
    #progress-container {
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        Binding("escape", "quit", "Exit"),
        Binding("ctrl+s", "skip", "Skip Step"),
    ]
    
    CONFIG_PATH = Path.home() / ".polycli" / "config.yaml"
    
    def __init__(self):
        super().__init__()
        self.state = self._load_state()
        self.steps = [
            "welcome",
            "polymarket",
            "kalshi",
            "newsapi",
            "google",
            "agent_config",
            "validation",
            "complete"
        ]
    
    def _load_state(self) -> SetupState:
        """Load existing state or create new."""
        if self.CONFIG_PATH.exists():
            try:
                with open(self.CONFIG_PATH) as f:
                    data = yaml.safe_load(f) or {}
                return SetupState.from_config_dict(data)
            except Exception as e:
                logger.warning("Failed to load existing config", error=str(e))
        return SetupState()
    
    def _save_state(self) -> None:
        """Save state to config file."""
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.CONFIG_PATH, "w") as f:
            yaml.dump(self.state.to_config_dict(), f, default_flow_style=False)
        
        # Set restrictive permissions
        self.CONFIG_PATH.chmod(0o600)
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            self._get_current_step_widget(),
            id="wizard-container"
        )
        yield Footer()
    
    def _get_current_step_widget(self) -> Container:
        """Get widget for current step."""
        step = self.steps[self.state.current_step]
        
        if step == "welcome":
            return WelcomeStepWidget()
        elif step == "polymarket":
            return PolymarketStepWidget(self.state)
        elif step == "kalshi":
            return KalshiStepWidget(self.state)
        elif step == "newsapi":
            return NewsApiStepWidget(self.state)
        elif step == "google":
            return GoogleStepWidget(self.state)
        elif step == "agent_config":
            return AgentConfigStepWidget(self.state)
        elif step == "validation":
            return ValidationStepWidget(self.state)
        else:
            return CompleteStepWidget(self.state)
    
    async def action_next(self) -> None:
        """Move to next step."""
        if self.state.current_step < len(self.steps) - 1:
            self.state.current_step += 1
            self._save_state()
            await self.refresh_step()
    
    async def action_back(self) -> None:
        """Move to previous step."""
        if self.state.current_step > 0:
            self.state.current_step -= 1
            await self.refresh_step()
    
    async def action_skip(self) -> None:
        """Skip current step."""
        step = self.steps[self.state.current_step]
        self.state.step_statuses[step] = SetupStepStatus.SKIPPED
        await self.action_next()
    
    async def refresh_step(self) -> None:
        """Refresh the current step display."""
        container = self.query_one("#wizard-container")
        await container.remove_children()
        container.mount(self._get_current_step_widget())


class WelcomeStepWidget(Container):
    """Welcome step widget."""
    
    def compose(self) -> ComposeResult:
        yield Static("Welcome to PolyCLI", id="step-title")
        yield Static("Step 1 of 8", id="step-indicator")
        yield Static(
            "\n"
            "This wizard will help you configure PolyCLI for prediction market trading.\n\n"
            "You'll set up:\n"
            "  • Polymarket connection (required)\n"
            "  • Kalshi connection (optional)\n"
            "  • News APIs for market intelligence (optional)\n"
            "  • Google Gemini for AI agents (optional)\n"
            "  • Agent behavior preferences\n\n"
            "Your credentials are stored securely in ~/.polycli/config.yaml\n"
            "with restricted file permissions (600).\n",
            id="welcome-text"
        )
        yield Static(
            "[dim]Press Enter to continue, Escape to exit[/dim]",
            classes="hint-text"
        )
        yield Horizontal(
            Button("Get Started", variant="primary", id="next-btn"),
            id="button-row"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next-btn":
            self.app.call_later(self.app.action_next)


class PolymarketStepWidget(Container):
    """Polymarket configuration step."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("Polymarket Setup", id="step-title")
        yield Static("Step 2 of 8 (Required)", id="step-indicator")
        
        yield Label("Private Key:", classes="input-label")
        yield Input(
            placeholder="0x... (64 hex characters)",
            password=True,
            value=self.state.polymarket_private_key,
            id="private-key-input",
            classes="input-field"
        )
        yield Static(
            "[dim]Your Ethereum wallet private key. Get this from MetaMask or your wallet provider.[/dim]",
            classes="hint-text"
        )
        
        yield Label("Funder Address:", classes="input-label")
        yield Input(
            placeholder="0x... (your wallet address)",
            value=self.state.polymarket_funder_address,
            id="funder-input",
            classes="input-field"
        )
        
        yield Label("Wallet Type:", classes="input-label")
        yield RadioSet(
            RadioButton("EOA (MetaMask, etc.)", id="eoa", value=self.state.polymarket_signature_type == 0),
            RadioButton("Gnosis Safe", id="safe", value=self.state.polymarket_signature_type == 1),
            id="wallet-type"
        )
        
        yield Static("", id="validation-result")
        
        yield Horizontal(
            Button("Back", variant="default", id="back-btn"),
            Button("Test Connection", variant="warning", id="test-btn"),
            Button("Next", variant="primary", id="next-btn"),
            id="button-row"
        )
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            await self.app.action_back()
        elif event.button.id == "test-btn":
            await self._test_connection()
        elif event.button.id == "next-btn":
            if await self._validate_and_save():
                await self.app.action_next()
    
    async def _test_connection(self) -> None:
        """Test Polymarket connection."""
        result_widget = self.query_one("#validation-result")
        result_widget.update("[yellow]Testing connection...[/yellow]")
        
        private_key = self.query_one("#private-key-input", Input).value
        funder = self.query_one("#funder-input", Input).value
        sig_type = 0 if self.query_one("#eoa", RadioButton).value else 1
        
        # Validate format first
        valid, msg = PolymarketValidator.validate_private_key(private_key)
        if not valid:
            result_widget.update(f"[red]{msg}[/red]")
            return
        
        valid, msg = PolymarketValidator.validate_address(funder)
        if not valid:
            result_widget.update(f"[red]{msg}[/red]")
            return
        
        # Test actual connection
        success, message = await PolymarketValidator.test_connection(private_key, funder, sig_type)
        
        if success:
            result_widget.update(f"[green]✓ {message}[/green]")
        else:
            result_widget.update(f"[red]✗ {message}[/red]")
    
    async def _validate_and_save(self) -> bool:
        """Validate inputs and save to state."""
        private_key = self.query_one("#private-key-input", Input).value
        funder = self.query_one("#funder-input", Input).value
        
        valid, msg = PolymarketValidator.validate_private_key(private_key)
        if not valid:
            result_widget = self.query_one("#validation-result")
            result_widget.update(f"[red]{msg}[/red]")
            return False
        
        valid, msg = PolymarketValidator.validate_address(funder)
        if not valid:
            result_widget = self.query_one("#validation-result")
            result_widget.update(f"[red]{msg}[/red]")
            return False
        
        # Save to state
        self.state.polymarket_private_key = private_key
        self.state.polymarket_funder_address = funder
        self.state.polymarket_signature_type = 0 if self.query_one("#eoa", RadioButton).value else 1
        self.state.polymarket_configured = True
        
        return True


class KalshiStepWidget(Container):
    """Kalshi configuration step (optional)."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("Kalshi Setup", id="step-title")
        yield Static("Step 3 of 8 (Optional - for arbitrage)", id="step-indicator")
        
        yield Label("API Key:", classes="input-label")
        yield Input(
            placeholder="Your Kalshi API key",
            password=True,
            value=self.state.kalshi_api_key,
            id="api-key-input",
            classes="input-field"
        )
        yield Static(
            "[dim]Get your API key from https://kalshi.com/settings/api[/dim]",
            classes="hint-text"
        )
        
        yield Static("", id="validation-result")
        
        yield Horizontal(
            Button("Back", variant="default", id="back-btn"),
            Button("Skip", variant="default", id="skip-btn"),
            Button("Test", variant="warning", id="test-btn"),
            Button("Next", variant="primary", id="next-btn"),
            id="button-row"
        )
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            await self.app.action_back()
        elif event.button.id == "skip-btn":
            await self.app.action_skip()
        elif event.button.id == "test-btn":
            await self._test_connection()
        elif event.button.id == "next-btn":
            self._save()
            await self.app.action_next()
    
    async def _test_connection(self) -> None:
        """Test Kalshi connection."""
        result_widget = self.query_one("#validation-result")
        result_widget.update("[yellow]Testing connection...[/yellow]")
        
        api_key = self.query_one("#api-key-input", Input).value
        if not api_key:
            result_widget.update("[yellow]No API key provided - skipping test[/yellow]")
            return
        
        success, message = await KalshiValidator.test_connection(api_key)
        
        if success:
            result_widget.update(f"[green]✓ {message}[/green]")
        else:
            result_widget.update(f"[red]✗ {message}[/red]")
    
    def _save(self) -> None:
        """Save to state."""
        api_key = self.query_one("#api-key-input", Input).value
        if api_key:
            self.state.kalshi_api_key = api_key
            self.state.kalshi_configured = True


class NewsApiStepWidget(Container):
    """News API configuration step."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("News API Setup", id="step-title")
        yield Static("Step 4 of 8 (Optional - for market intelligence)", id="step-indicator")
        
        yield Label("NewsAPI Key:", classes="input-label")
        yield Input(
            placeholder="Your NewsAPI key",
            password=True,
            value=self.state.newsapi_key,
            id="newsapi-input",
            classes="input-field"
        )
        yield Static("[dim]Get free key at https://newsapi.org[/dim]", classes="hint-text")
        
        yield Label("Tavily API Key:", classes="input-label")
        yield Input(
            placeholder="Your Tavily key (for web search)",
            password=True,
            value=self.state.tavily_api_key,
            id="tavily-input",
            classes="input-field"
        )
        yield Static("[dim]Get free key at https://tavily.com[/dim]", classes="hint-text")
        
        yield Static("", id="validation-result")
        
        yield Horizontal(
            Button("Back", variant="default", id="back-btn"),
            Button("Skip", variant="default", id="skip-btn"),
            Button("Next", variant="primary", id="next-btn"),
            id="button-row"
        )
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            await self.app.action_back()
        elif event.button.id == "skip-btn":
            await self.app.action_skip()
        elif event.button.id == "next-btn":
            self._save()
            await self.app.action_next()
    
    def _save(self) -> None:
        """Save to state."""
        newsapi = self.query_one("#newsapi-input", Input).value
        tavily = self.query_one("#tavily-input", Input).value
        
        if newsapi or tavily:
            self.state.newsapi_key = newsapi
            self.state.tavily_api_key = tavily
            self.state.newsapi_configured = bool(newsapi or tavily)


class GoogleStepWidget(Container):
    """Google API configuration step."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("Google Gemini Setup", id="step-title")
        yield Static("Step 5 of 8 (Required for AI agents)", id="step-indicator")
        
        yield Label("Google API Key:", classes="input-label")
        yield Input(
            placeholder="Your Google AI Studio API key",
            password=True,
            value=self.state.google_api_key,
            id="google-input",
            classes="input-field"
        )
        yield Static(
            "[dim]Get free key at https://aistudio.google.com/apikey[/dim]",
            classes="hint-text"
        )
        
        yield Static("", id="validation-result")
        
        yield Horizontal(
            Button("Back", variant="default", id="back-btn"),
            Button("Test", variant="warning", id="test-btn"),
            Button("Skip", variant="default", id="skip-btn"),
            Button("Next", variant="primary", id="next-btn"),
            id="button-row"
        )
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            await self.app.action_back()
        elif event.button.id == "test-btn":
            await self._test_connection()
        elif event.button.id == "skip-btn":
            await self.app.action_skip()
        elif event.button.id == "next-btn":
            self._save()
            await self.app.action_next()
    
    async def _test_connection(self) -> None:
        """Test Google API connection."""
        result_widget = self.query_one("#validation-result")
        result_widget.update("[yellow]Testing connection...[/yellow]")
        
        api_key = self.query_one("#google-input", Input).value
        if not api_key:
            result_widget.update("[yellow]No API key provided[/yellow]")
            return
        
        success, message = await GoogleValidator.test_gemini(api_key)
        
        if success:
            result_widget.update(f"[green]✓ {message}[/green]")
        else:
            result_widget.update(f"[red]✗ {message}[/red]")
    
    def _save(self) -> None:
        """Save to state."""
        self.state.google_api_key = self.query_one("#google-input", Input).value


class AgentConfigStepWidget(Container):
    """Agent configuration step."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("Agent Configuration", id="step-title")
        yield Static("Step 6 of 8", id="step-indicator")
        
        yield Label("Trading Mode:", classes="input-label")
        yield RadioSet(
            RadioButton("Manual - Agents suggest, you approve all trades", id="manual", 
                       value=self.state.agent_mode == "manual"),
            RadioButton("Semi-Auto - Auto-execute small trades, approve large ones", id="semi",
                       value=self.state.agent_mode == "semi-auto"),
            RadioButton("Full-Auto - Agents execute autonomously (use with caution)", id="auto",
                       value=self.state.agent_mode == "full-auto"),
            id="mode-select"
        )
        
        yield Label("Risk Level:", classes="input-label")
        yield RadioSet(
            RadioButton("Conservative - Lower position sizes, stricter limits", id="conservative",
                       value=self.state.default_risk_level == "conservative"),
            RadioButton("Moderate - Balanced approach", id="moderate",
                       value=self.state.default_risk_level == "moderate"),
            RadioButton("Aggressive - Higher limits (experienced users)", id="aggressive",
                       value=self.state.default_risk_level == "aggressive"),
            id="risk-select"
        )
        
        yield Horizontal(
            Button("Back", variant="default", id="back-btn"),
            Button("Next", variant="primary", id="next-btn"),
            id="button-row"
        )
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            await self.app.action_back()
        elif event.button.id == "next-btn":
            self._save()
            await self.app.action_next()
    
    def _save(self) -> None:
        """Save agent configuration."""
        # Determine selected mode
        if self.query_one("#manual", RadioButton).value:
            self.state.agent_mode = "manual"
        elif self.query_one("#semi", RadioButton).value:
            self.state.agent_mode = "semi-auto"
        else:
            self.state.agent_mode = "full-auto"
        
        # Determine risk level
        if self.query_one("#conservative", RadioButton).value:
            self.state.default_risk_level = "conservative"
        elif self.query_one("#moderate", RadioButton).value:
            self.state.default_risk_level = "moderate"
        else:
            self.state.default_risk_level = "aggressive"


class ValidationStepWidget(Container):
    """Final validation step."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("Validation", id="step-title")
        yield Static("Step 7 of 8", id="step-indicator")
        
        yield Static("Running final validation checks...\n", id="validation-status")
        yield Container(id="progress-container")
        yield Static("", id="validation-results")
        
        yield Horizontal(
            Button("Back", variant="default", id="back-btn"),
            Button("Complete Setup", variant="success", id="complete-btn", disabled=True),
            id="button-row"
        )
    
    async def on_mount(self) -> None:
        """Run validation on mount."""
        await self._run_validation()
    
    async def _run_validation(self) -> None:
        """Run all validation checks."""
        results = []
        
        # Check Polymarket
        if self.state.polymarket_configured:
            success, msg = await PolymarketValidator.test_connection(
                self.state.polymarket_private_key,
                self.state.polymarket_funder_address,
                self.state.polymarket_signature_type
            )
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            results.append(f"{status} Polymarket: {msg}")
        else:
            results.append("[red]✗[/red] Polymarket: Not configured")
        
        # Check Kalshi
        if self.state.kalshi_configured:
            success, msg = await KalshiValidator.test_connection(self.state.kalshi_api_key)
            status = "[green]✓[/green]" if success else "[yellow]![/yellow]"
            results.append(f"{status} Kalshi: {msg}")
        else:
            results.append("[dim]○[/dim] Kalshi: Skipped")
        
        # Check Google
        if self.state.google_api_key:
            success, msg = await GoogleValidator.test_gemini(self.state.google_api_key)
            status = "[green]✓[/green]" if success else "[yellow]![/yellow]"
            results.append(f"{status} Google Gemini: {msg}")
        else:
            results.append("[dim]○[/dim] Google Gemini: Skipped")
        
        # Update results display
        results_widget = self.query_one("#validation-results")
        results_widget.update("\n".join(results))
        
        # Enable complete button if Polymarket works
        if self.state.polymarket_configured:
            self.query_one("#complete-btn").disabled = False
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            await self.app.action_back()
        elif event.button.id == "complete-btn":
            self.state.setup_completed = True
            self.state.setup_completed_at = datetime.utcnow().isoformat()
            self.app._save_state()
            await self.app.action_next()


class CompleteStepWidget(Container):
    """Setup complete step."""
    
    def __init__(self, state: SetupState):
        super().__init__()
        self.state = state
    
    def compose(self) -> ComposeResult:
        yield Static("Setup Complete!", id="step-title")
        yield Static("Step 8 of 8", id="step-indicator")
        
        yield Static(
            "\n[green]✓ Your configuration has been saved![/green]\n\n"
            f"Configuration file: ~/.polycli/config.yaml\n\n"
            "You can now:\n"
            "  • Run [bold]poly dashboard[/bold] to open the TUI\n"
            "  • Run [bold]poly markets list[/bold] to browse markets\n"
            "  • Run [bold]poly --paper dashboard[/bold] for paper trading\n\n"
            "[dim]Run 'poly setup' anytime to reconfigure.[/dim]\n",
            id="complete-text"
        )
        
        yield Horizontal(
            Button("Exit", variant="primary", id="exit-btn"),
            Button("Launch Dashboard", variant="success", id="launch-btn"),
            id="button-row"
        )
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "exit-btn":
            self.app.exit()
        elif event.button.id == "launch-btn":
            self.app.exit(result="launch_dashboard")
