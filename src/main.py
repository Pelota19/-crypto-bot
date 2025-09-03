from __future__ import annotations
import logging
import time

from src.config import LOG_LEVEL
from src.simple_strategy import decide_trade
from src.orders.manager import order_manager

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def run_once():
    # Ejemplo de ejecución mínima: datos ficticios
    symbol = "BTC/USDT"
    price = 50000.0
    atr = 200.0
    features = {
        "mom": 0.5,
        "rsi_centered": 0.1,
        "vwap_dev": -0.2,
        "atr_regime": -0.1,
        "micro_trend": 0.3,
    }

    decision = decide_trade(symbol, features, price, atr)
    if not decision:
        logger.info("No signal for %s", symbol)
        return

    order = order_manager.place_order(symbol, decision["side"], decision["qty"], decision["price"], sl=decision["sl"], tp=decision["tp"])
    logger.info("Order placed: %s", order)


if __name__ == "__main__":
    logger.info("Starting bot (demo run)")
    run_once()