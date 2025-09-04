import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "True").lower() in ("true", "1")
POSITION_SIZE_PERCENT = 0.02
MAX_OPEN_TRADES = 5
CAPITAL_MAX_USDT = 2000.0
TRADING_PAIRS = ["BTC/USDT", "ETH/USDT"]

DATA_DIR = Path("data")
LOGS_DIR = Path("logs")
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
