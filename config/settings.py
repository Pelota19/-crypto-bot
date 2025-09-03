"""Configuration module for crypto bot."""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Callable, List

load_dotenv()

def _get_env(name: str, default: Any = None, cast: Callable[[str], Any] = str) -> Any:
    """Get environment variable with type casting."""
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return cast(val)
    except (ValueError, TypeError):
        return default

def _bool(v: str) -> bool:
    """Convert string to boolean."""
    return str(v).lower() in ("true", "1", "yes", "on")

def _float(v: str) -> float:
    """Convert string to float."""
    return float(v)

def _int(v: str) -> int:
    """Convert string to int."""
    return int(v)

def _list_str(v: str) -> List[str]:
    """Convert comma-separated string to list."""
    return [item.strip() for item in v.split(",") if item.strip()]

# Exchange settings
EXCHANGE = _get_env("EXCHANGE", "binance")
API_KEY = _get_env("API_KEY", "")
API_SECRET = _get_env("API_SECRET", "")
USE_TESTNET = _get_env("USE_TESTNET", True, _bool)

# Trading settings
DAILY_PROFIT_TARGET = _get_env("DAILY_PROFIT_TARGET", 50.0, _float)
MAX_INVESTMENT = _get_env("MAX_INVESTMENT", 2000.0, _float)
TRADING_PAIRS = _get_env("TRADING_PAIRS", "BTC/USDT,ETH/USDT", _list_str)
STRATEGY = _get_env("STRATEGY", "scalping_ema_rsi")

# Risk management
MAX_RISK_PER_TRADE = _get_env("MAX_RISK_PER_TRADE", 1.0, _float)  # percentage
MAX_OPEN_TRADES = _get_env("MAX_OPEN_TRADES", 5, _int)
MAX_DAILY_DRAWDOWN = _get_env("MAX_DAILY_DRAWDOWN", 5.0, _float)  # percentage
RISK_REWARD_RATIO = _get_env("RISK_REWARD_RATIO", 2.0, _float)

# Telegram
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID", "")

# Logging
LOG_LEVEL = _get_env("LOG_LEVEL", "INFO")

# Safety / execution
DRY_RUN = _get_env("DRY_RUN", True, _bool)  # True = no real orders (recommended to test)
ORDER_TIMEOUT = _get_env("ORDER_TIMEOUT", 30, _int)  # seconds to wait for fills

# Paths
DATA_DIR = Path("data")
LOGS_DIR = Path("logs")

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
