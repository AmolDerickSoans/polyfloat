"""Integration tests for telemetry event emission across the system."""
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from polycli.telemetry import (
    TelemetryEvent,
    TelemetryStore,
    get_session_id,
    set_session_id,
    reset_session_id,
)


class TestCommandInvocationTelemetry:
    """Test command_invoked event emission from CLI commands."""

    def test_track_command_decorator_exists(self, tmp_path):
        """The track_command decorator should be importable from cli module."""
        from polycli import cli

        assert hasattr(cli, "track_command")
        assert callable(cli.track_command)

    def test_track_command_emits_event(self, tmp_path):
        """track_command decorator should emit command_invoked event."""
        from polycli import cli

        mock_store_instance = MagicMock()
        mock_store_instance.enabled = True

        with patch("polycli.cli.get_telemetry_store", return_value=mock_store_instance):
            set_session_id("test_session_123")

            @cli.track_command
            def dummy_command():
                return "success"

            result = dummy_command()
            assert result == "success"

            assert mock_store_instance.emit.called

            call_args = mock_store_instance.emit.call_args
            event = call_args[0][0]
            assert event.event_type == "command_invoked"
            assert event.session_id == "test_session_123"
            assert "command" in event.payload
            assert event.payload["command"] == "dummy_command"
            assert "args_hash" in event.payload
            assert "paper_mode" in event.payload

        reset_session_id()

    def test_track_command_hashes_args(self, tmp_path):
        """track_command should hash arguments for privacy."""
        from polycli import cli

        mock_store_instance = MagicMock()
        mock_store_instance.enabled = True

        with patch("polycli.cli.get_telemetry_store", return_value=mock_store_instance):
            set_session_id("test_session_456")

            @cli.track_command
            def command_with_args(a, b, c):
                return a + b + c

            command_with_args(1, 2, 3)

            assert mock_store_instance.emit.called
            event = mock_store_instance.emit.call_args[0][0]
            args_hash = event.payload["args_hash"]
            assert isinstance(args_hash, str)
            assert len(args_hash) == 16

        reset_session_id()


class TestAgentProposalTelemetry:
    """Test agent_proposal_created event emission from TraderAgent."""

    def test_trader_agent_has_emit_method(self):
        """TraderAgent should have _emit_proposal_event method."""
        from polycli.agents.trader import TraderAgent

        agent = TraderAgent()
        assert hasattr(agent, "_emit_proposal_event")
        assert callable(agent._emit_proposal_event)

    def test_trader_agent_has_risk_status_method(self):
        """TraderAgent should have _get_risk_status method."""
        from polycli.agents.trader import TraderAgent

        agent = TraderAgent()
        assert hasattr(agent, "_get_risk_status")
        assert callable(agent._get_risk_status)

    def test_get_risk_status_parses_context(self):
        """_get_risk_status should parse risk context string."""
        from polycli.agents.trader import TraderAgent

        agent = TraderAgent()

        assert agent._get_risk_status("") == "unknown"
        assert agent._get_risk_status("GREEN") == "green"
        assert agent._get_risk_status("YELLOW") == "yellow"
        assert agent._get_risk_status("RED") == "red"
        assert (
            agent._get_risk_status("circuit_breaker_active: True")
            == "circuit_breaker_active"
        )
        assert agent._get_risk_status("trading_enabled: False") == "trading_disabled"

    def test_emit_proposal_event(self, tmp_path):
        """_emit_proposal_event should create and emit TelemetryEvent."""
        from polycli.agents.trader import TraderAgent
        from polycli.telemetry.store import TelemetryStore

        db_path = tmp_path / "test_telemetry.db"
        store = TelemetryStore(db_path=db_path)

        mock_store = MagicMock()
        mock_store.enabled = True

        with patch("polycli.agents.trader.TelemetryStore", return_value=mock_store):
            set_session_id("test_session_proposal")

            agent = TraderAgent()
            agent._emit_proposal_event(
                agent_id="trader",
                strategy="one_best_trade",
                market_id="0x1234567890abcdef",
                risk_context_status="green",
                news_context_used=True,
            )

            assert mock_store.emit.called
            event = mock_store.emit.call_args[0][0]
            assert event.event_type == "agent_proposal_created"
            assert event.session_id == "test_session_proposal"
            assert event.payload["agent_id"] == "trader"
            assert event.payload["strategy"] == "one_best_trade"
            assert event.payload["risk_context_status"] == "green"
            assert event.payload["news_context_used"] == True

        reset_session_id()


class TestTradeExecutionTelemetry:
    """Test trade_executed and trade_failed event emission from TradingTools."""

    def test_trading_tools_has_emit_methods(self):
        """TradingTools should have _emit_trade_executed_event and _emit_trade_failed_event."""
        from polycli.agents.tools.trading import TradingTools

        assert hasattr(TradingTools, "_emit_trade_executed_event")
        assert hasattr(TradingTools, "_emit_trade_failed_event")

    def test_emit_trade_executed_event(self, tmp_path):
        """_emit_trade_executed_event should create TelemetryEvent with truncated order_id."""
        from polycli.agents.tools.trading import TradingTools

        mock_store_instance = MagicMock()
        mock_store_instance.enabled = True

        with patch(
            "polycli.agents.tools.trading.TelemetryStore",
            return_value=mock_store_instance,
        ):
            with patch(
                "polycli.agents.tools.trading.get_paper_mode", return_value=False
            ):
                set_session_id("test_session_trade")

                tools = TradingTools(poly_provider=MagicMock())
                tools._emit_trade_executed_event(
                    provider="polymarket",
                    side="BUY",
                    amount=100.0,
                    order_id="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                    latency_ms=150,
                    agent_initiated=True,
                    paper_mode=False,
                )

                assert mock_store_instance.emit.called
                event = mock_store_instance.emit.call_args[0][0]
                assert event.event_type == "trade_executed"
                assert event.session_id == "test_session_trade"
                assert event.payload["provider"] == "polymarket"
                assert event.payload["side"] == "BUY"
                assert event.payload["amount"] == 100.0
                assert len(event.payload["order_id"]) == 8
                assert event.payload["order_id"].startswith("0x")
                assert event.payload["latency_ms"] == 150
                assert event.payload["agent_initiated"] == True
                assert event.payload["paper_mode"] == False

        reset_session_id()

    def test_emit_trade_failed_event(self, tmp_path):
        """_emit_trade_failed_event should create TelemetryEvent with error codes."""
        from polycli.agents.tools.trading import TradingTools

        mock_store = MagicMock()
        mock_store.enabled = True

        with patch(
            "polycli.agents.tools.trading.TelemetryStore", return_value=mock_store
        ):
            with patch(
                "polycli.agents.tools.trading.get_paper_mode", return_value=True
            ):
                set_session_id("test_session_failed")

                tools = TradingTools(poly_provider=MagicMock())
                tools._emit_trade_failed_event(
                    provider="polymarket",
                    failure_stage="risk_check",
                    error_codes=["E001", "E002"],
                    agent_initiated=False,
                    paper_mode=True,
                )

                assert mock_store.emit.called
                event = mock_store.emit.call_args[0][0]
                assert event.event_type == "trade_failed"
                assert event.session_id == "test_session_failed"
                assert event.payload["provider"] == "polymarket"
                assert event.payload["failure_stage"] == "risk_check"
                assert event.payload["error_codes"] == ["E001", "E002"]
                assert event.payload["agent_initiated"] == False
                assert event.payload["paper_mode"] == True

        reset_session_id()


class TestProposalApprovalTelemetry:
    """Test proposal_approved and proposal_rejected event emission from TUI."""

    def test_agent_chat_has_emit_methods(self):
        """AgentChatInterface should have proposal approval/rejection emit methods."""
        from polycli.tui_agent_chat import AgentChatInterface

        assert hasattr(AgentChatInterface, "_emit_proposal_approved_event")
        assert hasattr(AgentChatInterface, "_emit_proposal_rejected_event")

    def test_emit_proposal_approved_event(self, tmp_path):
        """_emit_proposal_approved_event should create TelemetryEvent."""
        from polycli.tui_agent_chat import AgentChatInterface

        mock_store = MagicMock()
        mock_store.enabled = True

        with patch("polycli.tui_agent_chat.TelemetryStore", return_value=mock_store):
            set_session_id("test_session_approve")

            chat = AgentChatInterface(redis_store=MagicMock(), supervisor=MagicMock())
            chat._emit_proposal_approved_event(
                proposal_age_seconds=45.5,
                market_id="0x12345678...",
                was_stale=False,
            )

            assert mock_store.emit.called
            event = mock_store.emit.call_args[0][0]
            assert event.event_type == "proposal_approved"
            assert event.session_id == "test_session_approve"
            assert event.payload["proposal_age_seconds"] == 45.5
            assert event.payload["market_id"] == "0x12345678..."
            assert event.payload["was_stale"] == False

        reset_session_id()

    def test_emit_proposal_rejected_event(self, tmp_path):
        """_emit_proposal_rejected_event should create TelemetryEvent."""
        from polycli.tui_agent_chat import AgentChatInterface

        mock_store = MagicMock()
        mock_store.enabled = True

        with patch("polycli.tui_agent_chat.TelemetryStore", return_value=mock_store):
            set_session_id("test_session_reject")

            chat = AgentChatInterface(redis_store=MagicMock(), supervisor=MagicMock())
            chat._emit_proposal_rejected_event(
                proposal_age_seconds=120.0,
                market_id="0xabcdef12...",
                was_stale=True,
            )

            assert mock_store.emit.called
            event = mock_store.emit.call_args[0][0]
            assert event.event_type == "proposal_rejected"
            assert event.session_id == "test_session_reject"
            assert event.payload["proposal_age_seconds"] == 120.0
            assert event.payload["market_id"] == "0xabcdef12..."
            assert event.payload["was_stale"] == True

        reset_session_id()


class TestTelemetryPrivacyRequirements:
    """Test that telemetry events respect privacy requirements."""

    def test_command_args_are_hashed_not_logged(self, tmp_path):
        """Command arguments should be hashed, not logged in plaintext."""
        from polycli import cli

        mock_store_instance = MagicMock()
        mock_store_instance.enabled = True

        with patch("polycli.cli.get_telemetry_store", return_value=mock_store_instance):
            set_session_id("test_session_hash")

            @cli.track_command
            def sensitive_command(api_key="secret_key", password="password123"):
                return "done"

            sensitive_command(api_key="secret_key_123", password="password456")

            assert mock_store_instance.emit.called
            event = mock_store_instance.emit.call_args[0][0]
            args_hash = event.payload["args_hash"]

            assert "secret" not in args_hash
            assert "password" not in args_hash
            assert "secret_key_123" not in args_hash
            assert "password456" not in args_hash

        reset_session_id()

    def test_order_id_truncation(self, tmp_path):
        """Order IDs should be truncated to 8 characters."""
        from polycli.agents.tools.trading import TradingTools

        mock_store = MagicMock()
        mock_store.enabled = True

        with patch(
            "polycli.agents.tools.trading.TelemetryStore", return_value=mock_store
        ):
            with patch(
                "polycli.agents.tools.trading.get_paper_mode", return_value=False
            ):
                set_session_id("test_session_truncate")

                tools = TradingTools(poly_provider=MagicMock())
                tools._emit_trade_executed_event(
                    provider="polymarket",
                    side="BUY",
                    amount=50.0,
                    order_id="very_long_order_id_that_should_be_truncated",
                    latency_ms=100,
                    agent_initiated=True,
                    paper_mode=False,
                )

                event = mock_store.emit.call_args[0][0]
                assert len(event.payload["order_id"]) == 8

        reset_session_id()

    def test_market_id_truncation(self, tmp_path):
        """Market IDs should be truncated in proposal events."""
        from polycli.agents.trader import TraderAgent

        mock_store = MagicMock()
        mock_store.enabled = True

        with patch("polycli.agents.trader.TelemetryStore", return_value=mock_store):
            set_session_id("test_session_market")

            agent = TraderAgent()
            agent._emit_proposal_event(
                agent_id="trader",
                strategy="one_best_trade",
                market_id="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                risk_context_status="green",
                news_context_used=False,
            )

            event = mock_store.emit.call_args[0][0]
            assert "..." in event.payload["market_id"]
            assert len(event.payload["market_id"]) < 30

        reset_session_id()


class TestTelemetryNonBlocking:
    """Test that telemetry emission does not block main flows."""

    def test_emit_does_not_raise_exceptions(self, tmp_path):
        """Event emission should not raise exceptions that block execution."""
        from polycli import cli
        from polycli.agents.trader import TraderAgent
        from polycli.agents.tools.trading import TradingTools
        from polycli.tui_agent_chat import AgentChatInterface

        mock_cli_instance = MagicMock()
        mock_cli_instance.enabled = True
        mock_cli_instance.emit.side_effect = Exception("Database error")

        mock_agent_instance = MagicMock()
        mock_agent_instance.enabled = True
        mock_agent_instance.emit.side_effect = Exception("DB error")

        mock_trade_instance = MagicMock()
        mock_trade_instance.enabled = True
        mock_trade_instance.emit.side_effect = Exception("Trade DB error")

        mock_chat_instance = MagicMock()
        mock_chat_instance.enabled = True
        mock_chat_instance.emit.side_effect = Exception("Chat DB error")

        with patch("polycli.cli.get_telemetry_store", return_value=mock_cli_instance):
            with patch(
                "polycli.agents.trader.TelemetryStore", return_value=mock_agent_instance
            ):
                with patch(
                    "polycli.agents.tools.trading.TelemetryStore",
                    return_value=mock_trade_instance,
                ):
                    with patch(
                        "polycli.agents.tools.trading.get_paper_mode",
                        return_value=False,
                    ):
                        with patch(
                            "polycli.tui_agent_chat.TelemetryStore",
                            return_value=mock_chat_instance,
                        ):
                            set_session_id("test_session_noblock")

                            @cli.track_command
                            def test_cmd():
                                return "should_succeed"

                            result = test_cmd()
                            assert result == "should_succeed"

                            agent = TraderAgent()
                            agent._emit_proposal_event(
                                agent_id="trader",
                                strategy="test",
                                market_id="0x123",
                                risk_context_status="green",
                                news_context_used=False,
                            )

                            tools = TradingTools(poly_provider=MagicMock())
                            tools._emit_trade_executed_event(
                                provider="polymarket",
                                side="BUY",
                                amount=10.0,
                                order_id="order123",
                                latency_ms=50,
                                agent_initiated=False,
                                paper_mode=True,
                            )

                            chat = AgentChatInterface(
                                redis_store=MagicMock(), supervisor=MagicMock()
                            )
                            chat._emit_proposal_approved_event(
                                proposal_age_seconds=10.0,
                                market_id="0x456",
                                was_stale=False,
                            )

        reset_session_id()


class TestTelemetryTimestamps:
    """Test that all events have correct timestamp format."""

    def test_all_events_have_float_timestamp(self, tmp_path):
        """All telemetry events should have Unix float timestamps."""
        from polycli import cli
        from polycli.agents.trader import TraderAgent
        from polycli.agents.tools.trading import TradingTools
        from polycli.tui_agent_chat import AgentChatInterface

        mock_cli_instance = MagicMock()
        mock_cli_instance.enabled = True

        mock_agent_instance = MagicMock()
        mock_agent_instance.enabled = True

        mock_trade_instance = MagicMock()
        mock_trade_instance.enabled = True

        mock_chat_instance = MagicMock()
        mock_chat_instance.enabled = True

        with patch("polycli.cli.get_telemetry_store", return_value=mock_cli_instance):
            with patch(
                "polycli.agents.trader.TelemetryStore", return_value=mock_agent_instance
            ):
                with patch(
                    "polycli.agents.tools.trading.TelemetryStore",
                    return_value=mock_trade_instance,
                ):
                    with patch(
                        "polycli.agents.tools.trading.get_paper_mode",
                        return_value=False,
                    ):
                        with patch(
                            "polycli.tui_agent_chat.TelemetryStore",
                            return_value=mock_chat_instance,
                        ):
                            set_session_id("test_session_ts")

                            @cli.track_command
                            def test_cmd():
                                pass

                            test_cmd()
                            cli_event = mock_cli_instance.emit.call_args[0][0]
                            assert isinstance(cli_event.timestamp, float)

                            agent = TraderAgent()
                            agent._emit_proposal_event(
                                agent_id="trader",
                                strategy="test",
                                market_id="0x123",
                                risk_context_status="green",
                                news_context_used=False,
                            )
                            agent_event = mock_agent_instance.emit.call_args[0][0]
                            assert isinstance(agent_event.timestamp, float)

                            tools = TradingTools(poly_provider=MagicMock())
                            tools._emit_trade_executed_event(
                                provider="polymarket",
                                side="BUY",
                                amount=10.0,
                                order_id="order123",
                                latency_ms=50,
                                agent_initiated=False,
                                paper_mode=True,
                            )
                            trade_event = mock_trade_instance.emit.call_args[0][0]
                            assert isinstance(trade_event.timestamp, float)

                            chat = AgentChatInterface(
                                redis_store=MagicMock(), supervisor=MagicMock()
                            )
                            chat._emit_proposal_approved_event(
                                proposal_age_seconds=10.0,
                                market_id="0x456",
                                was_stale=False,
                            )
                            proposal_event = mock_chat_instance.emit.call_args[0][0]
                            assert isinstance(proposal_event.timestamp, float)

        reset_session_id()
