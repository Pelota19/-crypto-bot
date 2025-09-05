import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env si existe
load_dotenv()

# --- Exchange / Credenciales ---
API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()
USE_TESTNET = os.getenv("USE_TESTNET", "True").lower() in ("true", "1", "yes")
DRY_RUN = os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes")

# --- Trading / Risk ---
DAILY_PROFIT_TARGET = float(os.getenv("DAILY_PROFIT_TARGET_USD", "50.0"))
MAX_INVESTMENT = float(os.getenv("MAX_INVESTMENT", "2000.0"))
POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", "0.01"))  # decimal (1% = 0.01)
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "5"))
MIN_NOTIONAL_USD = float(os.getenv("MIN_NOTIONAL_USD", "10.0"))
RISK_REWARD_RATIO = float(os.getenv("RISK_REWARD_RATIO", "1.5"))

# --- Leverage / Margin ---
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
MARGIN_MODE = os.getenv("MARGIN_MODE", "ISOLATED")

# --- Hedge / One-way mode (binance futures) ---
# Si HEDGE_MODE=True asumimos DUAL (Hedge mode) y el bot enviará positionSide en las órdenes.
# Si HEDGE_MODE=False asumimos One-way (BOTH) y el bot NO inyectará positionSide.
HEDGE_MODE = os.getenv("HEDGE_MODE", "True").lower() in ("true", "1", "yes")

# --- Universo y ciclo ---
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
MAX_ACTIVE_SYMBOLS = int(os.getenv("MAX_ACTIVE_SYMBOLS", "5"))
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "15"))
MIN_24H_VOLUME_USDT = float(os.getenv("MIN_24H_VOLUME_USDT", "5000000"))
SLEEP_SECONDS_BETWEEN_CYCLES = int(os.getenv("SLEEP_SECONDS_BETWEEN_CYCLES", "5"))
DAILY_RESET_HOUR_UTC = int(os.getenv("DAILY_RESET_HOUR_UTC", "0"))

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# --- Logging / Misc ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Defaults / data dirs ---
DATA_DIR = Path("data")
LOGS_DIR = Path("logs")
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
