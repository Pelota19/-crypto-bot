import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _get_env(name, default=None, cast=str):
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return cast(val)
    except:
        return default

def _bool(v): return str(v).lower() in ("true", "1", "yes", "on")
def _float(v): return float(v)
def _int(v): return int(v)
def _list_str(v): return [x.strip() for x in v.split(",") if x.strip()]

# Exchange
API_KEY = _get_env("BINANCE_API_KEY", "")
API_SECRET = _get_env("BINANCE_API_SECRET", "")
USE_TESTNET = _get_env("USE_TESTNET", True, _bool)

# Execution
DRY_RUN = _get_env("DRY_RUN", False, _bool)
ORDER_TIMEOUT = _get_env("ORDER_TIMEOUT", 30, _int)

# Trading
DAILY_PROFIT_TARGET = _get_env("DAILY_PROFIT_TARGET", 50.0, _float)
MAX_INVESTMENT = _get_env("MAX_INVESTMENT", 2000.0, _float)
TRADING_PAIRS = _get_env("TRADING_PAIRS", "BTC/USDT,ETH/USDT", _list_str)
POSITION_SIZE_PERCENT = 0.02
MAX_RISK_PER_TRADE = _get_env("MAX_RISK_PER_TRADE", 1.0, _float)
MAX_OPEN_TRADES = _get_env("MAX_OPEN_TRADES", 5, _int)
CAPITAL_MAX_USDT = _get_env("CAPITAL_MAX_USDT", 2000.0, _float)

# Logging
LOG_LEVEL = _get_env("LOG_LEVEL", "INFO")

# Telegram
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID", "")

# Paths
DATA_DIR = Path("data")
LOGS_DIR = Path("logs")
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
