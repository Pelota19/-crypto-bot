from __future__ import annotations

def position_size_in_base(equity_usdt: float, pct: float, price: float) -> float:
    # pct expresado 0..1
    usd = max(0.0, equity_usdt * max(0.0, min(1.0, pct)))
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
