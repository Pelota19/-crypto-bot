import ccxt.async_support as ccxt_async
from src.config import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET
import logging

logger = logging.getLogger(__name__)

def create_binance_exchange():
    """
    Crea y devuelve una instancia async de ccxt para Binance USDM (futuros USDT).
    Quien llame debe hacer await exchange.close() al finalizar.
    """
    config = {
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_API_SECRET,
        "enableRateLimit": True,
    }
    # USDM = Futuros USDT-margined
    exchange = ccxt_async.binanceusdm(config)

    try:
        if BINANCE_TESTNET and hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(True)
            logger.info("Binance USDM sandbox (testnet) enabled")
    except Exception:
        logger.warning("Could not set sandbox mode on exchange")

    return exchange