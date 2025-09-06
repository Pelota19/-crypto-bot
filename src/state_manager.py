# src/state_manager.py
import datetime
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class StateManager:
    """Gestión del estado del bot con tracking extendido para SL/TP y cierres."""

    def __init__(self, daily_profit_target: float = 50.0):
        # open_positions: symbol -> dict with keys:
        # { side, entry, quantity, sl, tp, entry_order_id, sl_order_id, tp_order_id,
        #   entry_avg, entry_filled, sl_type, tp_type, sl_fallback, tp_fallback,
        #   created_at, closed }
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
        entry_avg: Optional[float] = None,
        entry_filled: Optional[float] = 0.0,
    ):
        """
        Registra la posición abierta. entry_avg y entry_filled pueden actualizarse
        por el monitor cuando la entrada se ejecute (parcial/total).
        Se añaden campos para trackeo de tipos y fallbacks.
        """
        self.open_positions[symbol] = {
            "side": side,
            "entry": float(entry),
            "quantity": float(quantity),
            "sl": float(sl),
            "tp": float(tp),
            "entry_order_id": entry_order_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "entry_avg": float(entry_avg) if entry_avg is not None else None,
            "entry_filled": float(entry_filled or 0.0),
            "sl_type": None,
            "tp_type": None,
            "sl_fallback": False,
            "tp_fallback": False,
            "created_at": datetime.datetime.utcnow(),
            "closed": False,
        }
        logger.info(f"📌 Posición abierta en {symbol}: {side} {quantity} @ {entry}, SL {sl}, TP {tp}, orders: entry={entry_order_id} sl={sl_order_id} tp={tp_order_id}")

    def update_entry_execution(self, symbol: str, filled: float, avg: Optional[float]):
        """
        Actualiza los datos de ejecución de la entry (parcial/total).
        """
        pos = self.open_positions.get(symbol)
        if not pos:
            logger.debug("update_entry_execution: posición no encontrada para %s", symbol)
            return
        pos["entry_filled"] = float(filled)
        pos["entry_avg"] = float(avg) if avg is not None else pos.get("entry")
        pos["quantity"] = float(filled)
        self.open_positions[symbol] = pos
        logger.info("Entry execution updated for %s: filled=%s avg=%s", symbol, filled, avg)

    def set_sl_order(self, symbol: str, order_id: Optional[str], order_type: Optional[str], fallback_used: bool = False):
        pos = self.open_positions.get(symbol)
        if not pos:
            return
        pos["sl_order_id"] = order_id
        pos["sl_type"] = order_type
        pos["sl_fallback"] = bool(fallback_used)
        self.open_positions[symbol] = pos
        logger.info("SL order recorded for %s: id=%s type=%s fallback=%s", symbol, order_id, order_type, fallback_used)

    def set_tp_order(self, symbol: str, order_id: Optional[str], order_type: Optional[str], fallback_used: bool = False):
        pos = self.open_positions.get(symbol)
        if not pos:
            return
        pos["tp_order_id"] = order_id
        pos["tp_type"] = order_type
        pos["tp_fallback"] = bool(fallback_used)
        self.open_positions[symbol] = pos
        logger.info("TP order recorded for %s: id=%s type=%s fallback=%s", symbol, order_id, order_type, fallback_used)

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
        logger.info(f"✅  Operación cerrada en {symbol} por {reason} con PnL {pnl:.2f} USDT (Total diario: {self.realized_pnl_today:.2f})")

    def set_final_close_info(self, symbol: str, close_order_id: Optional[str], close_type: Optional[str], pnl: Optional[float]):
        """
        Guarda metadatos sobre el cierre (tipo de orden final y PnL).
        """
        # find in closed history the record and add details if present
        for rec in reversed(self.closed_positions_history):
            if rec.get("symbol") == symbol and rec.get("close_order_id") == close_order_id:
                rec["final_close_type"] = close_type
                rec["pnl"] = float(pnl) if pnl is not None else rec.get("pnl", 0.0)
                rec["annotated_at"] = datetime.datetime.utcnow()
                break

    def get_open_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.open_positions

    def find_position_by_order_id(self, order_id: str) -> Optional[str]:
        # retorna el símbolo si alguna de las order ids corresponde
        for symbol, pos in self.open_positions.items():
            if pos.get("entry_order_id") == order_id or pos.get("sl_order_id") == order_id or pos.get("tp_order_id") == order_id:
                return symbol
        return None
