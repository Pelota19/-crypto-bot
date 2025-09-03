from __future__ import annotations
import logging
from typing import Optional
from src.persistence.sqlite_store import save_order
from src.risk.manager import position_size_in_base, compute_sl_tp

log = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, exchange_client, equity_usdt_getter):
        self.x = exchange_client
        self.get_equity = equity_usdt_getter  # callable -> float

    def open_position_market(self, symbol: str, side: str, pct: float, price_hint: Optional[float] = None):
        eq = float(self.get_equity())
        price = price_hint or 0.0
        amount = position_size_in_base(eq, pct, price if price > 0 else 1.0)
        if amount <= 0:
            log.warning("Amount computed is zero; skipping order")
            return None
        
        try:
            order = self.x.market_order(symbol, side, amount)
            if order is None:
                log.warning(f"Market order for {symbol} returned None")
                return None
                
            fee = float(order.get("fees", [{}])[0].get("cost", 0.0)) if order.get("fees") else 0.0
            actual_amount = float(order.get("amount", amount))
            actual_price = float(order.get("price", price))
            save_order(symbol, side, actual_price, actual_amount, fee, order.get("status", "unknown"))
            log.info(f"Opened {side} {symbol} amount={actual_amount}")
            return order
        except Exception as e:
            log.warning(f"Failed to open position for {symbol}: {e}")
            return None

    def close_position_market(self, symbol: str, side: str, amount: float):
        # reduceOnly = True para cerrar
        opp = "sell" if side == "buy" else "buy"
        order = self.x.market_order(symbol, opp, amount, reduce_only=True)
        fee = float(order.get("fees", [{}])[0].get("cost", 0.0)) if order.get("fees") else 0.0
        save_order(symbol, opp, float(order.get("price") or 0.0), float(amount), fee, order.get("status", "unknown"))
        log.info(f"Closed {symbol} amount={amount}")
        return order

    def place_brackets(self, symbol: str, entry_side: str, amount: float, sl_price: float, tp_price: float):
        """Place SL and TP bracket orders as conditional reduceOnly orders."""
        try:
            # Stop Loss - STOP_MARKET order using wrapper
            sl_side = "sell" if entry_side == "buy" else "buy"
            sl_order = self.x.stop_market_reduce_only(symbol, sl_side, amount, sl_price)
            
            if sl_order is not None:
                save_order(symbol, sl_side, sl_price, amount, 0.0, sl_order.get("status", "unknown"))
                log.info(f"Placed SL bracket: {sl_side} {symbol} @ {sl_price}")
            else:
                log.warning(f"Failed to place SL bracket for {symbol}: wrapper returned None")

            # Take Profit - TAKE_PROFIT_MARKET order using wrapper
            tp_side = "sell" if entry_side == "buy" else "buy"
            tp_order = self.x.take_profit_market_reduce_only(symbol, tp_side, amount, tp_price)
            
            if tp_order is not None:
                save_order(symbol, tp_side, tp_price, amount, 0.0, tp_order.get("status", "unknown"))
                log.info(f"Placed TP bracket: {tp_side} {symbol} @ {tp_price}")
            else:
                log.warning(f"Failed to place TP bracket for {symbol}: wrapper returned None")

            # Return orders that were successfully created
            result = {}
            if sl_order is not None:
                result["sl_order"] = sl_order
            if tp_order is not None:
                result["tp_order"] = tp_order
                
            return result if result else None
            
        except Exception as e:
            log.warning(f"Failed to place brackets for {symbol}: {e}")
            return None
