"""
Async wrapper for Binance Futures via ccxt.async_support.
Soporta sandbox/testnet y DRY_RUN.
Provee create_bracket_order para emular OCO en Futures:
entrada LIMIT post-only, espera fill, luego STOP_MARKET + TAKE_PROFIT_LIMIT.
Aplica apalancamiento según configuración.
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
        # create exchange instance
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
            logger.exception("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.debug("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def fetch_all_symbols(self) -> List[str]:
        try:
            markets: Dict[str, dict] = await self.exchange.load_markets()
            return [sym for sym in markets.keys() if sym.endswith("/USDT")]
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

    async def fetch_order(self, order_id: str, symbol: str = None) -> Optional[dict]:
        if self.dry_run and order_id.startswith("sim"):
            if order_id.startswith("sim-market"):
                return {"id": order_id, "status": "closed", "filled": None}
            return {"id": order_id, "status": "open"}
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.exception("fetch_order error: %s", e)
            return None

    async def cancel_order(self, order_id: str, symbol: str):
        if self.dry_run:
            logger.info("DRY_RUN cancel order %s %s", order_id, symbol)
            return {"id": order_id, "status": "canceled"}
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.exception("cancel_order error: %s", e)
            raise

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
        """
        Entrada LIMIT post-only, espera fill, luego SL + TP.
        TP siempre como LIMIT para comisiones de Maker.
        Logging extendido y validación mínima de qty.
        Aplica leverage automáticamente.
        """
        await self.set_leverage(symbol)

        logger.info("=== CREATE_BRACKET_ORDER START ===")
        logger.info("Symbol: %s | Side: %s | Qty: %s | Entry: %s | Stop: %s | TP: %s",
                    symbol, side, quantity, entry_price, stop_price, take_profit_price)

        # --- Obtener info de mercado para validar mínimo qty ---
        try:
            market = self.exchange.markets[symbol]
            min_qty = float(market.get("limits", {}).get("amount", {}).get("min", 0))
            step_size = float(market.get("limits", {}).get("amount", {}).get("step", 1))
            logger.info("Market info: min_qty=%s | step_size=%s", min_qty, step_size)
        except Exception as e:
            logger.warning("No se pudo obtener market info para %s: %s", symbol, e)
            min_qty = 0
            step_size = 1

        # --- Ajustar quantity con leverage ---
        quantity = quantity * LEVERAGE
        logger.info("Cantidad ajustada con leverage %dx: %s", LEVERAGE, quantity)

        # --- Verificar que quantity cumpla mínimo ---
        if quantity < min_qty:
            logger.warning("Cantidad %s menor al mínimo %s para %s. Orden ignorada.", quantity, min_qty, symbol)
            return None, None, None

        # Redondear quantity al step_size
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
            # Entrada LIMIT post-only
            params_entry = {"timeInForce": "GTX"}
            entry_order = await self.exchange.create_order(symbol, "LIMIT", side, quantity, entry_price, params_entry)

            # Esperar fill
            entry_filled = False
            start = time.time()
            entry_id = entry_order.get("id")
            while time.time() - start < wait_timeout:
                ordinfo = await self.fetch_order(entry_id, symbol)
                if ordinfo and ordinfo.get("status") in ("closed", "filled"):
                    entry_filled = True
                    break
                await asyncio.sleep(0.5)

            if not entry_filled:
                await self.cancel_order(entry_id, symbol)
                return None, None, None

            # Stop Market
            stop_side = "SELL" if side.upper() == "BUY" else "BUY"
            params_stop = {"stopPrice": stop_price}
            stop_order = await self.exchange.create_order(symbol, "STOP_MARKET", stop_side, quantity, None, params_stop)

            # Take Profit LIMIT
            tp_side = "SELL" if side.upper() == "BUY" else "BUY"
            params_tp = {"timeInForce": "GTX"}
            tp_order = await self.exchange.create_order(symbol, "LIMIT", tp_side, quantity, take_profit_price, params_tp)

            logger.info("=== CREATE_BRACKET_ORDER END ===")
            return entry_order, stop_order, tp_order

        except Exception as e:
            logger.exception("Error creando bracket order para %s: %s", symbol, e)
            return None, None, None

    async def create_oco_order(self, *args, **kwargs):
        logger.warning("create_oco_order is deprecated. Using create_bracket_order instead.")
        return await self.create_bracket_order(*args, **kwargs)

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
