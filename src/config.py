# Compatibility shim: export common names expected across the codebase.
# Import from config.settings (single source of truth).
from config import settings as _s

# Primary settings (keep original names)
API_KEY = _s.API_KEY
API_SECRET = _s.API_SECRET
USE_TESTNET = _s.USE_TESTNET
DRY_RUN = _s.DRY_RUN

# Legacy/alternate names used by some scripts
BINANCE_API_KEY = API_KEY
BINANCE_API_SECRET = API_SECRET
BINANCE_TESTNET = USE_TESTNET

# Risk / sizing
MAX_INVESTMENT = _s.MAX_INVESTMENT
MAX_RISK_PER_TRADE = _s.MAX_RISK_PER_TRADE
DAILY_PROFIT_TARGET = _s.DAILY_PROFIT_TARGET
CAPITAL_MAX_USDT = _s.CAPITAL_MAX_USDT

# Logging
LOG_LEVEL = _s.LOG_LEVEL

# Paths
DATA_DIR = _s.DATA_DIR
LOGS_DIR = _s.LOGS_DIR

# Telegram
TELEGRAM_BOT_TOKEN = _s.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = _s.TELEGRAM_CHAT_ID
