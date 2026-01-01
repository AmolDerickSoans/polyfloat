"""Emergency stop data models."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List
import uuid


class StopReason(Enum):
    """Reasons for emergency stop."""
    USER_INITIATED = "user_initiated"
    RISK_LIMIT_BREACH = "risk_limit_breach"
    AGENT_ERROR = "agent_error"
    MARKET_EMERGENCY = "market_emergency"
    SYSTEM_ERROR = "system_error"
    CONNECTION_FAILURE = "connection_failure"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"


@dataclass
class EmergencyStopEvent:
    """Represents an emergency stop event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reason: StopReason = StopReason.USER_INITIATED
    description: str = ""
    triggered_by: str = "user"
    
    agents_stopped: int = 0
    orders_cancelled: int = 0
    websockets_closed: int = 0
    
    auto_resume_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    resumed_by: Optional[str] = None
    
    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason.value,
            "description": self.description,
            "triggered_by": self.triggered_by,
            "agents_stopped": self.agents_stopped,
            "orders_cancelled": self.orders_cancelled,
            "websockets_closed": self.websockets_closed,
            "auto_resume_at": self.auto_resume_at.isoformat() if self.auto_resume_at else None,
            "resumed_at": self.resumed_at.isoformat() if self.resumed_at else None,
            "resumed_by": self.resumed_by
        }


@dataclass
class StopState:
    """Current emergency stop state."""
    is_stopped: bool = False
    stop_event: Optional[EmergencyStopEvent] = None
    stop_file_path: str = ""
