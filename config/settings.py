import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Callable, List

load_dotenv()

def _get_env(name: str, default: Any = None, cast: Callable[[str], Any] = str) -> Any:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return cast(val)
    except Exception:
        return default

def _bool(v: str) -> bool:
    return str(v).lower() in ("true", "1", "yes", "on")

def _float(v: str) -> float:
    return float(v)

def _int(v: str) -> int:
    return int(v)

def _list_str(v: str) -> List[str]:
    return [item.strip() for item in v.split(",") if item.strip()]

# --- Exchange ---
API_KEY = _get_env("BINANCE_API_KEY", "")
API_SECRET = _get_env("BINANCE_API_SECRET", "")
USE_TESTNET = _get_env("USE_TESTNET", True, _bool)
DRY_RUN = _get_env("DRY_RUN", False, _bool)

# --- Trading ---
# legacy / .env compatibility: DAILY_PROFIT_TARGET_USD is kept, y además exponemos DAILY_PROFIT_TARGET
DAILY_PROFIT_TARGET_USD = _get_env("DAILY_PROFIT_TARGET_USD", 50.0, _float)
# Some parts of the code expect DAILY_PROFIT_TARGET (no sufijo). Allow either:
DAILY_PROFIT_TARGET = _get_env("DAILY_PROFIT_TARGET", DAILY_PROFIT_TARGET_USD, _float)

MAX_INVESTMENT = _get_env("MAX_INVESTMENT", 2000.0, _float)
TRADING_PAIRS = _get_env("TRADING_PAIRS", "BTC/USDT,ETH/USDT", _list_str)
STRATEGY = _get_env("STRATEGY", "scalping_ema_rsi")

# --- Risk ---
MAX_RISK_PER_TRADE = _get_env("MAX_RISK_PER_TRADE", 1.0, _float)
MAX_OPEN_TRADES = _get_env("MAX_OPEN_TRADES", 5, _int)
MAX_DAILY_DRAWDOWN = _get_env("MAX_DAILY_DRAWDOWN", 5.0, _float)
RISK_REWARD_RATIO = _get_env("RISK_REWARD_RATIO", 1.5, _float)

# --- Capital ---
CAPITAL_MAX_USDT = _get_env("CAPITAL_MAX_USDT", 2000.0, _float)
POSITION_SIZE_PERCENT = _get_env("POSITION_SIZE_PERCENT", 0.01, _float)
MIN_NOTIONAL_USD = _get_env("MIN_NOTIONAL_USD", 10.0, _float)

# --- Leverage / Margin ---
LEVERAGE = _get_env("LEVERAGE", 5, _int)
MARGIN_MODE = _get_env("MARGIN_MODE", "ISOLATED")

# --- Universo / Ciclo ---
TIMEFRAME = _get_env("TIMEFRAME", "1m")
MAX_ACTIVE_SYMBOLS = _get_env("MAX_ACTIVE_SYMBOLS", 5, _int)
MAX_SYMBOLS = _get_env("MAX_SYMBOLS", 15, _int)
MIN_24H_VOLUME_USDT = _get_env("MIN_24H_VOLUME_USDT", 5000000, _float)
SLEEP_SECONDS_BETWEEN_CYCLES = _get_env("SLEEP_SECONDS_BETWEEN_CYCLES", 5, _int)
DAILY_RESET_HOUR_UTC = _get_env("DAILY_RESET_HOUR_UTC", 0, _int)

# --- Telegram ---
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID", "")

# --- Logging ---
LOG_LEVEL = _get_env("LOG_LEVEL", "INFO")

# --- Paths ---
DATA_DIR = Path("data")
LOGS_DIR = Path("logs")
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
