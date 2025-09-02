import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

MODE = os.getenv("MODE", "paper")  # "paper" o "live"

# Binance Futuros USDM Testnet
BINANCE_TESTNET = _bool(os.getenv("BINANCE_TESTNET", "true"), True)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Operación
STARTING_BALANCE_USDT = float(os.getenv("STARTING_BALANCE_USDT", "2000.0"))
_raw_pct = float(os.getenv("POSITION_SIZE_PERCENT", "1.0"))
# Interpretación: valores >=1 se tratan como porcentaje (1 = 1% => 0.01). Valores <1 como fracción.
POSITION_SIZE_PERCENT = (_raw_pct / 100.0) if _raw_pct >= 1 else _raw_pct
DAILY_PROFIT_TARGET_USD = float(os.getenv("DAILY_PROFIT_TARGET_USD", "40.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "100.0"))

# Universo y scheduling
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "15"))
MIN_24H_VOLUME_USDT = float(os.getenv("MIN_24H_VOLUME_USDT", "5000000"))  # 5M USDT
SLEEP_SECONDS_BETWEEN_CYCLES = int(os.getenv("SLEEP_SECONDS_BETWEEN_CYCLES", "5"))
DAILY_RESET_HOUR_UTC = int(os.getenv("DAILY_RESET_HOUR_UTC", "0"))  # 00:00 UTC

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Miscelánea
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DATA_DIR = os.getenv("DATA_DIR", "data")
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "crypto_bot.db"))
STATE_PATH = os.getenv("STATE_PATH", os.path.join(DATA_DIR, "state.json"))
