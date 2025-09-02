import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Callable

load_dotenv()

# Optional YAML config support — if PyYAML is not installed or config.yml is missing,
# we fall back to environment variables.
CONFIG_PATH = Path("config.yml")
_yaml = None
try:
    import yaml as _yaml_pkg  # type: ignore
    _yaml = _yaml_pkg
except Exception:
    _yaml = None

_config: dict = {}
if _yaml and CONFIG_PATH.exists():
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            _config = _yaml.safe_load(f) or {}
    except Exception:
        _config = {}

def _get(name: str, env_name: str, default: Any, cast: Callable[[Any], Any] = lambda x: x) -> Any:
    # Priority: config.yml -> environment -> default
    if name in _config:
        try:
            return cast(_config[name])
        except Exception:
            # fallback to raw value from config
            return _config[name]
    val = os.getenv(env_name)
    if val is None:
        return default
    try:
        return cast(val)
    except Exception:
        return val

# Simple casters
def _bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")

def _float(v):
    return float(v)

def _int(v):
    return int(v)

# General mode
MODE = _get("MODE", "MODE", "paper", lambda v: str(v).lower())  # 'paper' or 'live'

# Binance futures (USDM) settings
BINANCE_TESTNET = _get("BINANCE_TESTNET", "BINANCE_TESTNET", True, _bool)
BINANCE_API_KEY = _get("BINANCE_API_KEY", "BINANCE_API_KEY", "", str)
BINANCE_API_SECRET = _get("BINANCE_API_SECRET", "BINANCE_API_SECRET", "", str)

# Money / risk settings
STARTING_BALANCE_USDT = _get("STARTING_BALANCE_USDT", "STARTING_BALANCE_USDT", 1000.0, _float)
POSITION_SIZE_PERCENT = _get("POSITION_SIZE_PERCENT", "POSITION_SIZE_PERCENT", 1.0, _float) / 100.0
DAILY_PROFIT_TARGET_USD = _get("DAILY_PROFIT_TARGET_USD", "DAILY_PROFIT_TARGET_USD", 40.0, _float)
MAX_DAILY_LOSS_USD = _get("MAX_DAILY_LOSS_USD", "MAX_DAILY_LOSS_USD", 100.0, _float)

# Notifications
TELEGRAM_TOKEN = _get("TELEGRAM_TOKEN", "TELEGRAM_TOKEN", "", str)
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID", "", str)

# Logging
LOG_LEVEL = _get("LOG_LEVEL", "LOG_LEVEL", "INFO", lambda v: str(v).upper())
