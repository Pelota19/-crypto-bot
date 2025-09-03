# Configuración centralizada y documentada para el bot de trading

import os
from pathlib import Path

def _bool(val: str | None, default: bool = False) -> bool:
    """
    Convierte un string de entorno en booleano.
    Permite valores: "1", "true", "yes", "on" (no sensible a mayúsculas).
    """
    if val is None:
        return default
    s = str(val).strip().lower()
    if s == "":
        return default
    return s in ("1", "true", "t", "yes", "y", "on")

# Modo de ejecución: "paper" (simulado) o "live"
MODE = os.getenv("MODE", "paper").lower()
"""Modo de operación del bot; 'paper' para simulado, 'live' para real."""

# Claves / entorno Binance
BINANCE_TESTNET = _bool(os.getenv("BINANCE_TESTNET", "true"), True)
"""Usar testnet de Binance (True) o producción (False)."""
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
"""API Key para Binance."""
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
"""API Secret para Binance."""

# Balance inicial para paper trading
STARTING_BALANCE_USDT = float(os.getenv("STARTING_BALANCE_USDT", "1000"))
"""Balance inicial en USDT para modo simulado."""

# Tamaño de posición: acepta 0.01 (=1%) o 1 (=1%) según convenga
_raw_pct = float(os.getenv("POSITION_SIZE_PERCENT", "1.0"))
POSITION_SIZE_PERCENT = (_raw_pct / 100.0) if _raw_pct >= 1 else _raw_pct
"""Porcentaje del balance destinado a cada posición."""

# Objetivos y límites diarios
DAILY_PROFIT_TARGET_USD = float(os.getenv("DAILY_PROFIT_TARGET_USD", "20.0"))
"""Meta diaria de ganancias en USD."""
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "20.0"))
"""Límite máximo de pérdida diaria en USD."""

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
"""Token del bot de Telegram para notificaciones y control."""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
"""Chat ID de Telegram para enviar mensajes."""

# Selección inteligente de pares
TOP_K_SELECTION = _bool(os.getenv("TOP_K_SELECTION", "true"), True)
"""Activar sistema de ranking top-K para elegir pares."""
MAX_ACTIVE_SYMBOLS = int(os.getenv("MAX_ACTIVE_SYMBOLS", "5"))
"""Número máximo de símbolos a operar por ciclo."""
MIN_NOTIONAL_USD = float(os.getenv("MIN_NOTIONAL_USD", "10.0"))
"""Valor mínimo de posición en USD."""

# Capital máximo permitido para trading
CAPITAL_MAX_USDT = float(os.getenv("CAPITAL_MAX_USDT", "1000.0"))
"""Capital máximo permitido para dimensionamiento de posiciones."""

# Path base del proyecto
BASE_PATH = Path(__file__).parent.parent
"""Ruta base del proyecto para cargar archivos auxiliares si se requiere."""