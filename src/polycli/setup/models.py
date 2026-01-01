"""Setup wizard data models."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
import yaml


class SetupStepStatus(Enum):
    """Status of a setup step."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class SetupState:
    """Tracks wizard progress and collected configuration."""
    
    # Step status
    current_step: int = 0
    step_statuses: Dict[str, SetupStepStatus] = field(default_factory=dict)
    
    # Polymarket config
    polymarket_configured: bool = False
    polymarket_private_key: str = ""
    polymarket_funder_address: str = ""
    polymarket_signature_type: int = 0  # 0 for EOA, 1 for Gnosis Safe
    
    # Kalshi config
    kalshi_configured: bool = False
    kalshi_email: str = ""
    kalshi_password: str = ""  # Never persisted
    kalshi_api_key: str = ""
    
    # News API config
    newsapi_configured: bool = False
    newsapi_key: str = ""
    tavily_api_key: str = ""
    
    # Google (for Gemini agents)
    google_api_key: str = ""
    
    # Agent config
    agent_mode: str = "manual"  # manual, semi-auto, full-auto
    default_risk_level: str = "conservative"  # conservative, moderate, aggressive
    
    # General
    setup_completed: bool = False
    setup_completed_at: Optional[str] = None
    
    def to_config_dict(self) -> Dict[str, Any]:
        """Convert to configuration dictionary for saving."""
        return {
            "polymarket": {
                "private_key": self.polymarket_private_key,
                "funder_address": self.polymarket_funder_address,
                "signature_type": self.polymarket_signature_type,
                "configured": self.polymarket_configured
            },
            "kalshi": {
                "api_key": self.kalshi_api_key,
                "configured": self.kalshi_configured
            },
            "news": {
                "newsapi_key": self.newsapi_key,
                "tavily_key": self.tavily_api_key,
                "configured": self.newsapi_configured
            },
            "google": {
                "api_key": self.google_api_key
            },
            "agent": {
                "mode": self.agent_mode,
                "risk_level": self.default_risk_level
            },
            "setup": {
                "completed": self.setup_completed,
                "completed_at": self.setup_completed_at
            }
        }
    
    @classmethod
    def from_config_dict(cls, data: Dict[str, Any]) -> "SetupState":
        """Load from existing configuration."""
        poly = data.get("polymarket", {})
        kalshi = data.get("kalshi", {})
        news = data.get("news", {})
        google = data.get("google", {})
        agent = data.get("agent", {})
        setup = data.get("setup", {})
        
        return cls(
            polymarket_configured=poly.get("configured", False),
            polymarket_private_key=poly.get("private_key", ""),
            polymarket_funder_address=poly.get("funder_address", ""),
            polymarket_signature_type=poly.get("signature_type", 0),
            kalshi_configured=kalshi.get("configured", False),
            kalshi_api_key=kalshi.get("api_key", ""),
            newsapi_configured=news.get("configured", False),
            newsapi_key=news.get("newsapi_key", ""),
            tavily_api_key=news.get("tavily_key", ""),
            google_api_key=google.get("api_key", ""),
            agent_mode=agent.get("mode", "manual"),
            default_risk_level=agent.get("risk_level", "conservative"),
            setup_completed=setup.get("completed", False),
            setup_completed_at=setup.get("completed_at")
        )


@dataclass
class ValidationResult:
    """Result of validating a configuration step."""
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
