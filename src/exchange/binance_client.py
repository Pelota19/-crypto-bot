import logging
from typing import Optional, Any, List
import os

import ccxt.async_support as ccxt
from ccxt.base.errors import BadRequest, ExchangeError, NetworkError, RequestTimeout

from src.config import LEVERAGE, FORCE_HEDGE_MODE

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        use_testnet: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        api_key = (api_key or os.getenv("BINANCE_API_KEY") or "").strip()
        api_secret = (api_secret or os.getenv("BINANCE_SECRET") or "").strip()

        if not api_key or not api_secret:
            logger.warning("BinanceClient: api_key or api_secret empty.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = use_testnet
        self.dry_run = dry_run
        self.verbose = verbose

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
            logger.info("Binance TESTNET mode enabled (USDT-M futures).")
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
            logger.warning("Warning loading markets: %s", e)

        if FORCE_HEDGE_MODE:
            try:
                await self.exchange.fapiPrivatePostPositionSideDual({"dualSidePosition": "true"})
                logger.info("Hedge Mode activado automáticamente.")
            except Exception as e:
                logger.warning("No se pudo activar Hedge Mode automáticamente: %s", e)

        self._initialized = True

    async def fetch_all_symbols(self) -> List[str]:
        await self._ensure_exchange()
        try:
            info = await self.exchange.fapiPublicGetExchangeInfo()
            return [
                f"{s['baseAsset']}/{s['quoteAsset']}"
                for s in info.get("symbols", [])
                if s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
            ]
        except Exception as e:
            logger.warning("fetch_all_symbols failed: %s", e)
            return []

    async def fetch_ticker(self, symbol: str):
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.warning("fetch_ticker failed %s: %s", symbol, e)
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe="1m", since=None, limit=100):
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        except Exception as e:
            logger.warning("fetch_ohlcv failed %s %s: %s", symbol, timeframe, e)
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
        params = params or {}

        if side.upper() == "BUY":
            params["positionSide"] = "LONG"
        elif side.upper() == "SELL":
            params["positionSide"] = "SHORT"

        if self.dry_run:
            logger.info("DRY RUN order %s %s %s @%s qty=%s params=%s",
                        symbol, type, side, price, amount, params)
            return {
                "id": "dryrun-" + symbol.replace("/", ""),
                "symbol": symbol,
                "type": type,
                "side": side,
                "price": price,
                "amount": amount,
                "params": params,
                "status": "open",
                "info": {"dry_run": True},
            }

        try:
            return await self.exchange.create_order(symbol, type, side, amount, price, params)
        except Exception as e:
            logger.exception("create_order failed %s %s %s: %s", symbol, side, amount, e)
            raise

    async def close(self):
        try:
            if self.exchange:
                await self.exchange.close()
        except Exception:
            logger.debug("Error closing exchange client", exc_info=True)
