import pandas as pd
import numpy as np
from typing import Dict, Tuple
from src.ai.scorer import scorer

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr1 = h - l
    tr2 = (h - c.shift()).abs()
    tr3 = (l - c.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def vwap(df: pd.DataFrame, period: int = 30) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"].replace(0, np.nan)
    num = pv.rolling(period, min_periods=1).sum()
    den = df["volume"].rolling(period, min_periods=1).sum().replace(0, np.nan)
    return (num / den).ffill()

def build_features(df: pd.DataFrame) -> Dict[str, float]:
    close = df["close"]
    fast = ema(close, 9)
    slow = ema(close, 21)
    r = compute_rsi(close, 14)
    _atr = atr(df, 14)
    _vwap = vwap(df, 30)

    mom = ((fast - slow) / close).iloc[-1]
    rsi_centered = ((r.iloc[-1] - 50.0) / 50.0)
    vwap_dev = ((close.iloc[-1] - _vwap.iloc[-1]) / (_atr.iloc[-1] + 1e-9))
    atr_regime = float((_atr.iloc[-1] / close.iloc[-1]))
    win = 5
    if len(close) >= win:
        y = close.iloc[-win:]
        x = np.arange(win)
        slope = np.polyfit(x, y, 1)[0]
        micro_trend = float((slope / (y.mean() + 1e-9)))
    else:
        micro_trend = 0.0

    vwap_dev = float(np.clip(vwap_dev, -3, 3))
    atr_regime = float(np.clip(atr_regime / 0.01, 0.0, 5.0))

    return {
        "mom": float(mom),
        "rsi_centered": float(rsi_centered),
        "vwap_dev": vwap_dev,
        "atr_regime": atr_regime,
        "micro_trend": micro_trend,
        "_atr": float(_atr.iloc[-1]),
        "_close": float(close.iloc[-1]),
        "_fast": float(fast.iloc[-1]),
        "_slow": float(slow.iloc[-1]),
        "_rsi": float(r.iloc[-1]),
    }

def compute_sl_tp_atr(price: float, atr_val: float, side: str) -> Tuple[float, float]:
    min_frac = 0.001
    max_frac = 0.012
    sl_dist = np.clip(0.35 * atr_val / price, min_frac, max_frac) * price
    tp_dist = np.clip(0.70 * atr_val / price, min_frac * 2, max_frac * 2) * price
    if side == "buy":
        return price * (1 - sl_dist / price), price * (1 + tp_dist / price)
    else:
        return price * (1 + sl_dist / price), price * (1 - tp_dist / price)

def decide_trade(ohlcv: pd.DataFrame) -> Dict[str, float | str]:
    if ohlcv is None or len(ohlcv) < 30:
        return {"signal": "hold", "sl": 0.0, "tp": 0.0, "score": 0.0}

    feats = build_features(ohlcv)
    score = scorer.score(feats)
    buy_th = 0.25
    sell_th = -0.25

    ema_agrees_buy = feats["_fast"] > feats["_slow"] and feats["_rsi"] > 50
    ema_agrees_sell = feats["_fast"] < feats["_slow"] and feats["_rsi"] < 50

    signal = "hold"
    if score >= buy_th and ema_agrees_buy:
        signal = "buy"
    elif score <= sell_th and ema_agrees_sell:
        signal = "sell"

    sl, tp = 0.0, 0.0
    if signal != "hold":
        sl, tp = compute_sl_tp_atr(price=feats["_close"], atr_val=feats["_atr"], side=signal)

    return {"signal": signal, "sl": float(sl), "tp": float(tp), "score": float(score)}

# Wrapper por compatibilidad
def decide_signal(ohlcv: pd.DataFrame) -> str:
    return decide_trade(ohlcv)["signal"]