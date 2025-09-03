from __future__ import annotations
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class OrderManager:
    """Manager de órdenes simulado: calcula SL/TP y mantiene registros locales.

    En este repo de ejemplo no se conecta a un exchange real. Está pensado
    para ser reemplazado por la integración concreta del usuario.
    """
    def __init__(self):
        self._orders = {}

    def place_order(self, symbol: str, side: str, qty: float, price: float, sl: Optional[float]=None, tp: Optional[float]=None) -> Dict:
        oid = f"local-{len(self._orders)+1}"
        order = {
            "id": oid,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "sl": sl,
            "tp": tp,
            "status": "open",
        }
        self._orders[oid] = order
        logger.info("Placed order %s", order)
        return order

    def cancel_order(self, order_id: str) -> bool:
        o = self._orders.get(order_id)
        if not o:
            return False
        o["status"] = "cancelled"
        logger.info("Cancelled order %s", order_id)
        return True

    def calculate_sl_tp(self, entry_price: float, atr: float, direction: str, rr: float = 1.5) -> Tuple[float, float]:
        """Calcula SL y TP a partir de ATR y ratio riesgo:beneficio.

        - direction: 'long' o 'short'
        - atr: valor de ATR en precio absoluto
        - rr: ratio TP/SL
        """
        sl_dist = max(atr * 1.5, atr)  # distancia mínima basada en ATR
        if direction == "long":
            sl = entry_price - sl_dist
            tp = entry_price + sl_dist * rr
        else:
            sl = entry_price + sl_dist
            tp = entry_price - sl_dist * rr
        return sl, tp


order_manager = OrderManager()