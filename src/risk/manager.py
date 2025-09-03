from __future__ import annotations
try:
    from src.config import CAPITAL_MAX_USDT
except ImportError:
    CAPITAL_MAX_USDT = 2000.0

def position_size_in_base(equity_usdt: float, pct: float, price: float) -> float:
    # pct expresado 0..1
    # Cap the equity at CAPITAL_MAX_USDT for position sizing
    capped_equity = min(equity_usdt, CAPITAL_MAX_USDT)
    usd = max(0.0, capped_equity * max(0.0, min(1.0, pct)))
    if price <= 0:
        return 0.0
    return usd / price

def compute_sl_tp(entry_price: float, side: str, sl_pct: float = 0.002, tp_pct: float = 0.004) -> tuple[float, float]:
    # por defecto SL 0.2% y TP 0.4% (ajustable si hace falta)
    if side == "buy":
        sl = entry_price * (1 - sl_pct)
        tp = entry_price * (1 + tp_pct)
    else:
        sl = entry_price * (1 + sl_pct)
        tp = entry_price * (1 - tp_pct)
    return sl, tp
