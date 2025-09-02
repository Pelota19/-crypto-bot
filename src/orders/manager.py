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
        order = self.x.market_order(symbol, side, amount)
        fee = float(order.get("fees", [{}])[0].get("cost", 0.0)) if order.get("fees") else 0.0
        save_order(symbol, side, float(order.get("price") or price), float(amount), fee, order.get("status", "unknown"))
        log.info(f"Opened {side} {symbol} amount={amount}")
        return order

    def close_position_market(self, symbol: str, side: str, amount: float):
        # reduceOnly = True para cerrar
        opp = "sell" if side == "buy" else "buy"
        order = self.x.market_order(symbol, opp, amount, reduce_only=True)
        fee = float(order.get("fees", [{}])[0].get("cost", 0.0)) if order.get("fees") else 0.0
        save_order(symbol, opp, float(order.get("price") or 0.0), float(amount), fee, order.get("status", "unknown"))
        log.info(f"Closed {symbol} amount={amount}")
        return order
