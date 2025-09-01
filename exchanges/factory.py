"""Exchange factory for creating exchange instances."""
import ccxt.async_support as ccxt
from config.settings import EXCHANGE, API_KEY, API_SECRET, USE_TESTNET
from utils.logger import get_logger
from .binance import BinanceExchange

logger = get_logger(__name__)

def create_exchange():
    """Create and return an exchange instance based on configuration."""
    if EXCHANGE.lower() == "binance":
        return BinanceExchange(
            api_key=API_KEY,
            api_secret=API_SECRET,
            testnet=USE_TESTNET
        )
    else:
        raise ValueError(f"Unsupported exchange: {EXCHANGE}")

def get_exchange_class(exchange_name: str):
    """Get exchange class by name."""
    exchange_map = {
        "binance": BinanceExchange,
    }
    
    exchange_class = exchange_map.get(exchange_name.lower())
    if not exchange_class:
        raise ValueError(f"Unsupported exchange: {exchange_name}")
    
    return exchange_class