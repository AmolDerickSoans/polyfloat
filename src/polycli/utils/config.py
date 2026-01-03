import os
import yaml
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG_PATH = Path.home() / ".polycli" / "config.yaml"


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_path.exists():
        return {}

    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def save_config(
    config: Dict[str, Any], config_path: Path = DEFAULT_CONFIG_PATH
) -> None:
    """Save configuration to YAML file"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f)


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a configuration value with environment variable override"""
    config = load_config()

    # Check env var first (e.g. POLYCLI_AUTH_POLYMARKET_PRIVATE_KEY)
    env_key = f"POLYCLI_{key.upper().replace('.', '_')}"
    if env_key in os.environ:
        return os.environ[env_key]

    # Navigate config dict
    keys = key.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def get_paper_mode() -> bool:
    """Check if paper trading mode is enabled"""
    return get_config_value("paper_mode", False)


def set_paper_mode(enabled: bool) -> None:
    """Toggle paper trading mode"""
    config = load_config()
    config["paper_mode"] = enabled
    save_config(config)


def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled (defaults to True if not set)."""
    return get_config_value("telemetry.enabled", True)


def get_telemetry_retention_days() -> int:
    """Get telemetry retention period in days (defaults to 30)."""
    return get_config_value("telemetry.retention_days", 30)


def set_telemetry_enabled(enabled: bool) -> None:
    """Enable or disable telemetry."""
    config = load_config()
    if "telemetry" not in config:
        config["telemetry"] = {}
    config["telemetry"]["enabled"] = enabled
    save_config(config)


def set_telemetry_retention_days(days: int) -> None:
    """Set telemetry retention period in days."""
    config = load_config()
    if "telemetry" not in config:
        config["telemetry"] = {}
    config["telemetry"]["retention_days"] = days
    save_config(config)
