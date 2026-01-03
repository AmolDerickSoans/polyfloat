"""Telemetry data models."""
from dataclasses import dataclass, field
from typing import Dict, Any
import time


@dataclass
class TelemetryEvent:
    """Represents a single telemetry event."""

    event_type: str
    timestamp: float = field(default_factory=lambda: time.time())
    session_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetryEvent":
        """Create from dictionary."""
        return cls(
            event_type=data["event_type"],
            timestamp=data["timestamp"],
            session_id=data["session_id"],
            payload=data["payload"],
        )
