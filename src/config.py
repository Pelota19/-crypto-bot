import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# Trading params
POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", "0.01"))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "3"))
DAILY_PROFIT_TARGET = float(os.getenv("DAILY_PROFIT_TARGET", "20"))
MIN_NOTIONAL_USD = float(os.getenv("MIN_NOTIONAL_USD", "5"))
LEVERAGE = int(os.getenv("LEVERAGE", "10"))

# Hedge mode
FORCE_HEDGE_MODE = os.getenv("FORCE_HEDGE_MODE", "true").lower() == "true"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
