import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        use_testnet: bool = False,
        enable_rate_limit: bool = True,
        dry_run: bool = False,
        **kwargs,
    ):
        """
        Compatible wrapper around ccxt.binance (async) for Binance Futures.
        - Accepts dry_run for backwards compatibility (no-op simulation mode).
        - Accepts extra kwargs to avoid unexpected-arg errors.
        - Uses futures (USDT-M) by default.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = bool(use_testnet)
        self.enable_rate_limit = bool(enable_rate_limit)
        self.dry_run = bool(dry_run)
        self.exchange: Optional[ccxt.binance] = None
        self._dual_position_mode: Optional[bool] = None
        self._init_lock = asyncio.Lock()

    def set_dry_run(self, enabled: bool) -> None:
        self.dry_run = bool(enabled)

    async def _ensure_exchange(self) -> None:
        if self.exchange is not None:
            return
        async with self._init_lock:
            if self.exchange is not None:
                return
            params = {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": self.enable_rate_limit,
                "options": {
                    "defaultType": "future",
                    "adjustForTimeDifference": True,
                },
            }
            if self.use_testnet:
                params["urls"] = {
                    "api": {
                        "public": "https://testnet.binancefuture.com",
                        "private": "https://testnet.binancefuture.com",
                        "fapiPublic": "https://testnet.binancefuture.com",
                        "fapiPrivate": "https://testnet.binancefuture.com",
                    }
                }

            self.exchange = ccxt.binance(params)

            try:
                if hasattr(self.exchange, "set_sandbox_mode"):
                    try:
                        self.exchange.set_sandbox_mode(self.use_testnet)
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                await self.exchange.load_markets()
            except Exception as e:
                logger.debug("load_markets failed during init: %s", e)

    async def close(self) -> None:
        if self.exchange:
            try:
                await self.exchange.close()
            except Exception:
                pass
            self.exchange = None

    async def fetch_balance(self) -> Dict[str, Any]:
        await self._ensure_exchange()
        return await self.exchange.fetch_balance()

    async def fetch_time(self) -> Optional[int]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_time()
        except Exception:
            try:
                if hasattr(self.exchange, "fapiPublicGetTime"):
                    info = await self.exchange.fapiPublicGetTime()
                    if isinstance(info, dict):
                        return int(info.get("serverTime", info.get("time", 0)))
            except Exception:
                pass
        return None

    async def fetch_markets(self) -> Dict[str, Any]:
        """
        Ensure markets are loaded and return the markets dict (ccxt format).
        """
        await self._ensure_exchange()
        # load_markets again to be safe (ccxt caches it but this is cheap when enabled)
        try:
            await self.exchange.load_markets(reload=False)
        except Exception:
            try:
                await self.exchange.load_markets()
            except Exception:
                pass
        return getattr(self.exchange, "markets", {})

    async def fetch_all_symbols(self) -> List[str]:
        """
        Return a list of available market symbols in CCXT format (e.g. 'BTC/USDT').
        This method exists because unified_main.py expects it.
        """
        markets = await self.fetch_markets()
        # ccxt uses dict keys as symbol strings
        if isinstance(markets, dict):
            return sorted(list(markets.keys()))
        return []

    async def _is_dual_position_mode(self) -> bool:
        if self._dual_position_mode is not None:
            return self._dual_position_mode

        await self._ensure_exchange()
        val = False
        try:
            resp = await self.exchange.request("positionSide/dual", "fapiPrivate", "GET", {})
            if isinstance(resp, dict):
                v = resp.get("dualSidePosition")
                val = v in (True, "true", "True", "1", 1)
        except Exception as e:
            logger.debug("Could not query positionSide/dual: %s", e)
            val = False

        self._dual_position_mode = bool(val)
        logger.debug("dual_position_mode=%s", self._dual_position_mode)
        return self._dual_position_mode

    async def refresh_position_mode_cache(self) -> bool:
        self._dual_position_mode = None
        return await self._is_dual_position_mode()

    async def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: Optional[float] = None,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Wrapper around exchange.create_order that:
         - ensures positionSide matches account mode (hedge vs one-way)
         - respects dry_run by returning a simulated order instead of calling the API
        """
        await self._ensure_exchange()
        params = dict(params or {})

        try:
            try:
                dual = await self._is_dual_position_mode()
            except Exception:
                dual = False

            side_l = (side or "").lower() if isinstance(side, str) else None

            if dual:
                if "positionSide" not in params:
                    if side_l == "buy":
                        params["positionSide"] = "LONG"
                    elif side_l == "sell":
                        params["positionSide"] = "SHORT"
                else:
                    try:
                        ps = str(params.get("positionSide")).upper()
                        if ps in ("LONG", "SHORT", "BOTH"):
                            params["positionSide"] = ps
                    except Exception:
                        pass
            else:
                if "positionSide" in params:
                    params.pop("positionSide", None)

            if self.dry_run:
                ts = int(time.time() * 1000)
                fake_id = f"dryrun-{ts}"
                logger.info("dry_run active: simulating create_order %s %s %s %s @ %s params=%s", symbol, type, side, amount, price, params)
                simulated = {
                    "info": {
                        "orderId": fake_id,
                        "symbol": symbol.replace("/", ""),
                        "status": "NEW",
                        "price": str(price) if price is not None else "0",
                        "origQty": str(amount) if amount is not None else "0",
                        "executedQty": "0.000",
                        "side": side.upper(),
                        "positionSide": params.get("positionSide"),
                    },
                    "id": fake_id,
                    "clientOrderId": f"dry-{fake_id}",
                    "timestamp": ts,
                    "datetime": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts / 1000.0)) + "Z",
                    "symbol": f"{symbol}:USDT",
                    "type": type,
                    "timeInForce": params.get("timeInForce", "GTC"),
                    "side": side.lower(),
                    "price": price,
                    "amount": amount,
                    "filled": 0.0,
                    "remaining": amount or 0.0,
                    "status": "open" if (amount and amount > 0) else "canceled",
                }
                return simulated

            result = await self.exchange.create_order(symbol, type, side, amount, price, params or {})
            return result

        except Exception as e:
            try:
                logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
            except Exception:
                pass
            raise

    def get_last_request_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        if not self.exchange:
            return info
        try:
            req = getattr(self.exchange, "last_http_request", None) or getattr(self.exchange, "last_request", None)
            resp = getattr(self.exchange, "last_http_response", None) or getattr(self.exchange, "last_response", None)
            info["last_request"] = req
            info["last_response"] = resp
        except Exception:
            pass
        return info
