"""
Executor: opens positions, places TP/SL (as limit orders where possible),
monitors order status, updates bot_state and sends Telegram alerts for important events.
"""
import asyncio
import logging
import time
from typing import Optional, Dict
from config.settings import RISK_REWARD_RATIO, ORDER_TIMEOUT
from src.risk.manager import usd_to_base, cap_equity
from src.state import bot_state
from src.notifications.telegram import send_telegram_message

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, client, risk_manager, dry_run: bool = True):
        self.client = client
        self.risk_manager = risk_manager
        self.dry_run = dry_run
        self._monitor_task: Optional[asyncio.Task] = None
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

    async def open_position(self, symbol: str, side: str, size_usd: float, entry_price: float) -> Optional[Dict]:
        """
        Open a position:
        - size_usd: amount in USD to use for the entry (will be converted to base asset)
        - entry_price: reference price to compute base amount
        """
        if bot_state.is_paused:
            logger.info("Bot paused, skipping new position for %s", symbol)
            return None

        # Ensure we respect capital cap
        # size_usd is an allocation; we also ensure it doesn't exceed cap
        usable_cap = cap_equity(size_usd)
        # Convert USD allocation to base amount
        if entry_price <= 0:
            logger.warning("Invalid entry price for %s: %s", symbol, entry_price)
            return None

        base_amount = usd_to_base(size_usd, entry_price)
        if base_amount <= 0:
            logger.warning("Calculated base amount <= 0 for %s, skipping", symbol)
            return None

        # Create market order
        try:
            order = await self.client.create_market_order(symbol, side, base_amount)
        except Exception as e:
            logger.exception("Failed to create market order for %s: %s", symbol, e)
            await send_telegram_message(f"⚠️ Error placing market order for {symbol}: {e}")
            return None

        order_id = order.get("id")
        filled = order.get("filled", base_amount)
        avg_price = order.get("average") or entry_price

        # Compute TP and SL using a default percent-based SL (0.5%) and RRR
        sl_pct = 0.005  # default 0.5% stop
        r = RISK_REWARD_RATIO
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

        # Place TP and SL as limit orders (note: futures exchanges may require different params)
        try:
            tp_order = await self.client.create_limit_order(symbol, tp_side, filled, tp_price)
        except Exception as e:
            logger.exception("Failed to place TP order for %s: %s", symbol, e)
            tp_order = None

        try:
            sl_order = await self.client.create_limit_order(symbol, sl_side, filled, sl_price)
        except Exception as e:
            logger.exception("Failed to place SL order for %s: %s", symbol, e)
            sl_order = None

        # Register position in bot state
        pos = {
            "symbol": symbol,
            "side": side,
            "size_usd": size_usd,
            "base_amount": filled,
            "entry_price": float(avg_price),
            "order_id": order_id,
            "tp_order": tp_order,
            "sl_order": sl_order,
            "opened_at": time.time()
        }
        bot_state.open_positions[order_id] = pos

        msg = (f"🟢 Opened {side.upper()} {symbol}: size_usd={size_usd:.2f}, base={filled:.6f}, "
               f"entry={avg_price:.2f}, TP={getval(tp_order,'price')}, SL={getval(sl_order,'price')}")
        logger.info(msg)
        await send_telegram_message(msg)

        return pos

    async def _monitor_positions_loop(self):
        while self._running:
            try:
                await self._check_positions_once()
            except Exception:
                logger.exception("Error in monitor loop")
            await asyncio.sleep(5)

    async def _check_positions_once(self):
        """Iterate positions and check TP/SL closures; simplified PnL calc (no fees)."""
        to_remove = []
        for oid, pos in list(bot_state.open_positions.items()):
            tp = pos.get("tp_order")
            sl = pos.get("sl_order")

            tp_state = None
            sl_state = None
            try:
                if tp:
                    tp_state = await self.client.fetch_order(tp.get("id"), pos["symbol"])
                if sl:
                    sl_state = await self.client.fetch_order(sl.get("id"), pos["symbol"])
            except Exception:
                logger.exception("Error fetching order state for %s", oid)

            closed = False
            exit_price = None
            reason = None

            if tp_state and tp_state.get("status") in ("closed", "filled"):
                closed = True
                exit_price = tp_state.get("price") or tp_state.get("average")
                reason = "TP"
            elif sl_state and sl_state.get("status") in ("closed", "filled"):
                closed = True
                exit_price = sl_state.get("price") or sl_state.get("average")
                reason = "SL"
            else:
                # Optionally we could fetch main order to detect full fills; skip for now
                pass

            if closed:
                entry = pos["entry_price"]
                base = pos["base_amount"]
                if exit_price is None:
                    # Fallback: if order objects didn't include price, use entry (0 pnl)
                    exit_price = entry
                if pos["side"].lower() == "buy":
                    pnl = (float(exit_price) - float(entry)) * float(base)
                else:
                    pnl = (float(entry) - float(exit_price)) * float(base)
                bot_state.daily_pnl_usd += float(pnl)
                logger.info("🔴 Position %s closed by %s: exit=%s pnl=%.2f total_daily=%.2f", oid, reason, exit_price, pnl, bot_state.daily_pnl_usd)
                await send_telegram_message(f"🔴 Position closed ({pos['symbol']}): reason={reason}, pnl={pnl:.2f} USD — Daily total: {bot_state.daily_pnl_usd:.2f} USD")

                # Cancel counterpart order if exists
                try:
                    if reason == "TP" and sl:
                        await self.client.cancel_order(sl.get("id"), pos["symbol"])
                    if reason == "SL" and tp:
                        await self.client.cancel_order(tp.get("id"), pos["symbol"])
                except Exception:
                    logger.exception("Error cancelling counterpart order after close")

                to_remove.append(oid)

                # Check daily profit target
                from config.settings import DAILY_PROFIT_TARGET
                if bot_state.daily_pnl_usd >= DAILY_PROFIT_TARGET:
                    bot_state.is_paused = True
                    logger.info("🎯 Daily profit target reached: %.2f. Pausing new trades.", bot_state.daily_pnl_usd)
                    await send_telegram_message(f"🎯 Objetivo diario alcanzado: {bot_state.daily_pnl_usd:.2f} USD. Pausando nuevas operaciones.")

        for oid in to_remove:
            bot_state.open_positions.pop(oid, None)

def getval(o, key):
    try:
        return o.get(key)
    except Exception:
        return None
