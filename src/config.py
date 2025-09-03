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

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")