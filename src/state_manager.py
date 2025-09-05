# src/state_manager.py
import datetime
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class StateManager:
    """Gestión avanzada del estado del bot, con tracking de órdenes SL/TP y cierre."""

    def __init__(self, daily_profit_target: float = 50.0):
        # open_positions: symbol -> dict with keys:
        # { side, entry, quantity, sl, tp, entry_order_id, sl_order_id, tp_order_id, created_at }
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        # closed history list of dicts
        self.closed_positions_history: List[Dict[str, Any]] = []
        self.realized_pnl_today = 0.0
        self.daily_profit_target = daily_profit_target
        self.last_reset_date = datetime.datetime.utcnow().date()

    def reset_daily_if_needed(self):
        today = datetime.datetime.utcnow().date()
        if today != self.last_reset_date:
            logger.info("Reset diario del PnL")
            self.realized_pnl_today = 0.0
            self.last_reset_date = today

    def can_open_new_trade(self):
        self.reset_daily_if_needed()
        if self.realized_pnl_today >= self.daily_profit_target:
            logger.info("Objetivo diario alcanzado. No se abrirán nuevas operaciones.")
            return False
        return True

    def register_open_position(
        self,
        symbol: str,
        side: str,
        entry: float,
        quantity: float,
        sl: float,
        tp: float,
        entry_order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
    ):
        self.open_positions[symbol] = {
            "side": side,
            "entry": float(entry),
            "quantity": float(quantity),
            "sl": float(sl),
            "tp": float(tp),
            "entry_order_id": entry_order_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "created_at": datetime.datetime.utcnow(),
        }
        logger.info(f"📌 Posición abierta en {symbol}: {side} {quantity} @ {entry}, SL {sl}, TP {tp}, orders: entry={entry_order_id} sl={sl_order_id} tp={tp_order_id}")

    def register_closed_position(self, symbol: str, pnl: float, reason: str, close_price: Optional[float] = None, close_order_id: Optional[str] = None):
        pos = self.open_positions.pop(symbol, None)
        if pos:
            entry = pos.get("entry")
            quantity = pos.get("quantity", 0.0)
        else:
            entry = None
            quantity = 0.0
        record = {
            "symbol": symbol,
            "pnl": float(pnl),
            "reason": reason,
            "close_price": close_price,
            "close_order_id": close_order_id,
            "entry": entry,
            "quantity": quantity,
            "closed_at": datetime.datetime.utcnow(),
        }
        self.closed_positions_history.append(record)
        self.realized_pnl_today += float(pnl)
        logger.info(f"✅ Operación cerrada en {symbol} por {reason} con PnL {pnl:.2f} USDT (Total diario: {self.realized_pnl_today:.2f})")

    def get_open_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.open_positions

    def find_position_by_order_id(self, order_id: str) -> Optional[str]:
        # retorna el símbolo si alguna de las order ids corresponde
        for symbol, pos in self.open_positions.items():
            if pos.get("entry_order_id") == order_id or pos.get("sl_order_id") == order_id or pos.get("tp_order_id") == order_id:
                return symbol
        return None
