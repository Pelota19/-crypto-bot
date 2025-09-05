"""
Robust async wrapper around ccxt.async_support.binance (USDT-M Futures).

Cambios / mejoras aplicadas:
- Lee credenciales desde parámetros o desde entorno y hace .strip() para evitar espacios/saltos de línea.
- Añade opción use_testnet para forzar los endpoints de testnet.binancefuture.com.
- Activa options['adjustForTimeDifference'] para sincronizar timestamps con el servidor.
- Mantiene compatibilidad con el resto del código (métodos: fetch_all_symbols, fetch_ohlcv, create_order, etc.).
- Añade parámetro verbose para debugging de CCXT (muestra request/response).
- Añade parámetro hedge_mode (True por defecto). Si hedge_mode=True y la orden es FUTURES, el cliente
  autoinyectará positionSide ('LONG' para BUY, 'SHORT' para SELL) cuando no esté explícito en params.
- Añade fallback automático para tipos de órdenes SL/TP no válidos en Binance Futures:
  si pides 'stop_limit' o 'take_profit_limit' y Binance rechaza, reintentamos con
  'stop_market' y 'take_profit_market' respectivamente.
"""
import logging
from typing import Optional, Any, List
import os

import ccxt.async_support as ccxt
from ccxt.base.errors import BadRequest, ExchangeError, NetworkError, RequestTimeout, InvalidOrder

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        use_testnet: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
        hedge_mode: bool = True,
    ):
        """
        Constructor:
        - api_key/api_secret: si no se pasan, se leen de env BINANCE_API_KEY / BINANCE_SECRET
        - use_testnet: apunta a testnet.binancefuture.com para USDT-M futures
        - dry_run: no crea órdenes reales, devuelve objeto simulado
        - verbose: activa exchange.verbose para debug (no compartir signatures)
        - hedge_mode: si True intenta inyectar 'positionSide' en órdenes futures cuando falta.
        """
        # Leer y recortar credenciales (evita saltos de línea o espacios accidentales)
        api_key = (api_key or os.getenv("BINANCE_API_KEY") or "").strip()
        api_secret = (api_secret or os.getenv("BINANCE_SECRET") or "").strip()

        if not api_key or not api_secret:
            logger.warning("BinanceClient: api_key or api_secret empty. Private endpoints will fail if called.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = use_testnet
        self.dry_run = dry_run
        self.verbose = verbose
        self.hedge_mode = hedge_mode

        self.exchange: Optional[ccxt.binance] = None
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
                "adjustForTimeDifference": True,
            },
        }

        if self.use_testnet:
            logger.info("Binance sandbox/testnet mode enabled (USDT-M futures). Using testnet endpoints.")
            params["urls"] = {
                "api": {
                    "public": "https://testnet.binancefuture.com",
                    "private": "https://testnet.binancefuture.com",
                }
            }

        self.exchange = ccxt.binance(params)

        if self.verbose:
            try:
                self.exchange.verbose = True
            except Exception:
                pass

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
            out: List[str] = []
            for s in info.get("symbols", []):
                try:
                    if (
                        s.get("contractType") == "PERPETUAL"
                        and s.get("quoteAsset") == "USDT"
                        and s.get("status") == "TRADING"
                    ):
                        base = s.get("baseAsset")
                        quote = s.get("quoteAsset")
                        if base and quote:
                            out.append(f"{base}/{quote}")
                except Exception:
                    continue
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

        try:
            await self._ensure_exchange()
            markets = self.exchange.markets or {}
            return [
                sym for sym, m in markets.items()
                if isinstance(sym, str)
                and sym.endswith("/USDT")
                and m.get("type") == "future"
                and m.get("active", True)
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
            if not ohlcv:
                logger.debug("fetch_ohlcv returned empty for %s %s", symbol, timeframe)
                return None
            for i in range(len(ohlcv)):
                try:
                    ohlcv[i] = [float(x) for x in ohlcv[i]]
                except Exception:
                    pass
            return ohlcv
        except (BadRequest, NetworkError, RequestTimeout, ExchangeError) as e:
            logger.warning("fetch_ohlcv failed for %s %s: %s", symbol, timeframe, e)
            return None
        except Exception as e:
            logger.exception("fetch_ohlcv unexpected error for %s %s: %s", symbol, timeframe, e)
            return None

    async def fetch_24h_change(self, symbol: str) -> Optional[float]:
        ticker = await self.fetch_ticker(symbol)
        if ticker and "percentage" in ticker:
            try:
                return abs(float(ticker["percentage"]))
            except Exception:
                return None
        return None

    async def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[dict] = None,
    ) -> Any:
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
            # defensive copy so we don't mutate caller dict
            params = dict(params or {})

            # Determinar si el mercado es FUTURE (usualmente para USDT-M)
            market_type = None
            try:
                if self.exchange and getattr(self.exchange, "markets", None):
                    m = self.exchange.markets.get(symbol)
                    if m:
                        market_type = m.get("type")
            except Exception:
                market_type = None

            if not market_type:
                try:
                    market_type = getattr(self.exchange, "options", {}).get("defaultType")
                except Exception:
                    market_type = None

            # Auto-inject positionSide only when hedge_mode=True and estamos en futuros
            if self.hedge_mode and market_type == "future" and "positionSide" not in params:
                params["positionSide"] = "LONG" if side.upper() == "BUY" else "SHORT"
                logger.debug("Auto-injected positionSide=%s for %s %s", params["positionSide"], side, symbol)

            # Primary attempt
            try:
                return await self.exchange.create_order(symbol, type, side, amount, price, params or {})
            except InvalidOrder as exc:
                # si Binance rechaza el tipo de orden, intentar fallback para SL/TP en futures
                msg = str(exc)
                logger.debug("create_order InvalidOrder: %s", msg)
                fallback_map = {
                    "stop_limit": "stop_market",
                    "take_profit_limit": "take_profit_market",
                    # otros mapeos posibles:
                    "stop_loss_limit": "stop_market",
                    "take_profit": "take_profit_market",
                }
                requested = (type or "").lower()
                if requested in fallback_map:
                    new_type = fallback_map[requested]
                    logger.warning("Order type %s rejected by exchange for %s -> retrying with %s", type, symbol, new_type)
                    try:
                        return await self.exchange.create_order(symbol, new_type, side, amount, price, params or {})
                    except Exception as exc2:
                        logger.exception("Retry with %s also failed for %s: %s", new_type, symbol, exc2)
                        raise
                # si no hay fallback o el fallback falló, re-lanzar
                raise

        except Exception as e:
            logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
            try:
                logger.debug("Last http response: %s", getattr(self.exchange, 'last_http_response', None))
            except Exception:
                pass
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
