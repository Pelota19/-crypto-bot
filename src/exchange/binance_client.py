"""
Async wrapper for Binance Futures via ccxt.async_support.
Supports sandbox/testnet mode (when supported by ccxt) and DRY_RUN simulation.
"""
import time
import logging
from typing import Optional, List
import ccxt.async_support as ccxt

from config.settings import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(
        self,
        api_key: str = API_KEY,
        api_secret: str = API_SECRET,
        use_testnet: bool = USE_TESTNET,
        dry_run: bool = DRY_RUN
    ):
        self.dry_run = dry_run
        opts = {"defaultType": "future"}
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": opts,
        })
        if use_testnet:
            try:
                self.exchange.set_sandbox_mode(True)
                logger.info("Binance sandbox mode enabled")
            except Exception:
                logger.warning("Sandbox/testnet mode no disponible en esta build de ccxt")

    # ---------- Market Data ----------
    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> List:
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=limit)
        except Exception as e:
            logger.exception("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.exception("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def fetch_all_symbols(self) -> List[str]:
        """Retorna todos los pares USDT-M futures disponibles."""
        try:
            markets = await self.exchange.load_markets()
            return [m for m in markets if "USDT" in m]
        except Exception as e:
            logger.exception("fetch_all_symbols failed: %s", e)
            return []

    # ---------- Orders ----------
    async def create_market_order(self, symbol: str, side: str, amount: float) -> dict:
        if self.dry_run:
            oid = f"sim-market-{int(time.time()*1000)}"
            logger.info("DRY_RUN market order simulated: %s %s %f (%s)", symbol, side, amount, oid)
            return {"id": oid, "status": "closed", "filled": amount, "average": None}
        try:
            return await self.exchange.create_order(symbol, "market", side, amount)
        except Exception as e:
            logger.exception("create_market_order failed: %s", e)
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: dict = None) -> dict:
        params = params or {}
        if self.dry_run:
            oid = f"sim-limit-{int(time.time()*1000)}"
            logger.info("DRY_RUN limit order simulated: %s %s %f @ %f (%s)", symbol, side, amount, price, oid)
            return {"id": oid, "status": "open", "price": price, "amount": amount}
        try:
            return await self.exchange.create_order(symbol, "limit", side, amount, price, params)
        except Exception as e:
            logger.exception("create_limit_order failed: %s", e)
            raise

    async def create_oco_order(self, symbol: str, side: str, quantity: float, stop_price: float, take_profit_price: float):
        """
        Crea OCO en Binance Futures usando STOP_MARKET + TAKE_PROFIT_LIMIT.
        side: 'BUY' o 'SELL' (inverso al abrir short/long)
        """
        if self.dry_run:
            oid = f"sim-oco-{int(time.time()*1000)}"
            logger.info("DRY_RUN OCO simulated: %s %s %f, stop %f, tp %f (%s)",
                        symbol, side, quantity, stop_price, take_profit_price, oid)
            return {"id": oid, "status": "open"}
        try:
            # Binance Futures no tiene OCO nativo, simulamos con dos órdenes
            side_opposite = "SELL" if side=="BUY" else "BUY"
            # Take profit limit
            await self.exchange.create_order(symbol, "LIMIT", side, quantity, take_profit_price)
            # Stop market
            await self.exchange.create_order(symbol, "STOP_MARKET", side_opposite, quantity, None, {"stopPrice": stop_price})
            return {"status": "open"}
        except Exception as e:
            logger.exception("create_oco_order failed: %s", e)
            raise

    async def fetch_balance(self) -> dict:
        if self.dry_run:
            return {"USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0}}
        try:
            return await self.exchange.fetch_balance(params={"type":"future"})
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def get_balance_usdt(self) -> float:
        bal = await self.fetch_balance()
        try:
            return bal["USDT"]["free"]
        except Exception:
            return 0.0

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
