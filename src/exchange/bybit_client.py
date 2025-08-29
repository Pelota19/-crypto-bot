import ccxt.async_support as ccxt_async
from src.config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_TESTNET, BYBIT_DEFAULT_TYPE
import logging

logger = logging.getLogger(__name__)

def create_bybit_exchange():
    """
    Create and return an async ccxt bybit exchange instance.
    Caller should await exchange.close() when done.
    """
    config = {
        "apiKey": BYBIT_API_KEY,
        "secret": BYBIT_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": BYBIT_DEFAULT_TYPE},
    }
    exchange = ccxt_async.bybit(config)

    try:
        if BYBIT_TESTNET and hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(True)
            logger.info("Bybit sandbox mode enabled")
    except Exception:
        logger.warning("Could not set sandbox mode on exchange")

    return exchange
