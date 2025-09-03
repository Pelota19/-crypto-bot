# binance_client.py
import time
import logging
import asyncio
from typing import Optional
import ccxt.async_support as ccxt

from config.settings import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key: str = API_KEY, api_secret: str = API_SECRET,
                 use_testnet: bool = USE_TESTNET, dry_run: bool = DRY_RUN):
        self.dry_run = dry_run

        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future"  # obligamos FAPI (USDT-M)
            },
        })

        if use_testnet:
            # Activar modo sandbox/testnet
            self.exchange.set_sandbox_mode(True)
            logger.info("Binance TESTNET de Futures habilitado (USDT-M).")

    async def fetch_balance(self) -> dict:
        if self.dry_run:
            return {"USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0}}
        try:
            return await self.exchange.fetch_balance()  # defaultType='future' ya está seteado
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.exception("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            logger.exception("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def create_market_order(self, symbol: str, side: str, amount: float, params: dict = None) -> dict:
        if self.dry_run:
            logger.info("DRY_RUN market order %s %s %f", symbol, side, amount)
            return {"id": f"sim-{int(time.time()*1000)}", "status": "closed", "filled": amount}
        try:
            return await self.exchange.create_order(symbol, "market", side, amount, None, params or {})
        except Exception as e:
            logger.exception("create_market_order failed: %s", e)
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: dict = None) -> dict:
        if self.dry_run:
            logger.info("DRY_RUN limit order %s %s %f @ %f", symbol, side, amount, price)
            return {"id": f"sim-lim-{int(time.time()*1000)}", "status": "open", "price": price, "amount": amount}
        try:
            return await self.exchange.create_order(symbol, "limit", side, amount, price, params or {})
        except Exception as e:
            logger.exception("create_limit_order failed: %s", e)
            raise

    async def fetch_order(self, order_id: str, symbol: str) -> Optional[dict]:
        if self.dry_run and order_id.startswith("sim"):
            return {"id": order_id, "status": "closed"}
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.exception("fetch_order error: %s", e)
            return None

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        if self.dry_run:
            logger.info("DRY_RUN cancel order %s %s", order_id, symbol)
            return {"id": order_id, "status": "canceled"}
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.exception("cancel_order error: %s", e)
            raise

    async def fetch_positions(self) -> list:
        try:
            return await self.exchange.fetch_positions()
        except Exception as e:
            logger.exception("fetch_positions error: %s", e)
            return []

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass

    # Context manager async opcional
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
