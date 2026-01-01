"""Risk configuration management."""
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional
import json

import structlog

logger = structlog.get_logger()


@dataclass
class RiskConfig:
    """
    Configuration for risk management.
    
    All monetary values are in the account's base currency (USD/USDC).
    All percentages are decimals (0.1 = 10%).
    """
    
    # Position size limits
    max_position_size_usd: Decimal = Decimal("100.00")  # Max single position
    max_position_size_pct: Decimal = Decimal("0.10")  # Max 10% of portfolio per position
    
    # Portfolio concentration
    max_concentration_single_market: Decimal = Decimal("0.25")  # Max 25% in one market
    max_concentration_single_event: Decimal = Decimal("0.40")  # Max 40% in one event
    
    # Loss limits
    daily_loss_limit_usd: Decimal = Decimal("50.00")  # Max daily loss
    daily_loss_limit_pct: Decimal = Decimal("0.05")  # Max 5% daily loss
    max_drawdown_pct: Decimal = Decimal("0.20")  # Max 20% drawdown from peak
    
    # Circuit breaker
    circuit_breaker_enabled: bool = True
    circuit_breaker_cooldown_minutes: int = 60  # Cooldown after trigger
    
    # Price sanity checks
    max_price_deviation_pct: Decimal = Decimal("0.05")  # Max 5% deviation from midpoint
    
    # Trade frequency
    max_trades_per_minute: int = 10
    max_trades_per_hour: int = 100
    
    # Global controls
    trading_enabled: bool = True  # Master switch
    agents_enabled: bool = True  # Allow autonomous agents
    
    # Provider-specific overrides
    provider_overrides: Dict[str, Dict] = field(default_factory=dict)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "RiskConfig":
        """Load risk config from file."""
        if path is None:
            path = Path.home() / ".polycli" / "risk_config.json"
        
        if not path.exists():
            config = cls()
            config.save(path)
            return config
        
        try:
            with open(path) as f:
                data = json.load(f)
            
            return cls(
                max_position_size_usd=Decimal(str(data.get("max_position_size_usd", 100))),
                max_position_size_pct=Decimal(str(data.get("max_position_size_pct", 0.10))),
                max_concentration_single_market=Decimal(str(data.get("max_concentration_single_market", 0.25))),
                max_concentration_single_event=Decimal(str(data.get("max_concentration_single_event", 0.40))),
                daily_loss_limit_usd=Decimal(str(data.get("daily_loss_limit_usd", 50))),
                daily_loss_limit_pct=Decimal(str(data.get("daily_loss_limit_pct", 0.05))),
                max_drawdown_pct=Decimal(str(data.get("max_drawdown_pct", 0.20))),
                circuit_breaker_enabled=data.get("circuit_breaker_enabled", True),
                circuit_breaker_cooldown_minutes=data.get("circuit_breaker_cooldown_minutes", 60),
                max_price_deviation_pct=Decimal(str(data.get("max_price_deviation_pct", 0.05))),
                max_trades_per_minute=data.get("max_trades_per_minute", 10),
                max_trades_per_hour=data.get("max_trades_per_hour", 100),
                trading_enabled=data.get("trading_enabled", True),
                agents_enabled=data.get("agents_enabled", True),
                provider_overrides=data.get("provider_overrides", {})
            )
        except Exception as e:
            logger.error("Failed to load risk config, using defaults", error=str(e))
            return cls()
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save risk config to file."""
        if path is None:
            path = Path.home() / ".polycli" / "risk_config.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "max_position_size_usd": float(self.max_position_size_usd),
            "max_position_size_pct": float(self.max_position_size_pct),
            "max_concentration_single_market": float(self.max_concentration_single_market),
            "max_concentration_single_event": float(self.max_concentration_single_event),
            "daily_loss_limit_usd": float(self.daily_loss_limit_usd),
            "daily_loss_limit_pct": float(self.daily_loss_limit_pct),
            "max_drawdown_pct": float(self.max_drawdown_pct),
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "circuit_breaker_cooldown_minutes": self.circuit_breaker_cooldown_minutes,
            "max_price_deviation_pct": float(self.max_price_deviation_pct),
            "max_trades_per_minute": self.max_trades_per_minute,
            "max_trades_per_hour": self.max_trades_per_hour,
            "trading_enabled": self.trading_enabled,
            "agents_enabled": self.agents_enabled,
            "provider_overrides": self.provider_overrides
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_for_provider(self, provider: str) -> "RiskConfig":
        """Get config with provider-specific overrides applied."""
        if provider not in self.provider_overrides:
            return self
        
        # Create copy with overrides
        overrides = self.provider_overrides[provider]
        return RiskConfig(
            max_position_size_usd=Decimal(str(overrides.get("max_position_size_usd", self.max_position_size_usd))),
            max_position_size_pct=Decimal(str(overrides.get("max_position_size_pct", self.max_position_size_pct))),
            # ... apply other overrides
            trading_enabled=overrides.get("trading_enabled", self.trading_enabled),
            agents_enabled=overrides.get("agents_enabled", self.agents_enabled),
        )
