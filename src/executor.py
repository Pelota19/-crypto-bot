# Módulo responsable de ejecutar órdenes, TP/SL y actualizar el estado en memoria.
import asyncio
import logging
import time
from typing import Optional
from config.settings import RISK_REWARD_RATIO, ORDER_TIMEOUT, DRY_RUN
from src.risk.manager import position_size_in_base
from src.state import bot_state

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, client, risk_manager, dry_run: bool = DRY_RUN):
        self.client = client
        self.risk_manager = risk_manager
        self.dry_run = dry_run
        self._monitor_task = None
        self._running = False

    async def start(self):
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_positions_loop())

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def open_position(self, symbol: str, side: str, size_usd: float, entry_price: float):
        """
        Abre una posición: mercado de entrada + crea órdenes limit TP y SL (si es posible).
        side: "buy" or "sell"
        size_usd: tamaño en USD
        entry_price: precio actual (para cálculo de cantidad base)
        """
        if bot_state.is_paused:
            logger.info("Bot paused, skip opening new position")
            return None

        base_amount = position_size_in_base(size_usd, 1.0, entry_price)  # usa helper existente
        if base_amount <= 0:
            logger.warning("Calculated base amount <= 0, skipping open")
            return None

        # Create market entry
        try:
            order = await self.client.create_market_order(symbol, side, base_amount)
        except Exception as e:
            logger.exception("Failed to create market order: %s", e)
            return None

        order_id = order.get("id")
        filled = order.get("filled", base_amount)
        avg_price = order.get("average") or entry_price

        # Compute TP/SL using RISK_REWARD_RATIO and a simple ATR proxy (no ATR here; use percent)
        r = RISK_REWARD_RATIO
        sl_pct = 0.005  # 0.5% stop by default (ajustable)
        if side.lower() == "buy":
            tp_price = avg_price * (1 + sl_pct * r)
            sl_price = avg_price * (1 - sl_pct)
            tp_side = "sell"
            sl_side = "sell"
        else:
            tp_price = avg_price * (1 - sl_pct * r)
            sl_price = avg_price * (1 + sl_pct)
            tp_side = "buy"
            sl_side = "buy"

        # Place TP and SL as limit orders (note: stop-loss market may require special params per exchange)
        tp_order = await self.client.create_limit_order(symbol, tp_side, filled, tp_price)
        sl_order = await self.client.create_limit_order(symbol, sl_side, filled, sl_price)

        # Register in state
        pos = {
            "symbol": symbol,
            "side": side,
            "size_usd": size_usd,
            "base_amount": filled,
            "entry_price": avg_price,
            "order_id": order_id,
            "tp_order": tp_order,
            "sl_order": sl_order,
            "opened_at": time.time()
        }
        bot_state.open_positions[order_id] = pos
        logger.info("Opened position %s: %s", order_id, pos)
        return pos

    async def _monitor_positions_loop(self):
        while self._running:
            try:
                await self._check_positions_once()
            except Exception:
                logger.exception("Error in monitor loop")
            await asyncio.sleep(5)
    
    async def _check_positions_once(self):
        # Check each registered position for order status, realized PnL simplificado
        to_remove = []
        for oid, pos in list(bot_state.open_positions.items()):
            tp = pos.get("tp_order")
            sl = pos.get("sl_order")
            # Fetch order states
            tp_state = await self.client.fetch_order(tp.get("id"), pos["symbol"]) if tp else None
            sl_state = await self.client.fetch_order(sl.get("id"), pos["symbol"]) if sl else None

            closed = False
            if tp_state and tp_state.get("status") in ("closed", "filled"):
                closed = True
                exit_price = tp_state.get("price") or tp_state.get("average")
                reason = "tp"
            elif sl_state and sl_state.get("status") in ("closed", "filled"):
                closed = True
                exit_price = sl_state.get("price") or sl_state.get("average")
                reason = "sl"
            else:
                # Optionally: check if main position is closed
                main_state = await self.client.fetch_order(pos.get("order_id"), pos["symbol"])
                if main_state and main_state.get("status") in ("closed", "filled") and main_state.get("remaining", 0) == 0:
                    # still open via TP/SL, skip
                    pass

            if closed:
                entry = pos["entry_price"]
                base = pos["base_amount"]
                # Simplified pnl (no fees)
                if pos["side"].lower() == "buy":
                    pnl = (exit_price - entry) * base
                else:
                    pnl = (entry - exit_price) * base
                bot_state.daily_pnl_usd += pnl
                logger.info("Position %s closed by %s: exit_price=%s pnl=%.2f total_daily=%.2f", oid, reason, exit_price, pnl, bot_state.daily_pnl_usd)
                to_remove.append(oid)
                # cancel counterpart orders
                try:
                    if reason == "tp" and sl:
                        await self.client.cancel_order(sl.get("id"), pos["symbol"])
                    if reason == "sl" and tp:
                        await self.client.cancel_order(tp.get("id"), pos["symbol"])
                except Exception:
                    logger.exception("Error cancelling counterpart order")

        for oid in to_remove:
            bot_state.open_positions.pop(oid, None)
            # Check profit target
            from config.settings import DAILY_PROFIT_TARGET
            if bot_state.daily_pnl_usd >= DAILY_PROFIT_TARGET:
                bot_state.is_paused = True
                logger.info("Daily profit target reached: %.2f. Pausing new trades.", bot_state.daily_pnl_usd)
