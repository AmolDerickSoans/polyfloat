"""Telemetry module for local-first event tracking."""
import secrets
import socket
import time
from typing import Optional

from .models import TelemetryEvent
from .store import TelemetryStore


_session_id: Optional[str] = None


def generate_session_id() -> str:
    """Generate a unique session ID.

    Format: {hostname}_{timestamp}_{random_suffix}
    Example: mbp2024_1704307100_a1b2c3
    """
    hostname = socket.gethostname()[:10]
    timestamp = int(time.time())
    random_suffix = secrets.token_hex(3)
    return f"{hostname}_{timestamp}_{random_suffix}"


def get_session_id() -> str:
    """Get the current session ID, generating one if needed."""
    global _session_id
    if _session_id is None:
        _session_id = generate_session_id()
    return _session_id


def set_session_id(session_id: str) -> None:
    """Set the session ID explicitly (useful for testing)."""
    global _session_id
    _session_id = session_id


def reset_session_id() -> None:
    """Reset the session ID (generates a new one on next call)."""
    global _session_id
    _session_id = None


def emit_event(
    event_type: str,
    payload: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> None:
    """Convenience function to emit a telemetry event.

    Args:
        event_type: The type of event (e.g., 'agent_proposal', 'trade_executed')
        payload: Additional data to log with the event
        session_id: Optional session ID (uses current session if not provided)
    """
    store = TelemetryStore()
    event = TelemetryEvent(
        event_type=event_type,
        timestamp=time.time(),
        session_id=session_id or get_session_id(),
        payload=payload or {},
    )
    store.emit(event)


__all__ = [
    "TelemetryEvent",
    "TelemetryStore",
    "generate_session_id",
    "get_session_id",
    "set_session_id",
    "reset_session_id",
    "emit_event",
]
