import os
import logging
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


class BinanceClient:
    """
    Cliente CCXT para Binance con soporte opcional para Testnet (futuros USDT-M).
    - Lee credenciales del entorno si no se pasan explícitamente.
    - Hace strip() a apiKey/secret para evitar espacios/saltos de línea.
    - Soporta use_testnet=True para apuntar a testnet.binancefuture.com.
    - Ajusta la diferencia de tiempo automáticamente.
    """

    def __init__(self, api_key: str | None = None, api_secret: str | None = None,
                 use_futures: bool = True, use_testnet: bool = False, verbose: bool = False):
        api_key = (api_key or os.getenv("BINANCE_API_KEY") or "").strip()
        api_secret = (api_secret or os.getenv("BINANCE_SECRET") or "").strip()
        if not api_key or not api_secret:
            raise ValueError("Binance API key/secret missing. Export BINANCE_API_KEY and BINANCE_SECRET.")

        options = {
            "defaultType": "future" if use_futures else "spot",
            "adjustForTimeDifference": True,
        }

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": options,
        }

        if use_testnet:
            # Futuros USDT-M testnet base URL
            config["urls"] = {
                "api": {
                    "public": "https://testnet.binancefuture.com",
                    "private": "https://testnet.binancefuture.com",
                }
            }

        self.exchange = ccxt.binance(config)

        if verbose:
            # Muestra request/response en stdout/stderr (local debug). No compartas signature/secret.
            self.exchange.verbose = True

    async def initialize(self):
        """
        Carga mercados y fuerza ajuste de tiempo.
        Llamar antes de ejecutar operaciones privadas.
        """
        try:
            await self.exchange.load_markets()
            logger.info("Binance client initialized: markets loaded and time adjusted.")
        except Exception as e:
            logger.exception("Failed to initialize Binance client: %s", e)
            raise

    async def fetch_balance(self):
        try:
            return await self.exchange.fetch_balance()
        except Exception as e:
            logger.exception("fetch_balance failed: %s", getattr(e, 'args', e))
            raise

    async def create_order(self, symbol: str, type_: str, side: str, amount: float, price: float | None = None,
                           params: dict | None = None):
        """
        Wrapper simple de create_order. params puede incluir {"test": True} para endpoints de prueba.
        """
        try:
            return await self.exchange.create_order(symbol, type_, side, amount, price, params or {})
        except Exception as e:
            logger.exception("create_order failed for %s %s %s %s: %s", symbol, type_, side, amount, getattr(e, 'args', e))
            try:
                logger.debug("Last http response: %s", getattr(self.exchange, 'last_http_response', None))
            except Exception:
                pass
            raise

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
                
