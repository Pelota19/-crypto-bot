# Configuración simple basada en variables de entorno y rutas por defecto.
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AI_MODEL_PATH = str(DATA_DIR / "ai_model.json")

# Exchange / trading defaults (placeholders)
EXCHANGE = {
    "name": os.environ.get("EXCHANGE_NAME", "paper_exchange"),
}

# Telegram (opcional)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Risk defaults
DEFAULT_RISK_PCT = float(os.environ.get("DEFAULT_RISK_PCT", "0.01"))  # 1% por operación

_raw_pct = float(os.getenv("POSITION_SIZE_PERCENT", "1.0"))
# Interpretación: valores >=1 se tratan como porcentaje (1 = 1% => 0.01). Valores <1 como fracción.
POSITION_SIZE_PERCENT = (_raw_pct / 100.0) if _raw_pct >= 1 else _raw_pct

# Objetivos diarios
DAILY_PROFIT_TARGET_USD = float(os.getenv("DAILY_PROFIT_TARGET_USD", "50.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "100.0"))

# Leverage/Margin (para LIVE en testnet)
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
MARGIN_MODE = os.getenv("MARGIN_MODE", "ISOLATED")  # ISOLATED o CROSSED

# Universo y scheduling
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "10"))
MIN_24H_VOLUME_USDT = float(os.getenv("MIN_24H_VOLUME_USDT", "5000000"))  # 5M USDT
SLEEP_SECONDS_BETWEEN_CYCLES = int(os.getenv("SLEEP_SECONDS_BETWEEN_CYCLES", "5"))
DAILY_RESET_HOUR_UTC = int(os.getenv("DAILY_RESET_HOUR_UTC", "0"))  # 00:00 UTC

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Top-K symbol selection
MAX_ACTIVE_SYMBOLS = int(os.getenv("MAX_ACTIVE_SYMBOLS", "5"))
MIN_NOTIONAL_USD = float(os.getenv("MIN_NOTIONAL_USD", "10.0"))
TOP_K_SELECTION = _bool(os.getenv("TOP_K_SELECTION", "true"), True)

# Miscelánea
# Por defecto WARNING para no spamear la shell. Telegram será el canal principal.
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING")
DATA_DIR = os.getenv("DATA_DIR", "data")
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "crypto_bot.db"))
STATE_PATH = os.getenv("STATE_PATH", os.path.join(DATA_DIR, "state.json"))
AI_MODEL_PATH = os.getenv("AI_MODEL_PATH", os.path.join(DATA_DIR, "ai_model.json"))