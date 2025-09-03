from __future__ import annotations
from typing import Dict, Optional

from src.ai import scorer

# Strategy: recibe features ya calculadas (dict) y decide acción.

DAILY_TARGET_PCT = 0.01  # objetivo diario 1% por ejemplo


def decide_trade(symbol: str, features: Dict[str, float], price: float, atr: float) -> Optional[Dict]:
    """Decide si abrir una operación basándose en el scorer y devuelve una orden simulada.

    features: dict con claves compatibles con src/ai/scorer.py (mom, rsi_centered, vwap_dev, atr_regime, micro_trend)
    price: precio de entrada
    atr: ATR absoluto para calcular SL/TP

    Retorna None si no hay señal o dict con keys: side, qty, price, sl, tp, info
    """
    score = scorer.score(features)
    # Umbral simple: >0.5 buy, < -0.5 sell
    if score > 0.5:
        side = "long"
    elif score < -0.5:
        side = "short"
    else:
        return None

    # tamaño simple: basado en un riesgo fijo (usuario deberá ajustar)
    risk_pct = 0.01
    # qty placeholder: el usuario debe calcular según capital/lev
    qty = 1.0

    # calcular SL/TP usando ATR
    if atr <= 0:
        atr = max(1.0, abs(price) * 0.001)

    from src.orders.manager import OrderManager
    om = OrderManager()
    sl, tp = om.calculate_sl_tp(price, atr, "long" if side == "long" else "short", rr=1.5)

    return {
        "side": side,
        "qty": qty,
        "price": price,
        "sl": sl,
        "tp": tp,
        "score": score,
    }