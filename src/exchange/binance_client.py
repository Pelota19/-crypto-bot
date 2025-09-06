# src/exchange/binance_client.py
"""
Wrapper robusto y asíncrono sobre ccxt.async_support.binance (USDT-M Futures).

Incluye:
- Inicialización segura (_ensure_exchange)
- adjust_amount_to_step para roundear qty al stepSize del mercado
- create_order con sanitización y retries (quita reduceOnly si falla, fallback de tipos)
- fetch_trades_for_order para obtener fills asociados a un orderId
- fetch_ohlcv / fetch_ticker / fetch_all_symbols / fetch_24h_change
- cancel_order / fetch_order / fetch_open_orders
- dry_run support (logs en lugar de enviar órdenes)
"""
import asyncio
import logging
import math
import os
from typing import Optional, Any, Dict, List

import ccxt.async_support as ccxt
from ccxt.base.errors import InvalidOrder

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        use_testnet: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
        hedge_mode: bool = True,
    ):
        self.api_key = (api_key or os.getenv("API_KEY") or "").strip()
        self.api_secret = (api_secret or os.getenv("API_SECRET") or "").strip()
        self.use_testnet = use_testnet or (os.getenv("USE_TESTNET", "False").lower() in ("1", "true", "yes"))
        self.dry_run = dry_run or (os.getenv("DRY_RUN", "False").lower() in ("1", "true", "yes"))
        self.verbose = verbose
        self.hedge_mode = hedge_mode or (os.getenv("HEDGE_MODE", "False").lower() in ("1", "true", "yes"))

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
        # use testnet endpoints if requested
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

    async def close(self):
        try:
            if self.exchange:
                await self.exchange.close()
        except Exception:
            logger.debug("Error closing exchange client", exc_info=True)

    async def fetch_all_symbols(self) -> List[str]:
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
            return out
        except Exception:
            # fallback to loaded markets
            try:
                markets = self.exchange.markets or {}
                return [
                    sym for sym, m in markets.items()
                    if isinstance(sym, str)
                    and sym.endswith("/USDT")
                    and m.get("type") == "future"
                    and m.get("active", True)
                ]
            except Exception:
                return []

    async def fetch_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception:
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", since: Optional[int] = None, limit: int = 100):
        await self._ensure_exchange()
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
            if not ohlcv:
                return None
            # ensure numeric types
            for i in range(len(ohlcv)):
                try:
                    ohlcv[i] = [float(x) for x in ohlcv[i]]
                except Exception:
                    pass
            return ohlcv
        except Exception:
            return None

    async def fetch_24h_change(self, symbol: str) -> Optional[float]:
        ticker = await self.fetch_ticker(symbol)
        if not ticker:
            return None
        # ccxt may include 'percentage' or info.priceChangePercent
        try:
            if "percentage" in ticker:
                return abs(float(ticker["percentage"]))
            info = ticker.get("info", {}) if isinstance(ticker, dict) else {}
            return abs(float(info.get("priceChangePercent") or 0.0))
        except Exception:
            return None

    async def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[dict]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception:
            return None

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_open_orders(symbol)
        except Exception:
            return []

    def adjust_amount_to_step(self, symbol: str, amount: float) -> float:
        """
        Ajusta cantidad al stepSize/precision del mercado (round down).
        """
        try:
            if amount is None:
                return 0.0
            amount = float(amount)
            if not self.exchange or not getattr(self.exchange, "markets", None):
                return amount
            info = self.exchange.markets.get(symbol)
            if not info:
                return amount
            # Try to get amount precision
            precision = info.get("precision", {}) or {}
            step = None
            if isinstance(precision, dict) and precision.get("amount") is not None:
                step = float(precision.get("amount"))
            else:
                limits = info.get("limits", {}) or {}
                amt_lim = limits.get("amount", {}) or {}
                step = None
                for key in ("stepSize", "min", "step"):
                    if key in amt_lim and amt_lim.get(key):
                        try:
                            step = float(amt_lim.get(key))
                            break
                        except Exception:
                            continue
            if not step or step <= 0:
                return amount
            steps = math.floor(amount / step)
            adjusted = float(steps * step) if steps > 0 else 0.0
            return adjusted
        except Exception as e:
            logger.debug("adjust_amount_to_step failed for %s: %s", symbol, e)
            return amount

    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Wrapper create_order con:
          - dry_run support (si self.dry_run True, no pide a la API)
          - auto-inyección de positionSide cuando hedge_mode
          - sanitización y reintentos comunes:
              * captura InvalidOrder -> intenta fallback_map (stop_limit->stop_market, take_profit_limit->take_profit_market)
              * en reintento quita reduceOnly/reduce_only/reduceonly si aparecen
        Propaga excepciones si todo falla.
        """
        await self._ensure_exchange()
        params = dict(params or {})
        # sanitize boolean-like strings
        for k in ("reduceOnly", "reduce_only", "reduceonly"):
            if k in params and isinstance(params[k], str):
                params[k] = params[k].lower() in ("1", "true", "yes")

        # dry-run: log and return fake order
        if self.dry_run:
            logger.info("DRY RUN create_order %s %s %s @%s qty=%s params=%s", symbol, type, side, price, amount, params)
            return {
                "id": f"dryrun-{symbol.replace('/','')}-{int(math.floor(amount))}",
                "symbol": symbol,
                "type": type,
                "side": side,
                "price": price,
                "amount": amount,
                "status": "closed",
                "filled": amount,
                "info": {"dry_run": True},
            }

        # positionSide autoinject for hedge-mode futures (ensure proper casings)
        try:
            market_type = None
            if self.exchange and getattr(self.exchange, "markets", None):
                m = self.exchange.markets.get(symbol)
                if m:
                    market_type = m.get("type")
        except Exception:
            market_type = None

        if self.hedge_mode and market_type == "future" and "positionSide" not in params:
            # side may be 'buy'/'sell' or 'BUY'/'SELL'
            params["positionSide"] = "LONG" if str(side).lower() in ("buy", "b", "long") else "SHORT"

        try:
            return await self.exchange.create_order(symbol, type, side, amount, price, params or {})
        except InvalidOrder as exc:
            msg = str(exc)
            logger.debug("create_order InvalidOrder for %s %s %s: %s", symbol, type, side, msg)
            # fallback mapping for common unsupported types
            fallback_map = {
                "stop_limit": "stop_market",
                "take_profit_limit": "take_profit_market",
                "stop_loss_limit": "stop_market",
                "take_profit": "take_profit_market",
            }
            requested = (type or "").lower()
            if requested in fallback_map:
                new_type = fallback_map[requested]
                params_retry = dict(params or {})
                # remove reduceOnly variants (can cause -1106)
                for k in ("reduceOnly", "reduce_only", "reduceonly"):
                    params_retry.pop(k, None)
                logger.warning("Order type %s rejected by exchange for %s -> retrying with %s (sanitized params)", type, symbol, new_type)
                try:
                    return await self.exchange.create_order(symbol, new_type, side, amount, price, params_retry or {})
                except Exception as exc2:
                    logger.exception("Retry with %s also failed for %s: %s", new_type, symbol, exc2)
                    raise
            # if no fallback applicable, re-raise
            raise
        except Exception as e:
            # Try to handle reduceOnly related errors in other exception types (e.g., BadRequest messages)
            msg = str(e).lower()
            if "reduceonly" in msg or "-1106" in msg:
                params_retry = dict(params or {})
                for k in ("reduceOnly", "reduce_only", "reduceonly"):
                    params_retry.pop(k, None)
                try:
                    logger.warning("Retrying create_order without reduceOnly due to error: %s", e)
                    return await self.exchange.create_order(symbol, type, side, amount, price, params_retry or {})
                except Exception as e2:
                    logger.exception("Retry without reduceOnly failed for %s: %s", symbol, e2)
                    raise
            logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
            raise

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Any:
        await self._ensure_exchange()
        if self.dry_run:
            logger.info("DRY RUN cancel_order %s %s", order_id, symbol)
            return {"id": order_id, "status": "canceled", "info": {"dry_run": True}}
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.warning("cancel_order failed for %s (%s): %s", order_id, symbol, e)
            return None

    async def fetch_trades_for_order(self, order_id: str, symbol: Optional[str] = None) -> List[dict]:
        """
        Intenta obtener los trades (fills) asociados a un orderId.
        Usa exchange.fetch_my_trades(symbol) y filtra por orderId en trade['info'] o trade.get('order').
        Retorna lista de trades (puede estar vacía).
        """
        await self._ensure_exchange()
        if not order_id:
            return []
        try:
            # dry-run -> no trades
            if self.dry_run:
                return []

            trades = []
            try:
                if symbol:
                    trades = await self.exchange.fetch_my_trades(symbol)
                else:
                    trades = await self.exchange.fetch_my_trades()
            except Exception as e:
                logger.debug("fetch_my_trades initial call failed: %s", e)
                try:
                    trades = await self.exchange.fetch_my_trades()
                except Exception as e2:
                    logger.warning("fetch_my_trades failed: %s", e2)
                    return []

            out = []
            for t in trades or []:
                try:
                    info = t.get("info", {}) or {}
                    if str(t.get("order") or info.get("orderId") or info.get("orderIdStr") or "") == str(order_id):
                        out.append(t)
                except Exception:
                    continue
            return out
        except Exception as e:
            logger.exception("fetch_trades_for_order failed for %s %s: %s", order_id, symbol, e)
            return []
