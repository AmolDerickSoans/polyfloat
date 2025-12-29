import pytest
from unittest.mock import MagicMock, patch
from polycli.tui import DashboardApp

@pytest.fixture
def app():
    # Use a dummy APP or mock necessary components
    with patch("polycli.tui.RedisStore"), \
         patch("polycli.tui.SQLiteStore"), \
         patch("polycli.tui.PolyProvider"), \
         patch("polycli.tui.KalshiProvider"), \
         patch("polycli.tui.SupervisorAgent"), \
         patch("polycli.tui.PolymarketWebSocket"), \
         patch("polycli.tui.KalshiWebSocket"):
        return DashboardApp()

def test_agent_mode_cycling(app):
    assert app.agent_mode == "manual"
    app.action_cycle_agent_mode()
    assert app.agent_mode == "auto-approval"
    app.action_cycle_agent_mode()
    assert app.agent_mode == "full-auto"
    app.action_cycle_agent_mode()
    assert app.agent_mode == "manual"

def test_provider_change_updates_supervisor(app):
    mock_event = MagicMock()
    mock_event.pressed.id = "p_kalshi"
    
    with patch.object(app, "update_markets"):
        app.on_provider_change(mock_event)
        assert app.selected_provider == "kalshi"
        assert app.supervisor.provider == app.kalshi
