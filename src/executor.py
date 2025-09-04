# src/executor.py
"""
Executor: place orders on Binance Futures via ccxt wrapper (BinanceClient.exchange).
Implements:
 - place_limit_post_only_entry()
 - wait_for_fill()
 - place_sl_tp_orders()  (tries stop-market + take-profit-limit)
"""

import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, client, risk_manager=None, dry_run: bool = False):
        self.client = client  # instance of BinanceClient (has exchange / create methods)
        self.risk_manager = risk_manager
        self.dry_run = dry_run

    async def start(self):
        logger.info("Executor started (dry_run=%s)", self.dry_run)

    async def stop(self):
        logger.info("Executor stopped")

    async def place_limit_post_only_entry(self, symbol: str, side: str, amount: float, price: float) -> Dict[str, Any]:
        """
        Place a limit order with postOnly flag. Returns order dict.
        """
        if self.dry_run:
            logger.info("DRY_RUN place_limit_post_only_entry %s %s %f @ %f", symbol, side, amount, price)
            return {"id": f"sim-entry-{symbol}-{int(asyncio.get_event_loop().time())}", "status": "open", "price": price}
        try:
            params = {"postOnly": True}
            # ccxt create_order usage: create_order(symbol, type, side, amount, price, params)
            order = await self.client.exchange.create_order(symbol, "limit", side, amount, price, params)
            logger.info("Placed limit post-only entry %s", order)
            return order
        except Exception as e:
            logger.exception("place_limit_post_only_entry failed: %s", e)
            raise

    async def wait_for_fill(self, order_id: str, symbol: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Poll order status until filled or timeout (seconds). Returns final order dict.
        """
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            try:
                order = await self.client.fetch_order(order_id, symbol)
                if not order:
                    await asyncio.sleep(1)
                    continue
                status = order.get("status", "").lower()
                if status in ("closed", "filled", "canceled", "cancelled"):
                    return order
            except Exception:
                logger.exception("Error fetching order status")
            await asyncio.sleep(1)
        raise TimeoutError("Order fill timeout")

    async def place_sl_tp_orders(self, symbol: str, side: str, base_amount: float,
                                 sl_price: float, tp_price: float, reduce_only: bool = True) -> Dict[str, Any]:
        """
        Place stop-market for SL and take-profit limit. Returns dict with both orders.
        Note: Binance Futures via ccxt may have different param names; implementations may vary.
        """
        if self.dry_run:
            logger.info("DRY_RUN place_sl_tp_orders %s SL:%f TP:%f", symbol, sl_price, tp_price)
            return {"sl": {"id": "sim-sl"}, "tp": {"id": "sim-tp"}}
        try:
            # Stop market (stopPrice param). Side for stop is opposite of entry.
            stop_side = "sell" if side == "buy" else "buy"
            # place stop market
            sl_params = {"stopPrice": sl_price, "closePosition": False, "reduceOnly": reduce_only}
            sl_order = await self.client.exchange.create_order(symbol, "stop_market", stop_side, base_amount, None, sl_params)

            # place take profit limit (some exchanges use 'takeProfit' or 'stopPrice' with type)
            tp_side = stop_side
            tp_params = {"stopPrice": tp_price, "reduceOnly": reduce_only}
            tp_order = await self.client.exchange.create_order(symbol, "take_profit_limit", tp_side, base_amount, tp_price, tp_params)

            logger.info("Placed SL and TP orders %s / %s", sl_order, tp_order)
            return {"sl": sl_order, "tp": tp_order}
        except Exception as e:
            logger.exception("place_sl_tp_orders failed: %s", e)
            raise

    async def open_position(self, symbol: str, side: str, size_usd: float, entry_price: float):
        """
        High-level: compute base amount from size_usd/price and place entry -> wait -> place SL/TP
        """
        base_amount = size_usd / entry_price
        # For futures, the amount may be in contracts or base asset units depending on market
        # Round appropriately if needed.
        # Place limit post-only entry
        order = await self.place_limit_post_only_entry(symbol, side, base_amount, entry_price)
        order_id = order.get("id")
        # Wait for fill
        try:
            final = await self.wait_for_fill(order_id, symbol, timeout=120)
            status = final.get("status", "").lower()
            if status in ("closed", "filled"):
                # compute sl / tp from entry
                # For demo: fixed SL and TP percentages (could be from strategy)
                sl_pct = 0.002  # 0.2%
                tp_pct = sl_pct * 1.5  # R:R 1.5
                if side == "buy":
                    sl_price = entry_price * (1 - sl_pct)
                    tp_price = entry_price * (1 + tp_pct)
                else:
                    sl_price = entry_price * (1 + sl_pct)
                    tp_price = entry_price * (1 - tp_pct)
                await self.place_sl_tp_orders(symbol, side, base_amount, sl_price, tp_price)
                return final
            else:
                logger.warning("Entry order not filled (status=%s), cancelling", status)
                try:
                    await self.client.cancel_order(order_id, symbol)
                except Exception:
                    pass
                return final
        except TimeoutError:
            logger.warning("Entry not filled in time, cancelling...")
            try:
                await self.client.cancel_order(order_id, symbol)
            except Exception:
                pass
            raise
