"""
Compatibility shim: export common names expected across the codebase.
Includes paths, API keys, risk management, and other global constants.
"""
from config import settings as _s
from pathlib import Path

# API / Exchange
API_KEY = _s.API_KEY
API_SECRET = _s.API_SECRET
USE_TESTNET = _s.USE_TESTNET
DRY_RUN = _s.DRY_RUN

BINANCE_API_KEY = API_KEY
BINANCE_API_SECRET = API_SECRET
BINANCE_TESTNET = USE_TESTNET

# Risk / sizing
MAX_INVESTMENT = getattr(_s, "MAX_INVESTMENT", None)
MAX_RISK_PER_TRADE = getattr(_s, "MAX_RISK_PER_TRADE", None)
DAILY_PROFIT_TARGET = getattr(_s, "DAILY_PROFIT_TARGET", getattr(_s, "DAILY_PROFIT_TARGET_USD", None))
CAPITAL_MAX_USDT = getattr(_s, "CAPITAL_MAX_USDT", None)
POSITION_SIZE_PERCENT = getattr(_s, "POSITION_SIZE_PERCENT", 0.02)
MAX_OPEN_TRADES = getattr(_s, "MAX_OPEN_TRADES", None)
MAX_DAILY_DRAWDOWN = getattr(_s, "MAX_DAILY_DRAWDOWN", 5.0)
RISK_REWARD_RATIO = getattr(_s, "RISK_REWARD_RATIO", 2.0)

# Leverage / margin (added to fix ImportError)
LEVERAGE = getattr(_s, "LEVERAGE", getattr(_s, "LEVERAGE", 5))

# Trading / pairs
TRADING_PAIRS = getattr(_s, "TRADING_PAIRS", [])
STRATEGY = getattr(_s, "STRATEGY", "scalping_ema_rsi")
TIMEFRAME = getattr(_s, "TIMEFRAME", "1m")
MIN_NOTIONAL_USD = getattr(_s, "MIN_NOTIONAL_USD", 10.0)
MAX_ACTIVE_SYMBOLS = getattr(_s, "MAX_ACTIVE_SYMBOLS", 5)

# Telegram
TELEGRAM_BOT_TOKEN = getattr(_s, "TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = getattr(_s, "TELEGRAM_CHAT_ID", "")

# Logging
LOG_LEVEL = getattr(_s, "LOG_LEVEL", "INFO")

# Paths
DATA_DIR = getattr(_s, "DATA_DIR", Path("data"))
LOGS_DIR = getattr(_s, "LOGS_DIR", Path("logs"))
DB_PATH = DATA_DIR / "bot_state.sqlite"  # <--- esto arregla el ImportError

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
