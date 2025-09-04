"""
Async wrapper for Binance Futures via ccxt.async_support.
Soporta sandbox/testnet y DRY_RUN.
Provee create_bracket_order para emular OCO en Futures:
entrada LIMIT post-only, espera fill, luego STOP_MARKET + TAKE_PROFIT_LIMIT.
Aplica apalancamiento según configuración y valida pares activos.
"""
import time
import logging
from typing import Optional, List, Dict, Tuple
import asyncio
import ccxt.async_support as ccxt

from config.settings import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN, LEVERAGE, MARGIN_MODE

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
        self.markets_cache = {}

    async def load_markets(self):
        if not self.markets_cache:
            try:
                self.markets_cache = await self.exchange.load_markets()
            except Exception as e:
                logger.exception("Error cargando mercados: %s", e)
        return self.markets_cache

    async def set_leverage(self, symbol: str):
        if self.dry_run:
            return
        try:
            await self.exchange.fapiPrivate_post_leverage({
                "symbol": symbol.replace("/", ""),
                "leverage": int(LEVERAGE)
            })
            await self.exchange.fapiPrivate_post_marginType({
                "symbol": symbol.replace("/", ""),
                "marginType": MARGIN_MODE
            })
            logger.info("Leverage %dx y margin mode %s aplicado a %s", LEVERAGE, MARGIN_MODE, symbol)
        except Exception as e:
            logger.exception("No se pudo aplicar leverage/margin para %s: %s", symbol, e)

    # ---------- Market Data ----------
    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> List:
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=limit)
        except Exception as e:
            logger.debug("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.debug("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def fetch_all_symbols(self) -> List[str]:
        try:
            markets = await self.load_markets()
            # Solo pares USDT, activos, y futuros PERPETUALES
            return [
                sym for sym, m in markets.items()
                if sym.endswith("/USDT") and m.get("active", True) and m.get("contractType") == "PERPETUAL"
            ]
        except Exception as e:
            logger.exception("fetch_all_symbols failed: %s", e)
            return []

    # ---------- Orders ----------
    async def create_bracket_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        wait_timeout: int = 30
    ) -> Tuple[Optional[dict], Optional[dict], Optional[dict]]:
        await self.set_leverage(symbol)
        logger.info("=== CREATE_BRACKET_ORDER START ===")
        logger.info("Symbol: %s | Side: %s | Qty: %s | Entry: %s | Stop: %s | TP: %s",
                    symbol, side, quantity, entry_price, stop_price, take_profit_price)

        # --- Validar mercado ---
        try:
            markets = await self.load_markets()
            market = markets[symbol]
            if not market.get("active", True):
                logger.warning("%s no está activo. Orden ignorada.", symbol)
                return None, None, None
            min_qty = float(market.get("limits", {}).get("amount", {}).get("min", 0))
            step_size = float(market.get("limits", {}).get("amount", {}).get("step", 1))
        except Exception as e:
            logger.warning("No se pudo obtener market info para %s: %s", symbol, e)
            min_qty = 0
            step_size = 1

        # --- Excepción SOL/USDT ---
        if symbol == "SOL/USDT" and quantity < min_qty:
            logger.info("Excepción SOL/USDT: permitiendo orden mínima de %s", quantity)
            min_qty = quantity

        # --- Ajustar quantity con leverage ---
        quantity = quantity * LEVERAGE
        logger.info("Cantidad ajustada con leverage %dx: %s", LEVERAGE, quantity)

        # --- Verificar mínimos ---
        if quantity < min_qty:
            logger.warning("Cantidad %s menor al mínimo %s para %s. Orden ignorada.", quantity, min_qty, symbol)
            return None, None, None

        # Redondear al step_size
        if step_size > 0:
            quantity = (quantity // step_size) * step_size
            logger.info("Cantidad ajustada a step_size: %s", quantity)

        if self.dry_run:
            oid = f"sim-bracket-{int(time.time()*1000)}"
            logger.info("DRY_RUN bracket simulated: %s %s %f entry=%f stop=%f tp=%f (%s)",
                        symbol, side, quantity, entry_price, stop_price, take_profit_price, oid)
            return ({"id": f"{oid}-entry", "status": "closed"},
                    {"id": f"{oid}-stop", "status": "open"},
                    {"id": f"{oid}-tp", "status": "open"})

        try:
            params_entry = {"timeInForce": "GTX"}
            entry_order = await self.exchange.create_order(symbol, "LIMIT", side, quantity, entry_price, params_entry)

            # Esperar fill
            entry_filled = False
            start = time.time()
            entry_id = entry_order.get("id")
            while time.time() - start < wait_timeout:
                ordinfo = await self.exchange.fetch_order(entry_id, symbol)
                if ordinfo and ordinfo.get("status") in ("closed", "filled"):
                    entry_filled = True
                    break
                await asyncio.sleep(0.5)
            if not entry_filled:
                await self.exchange.cancel_order(entry_id, symbol)
                return None, None, None

            # Stop Market
            stop_side = "SELL" if side.upper() == "BUY" else "BUY"
            stop_order = await self.exchange.create_order(
                symbol, "STOP_MARKET", stop_side, quantity, None, {"stopPrice": stop_price}
            )

            # Take Profit LIMIT
            tp_side = "SELL" if side.upper() == "BUY" else "BUY"
            tp_order = await self.exchange.create_order(
                symbol, "LIMIT", tp_side, quantity, take_profit_price, {"timeInForce": "GTX"}
            )

            logger.info("=== CREATE_BRACKET_ORDER END ===")
            return entry_order, stop_order, tp_order

        except Exception as e:
            logger.exception("Error creando bracket order para %s: %s", symbol, e)
            return None, None, None

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
            return float(bal.get("USDT", {}).get("free", 0.0))
        except Exception:
            return 0.0

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
