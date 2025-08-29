import os
from dotenv import load_dotenv

load_dotenv()

BYBIT_MODE = os.getenv("BYBIT_MODE", "paper").lower()  # 'paper' or 'live'
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() in ("1", "true", "yes")
BYBIT_DEFAULT_TYPE = os.getenv("BYBIT_DEFAULT_TYPE", "swap")

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

STARTING_BALANCE_USDT = float(os.getenv("STARTING_BALANCE_USDT", "1000.0"))
POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", "1.0")) / 100.0
DAILY_PROFIT_TARGET_USD = float(os.getenv("DAILY_PROFIT_TARGET_USD", "40.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "100.0"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
