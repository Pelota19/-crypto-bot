"""
Robust async wrapper around ccxt.async_support.binance (USDT-M Futures).

- Testnet bien configurado para USDT-M (fapi endpoints).
- fetch_all_symbols() usa fapiPublicGetExchangeInfo para traer todos los
  símbolos PERPETUAL/USDT en estado TRADING, devuelve 'BASE/USDT'.
- Manejo de errores y cierre limpio.
"""
import logging
from typing import Optional, Any, List

import ccxt.async_support as ccxt
from ccxt.base.errors import BadRequest, ExchangeError, NetworkError, RequestTimeout

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key: str = None, api_secret: str = None, use_testnet: bool = False, dry_run: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = use_testnet
        self.dry_run = dry_run
        self.exchange = None
        self._initialized = False

    async def _ensure_exchange(self):
        if self._initialized and self.exchange:
            return

        params = {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "warnOnFetchOHLCVLimitArgument": False,
            },
        }

        if self.use_testnet:
            logger.info("Binance sandbox mode enabled (USDT-M fapi testnet)")
            params["urls"] = {
                "api": {
                    "fapiPublic": "https://testnet.binancefuture.com/fapi/v1",
                    "fapiPrivate": "https://testnet.binancefuture.com/fapi/v1",
                }
            }

        self.exchange = ccxt.binance(params)
        try:
            if hasattr(self.exchange, "set_sandbox_mode"):
                self.exchange.set_sandbox_mode(self.use_testnet)
        except Exception:
            pass

        try:
            await self.exchange.load_markets()
        except Exception as e:
            logger.warning("Warning loading markets for BinanceClient: %s", e)

        self._initialized = True

    async def _fetch_all_usdt_perpetual_symbols_via_raw(self) -> List[str]:
        await self._ensure_exchange()
        try:
            info = await self.exchange.fapiPublicGetExchangeInfo()
            out = []
            for s in info.get("symbols", []):
                try:
                    if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
                        base = s.get("baseAsset")
                        quote = s.get("quoteAsset")
                        if base and quote:
                            out.append(f"{base}/{quote}")
                except Exception:
                    continue
            # quitar duplicados por si acaso
            out = sorted(list(set(out)))
            logger.info("Símbolos detectados en Binance (USDT-M PERPETUAL): %s", out)
            return out
        except Exception as e:
            logger.warning("No se pudieron obtener símbolos PERPETUAL via fapiPublicGetExchangeInfo: %s", e)
            return []

    async def fetch_all_symbols(self) -> List[str]:
        syms = await self._fetch_all_usdt_perpetual_symbols_via_raw()
        if syms:
            return syms
        # fallback
        try:
            await self._ensure_exchange()
            markets = self.exchange.markets or {}
            return [
                sym for sym, m in markets.items()
                if isinstance(sym, str) and sym.endswith("/USDT") and m.get("type") == "future" and m.get("active", True)
            ]
        except Exception as e:
            logger.warning("fetch_all_symbols fallback failed: %s", e)
            return []

    async def fetch_ticker(self, symbol: str):
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_ticker(symbol)
        except (BadRequest, NetworkError, RequestTimeout, ExchangeError) as e:
            logger.warning("fetch_ticker failed for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.exception("fetch_ticker unexpected error for %s: %s", symbol, e)
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", since: Optional[int] = None, limit: int = 100):
        await self._ensure_exchange()
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
            return ohlcv if ohlcv else None
        except (BadRequest, NetworkError, RequestTimeout, ExchangeError) as e:
            logger.warning("fetch_ohlcv failed for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.exception("fetch_ohlcv unexpected error for %s: %s", symbol, e)
            return None

    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, params: Optional[dict] = None) -> Any:
        await self._ensure_exchange()
        if self.dry_run:
            logger.info("DRY RUN create_order %s %s %s @%s qty=%s params=%s", symbol, type, side, price, amount, params)
            return {
                "id": "dryrun-" + symbol.replace('/', ''),
                "symbol": symbol,
                "type": type,
                "side": side,
                "price": price,
                "amount": amount,
                "status": "open",
                "info": {"dry_run": True}
            }
        try:
            return await self.exchange.create_order(symbol, type, side, amount, price, params or {})
        except Exception as e:
            logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
            raise

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.warning("fetch_open_orders failed for %s: %s", symbol, e)
            return []

    async def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[dict]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.warning("fetch_order failed for %s (%s): %s", order_id, symbol, e)
            return None

    async def close(self):
        try:
            if self.exchange:
                await self.exchange.close()
        except Exception:
            logger.debug("Error closing exchange client", exc_info=True)
