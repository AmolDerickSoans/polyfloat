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
