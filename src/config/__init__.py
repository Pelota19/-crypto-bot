# Config centralizada para el bot

import os
from pathlib import Path

def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s == "":
        return default
    return s in ("1", "true", "t", "yes", "y", "on")

# Modo de ejecución: "paper" (simulado) o "live"
MODE = os.getenv("MODE", "paper").lower()

# Claves / entorno Binance
BINANCE_TESTNET = _bool(os.getenv("BINANCE_TESTNET", "true"), True)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Balance inicial para paper trading
STARTING_BALANCE_USDT = float(os.getenv("STARTING_BALANCE_USDT", "1000"))

# Tamaño de posición: acepta 0.01 (=1%) o 1 (=1%) según convenga
_raw_pct = float(os.getenv("POSITION_SIZE_PERCENT", "1.0"))
POSITION_SIZE_PERCENT = (_raw_pct / 100.0) if _raw_pct >= 1 else _raw_pct

# Objetivos y límites diarios
DAILY_PROFIT_TARGET_USD = float(os.getenv("DAILY_PROFIT_TARGET_USD", "50.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "100.0"))

# Leverage / Margin (para LIVE; en testnet también puede aplicar)
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
MARGIN_MODE = os.getenv("MARGIN_MODE", "ISOLATED")  # ISOLATED o CROSSED

# Universo y scheduling
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "10"))
MIN_24H_VOLUME_USDT = float(os.getenv("MIN_24H_VOLUME_USDT", "5000000"))
SLEEP_SECONDS_BETWEEN_CYCLES = int(os.getenv("SLEEP_SECONDS_BETWEEN_CYCLES", "5"))
DAILY_RESET_HOUR_UTC = int(os.getenv("DAILY_RESET_HOUR_UTC", "0"))

# Selección Top-K
MAX_ACTIVE_SYMBOLS = int(os.getenv("MAX_ACTIVE_SYMBOLS", "5"))
MIN_NOTIONAL_USD = float(os.getenv("MIN_NOTIONAL_USD", "10.0"))
TOP_K_SELECTION = _bool(os.getenv("TOP_K_SELECTION", "true"), True)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING")

# Rutas de datos
ROOT = Path(__file__).resolve().parent.parent  # .../src
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "crypto_bot.db"))
STATE_PATH = os.getenv("STATE_PATH", str(DATA_DIR / "state.json"))
AI_MODEL_PATH = os.getenv("AI_MODEL_PATH", str(DATA_DIR / "ai_model.json"))

# Telegram (opcional)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")# config package
