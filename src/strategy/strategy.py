"""
Simple strategy:
- EMA fast/slow crossover + RSI filter
- Returns one of: "buy", "sell", "hold"
This is a baseline strategy for testing. Later you can replace or augment
with ML/IA models using src/ai/* and src/strategy/predictor.py
"""
import pandas as pd
import numpy as np
from typing import Optional

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).fillna(0)
    down = -1 * delta.clip(upper=0).fillna(0)
    ma_up = up.ewm(alpha=1/period, adjust=False).mean()
    ma_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = ma_up / (ma_down + 1e-9)
    return 100 - (100 / (1 + rs))

def decide_signal(ohlcv: pd.DataFrame, fast: int = 12, slow: int = 26, rsi_period: int = 14, rsi_low: int = 30, rsi_high: int = 70) -> str:
    """
    ohlcv: DataFrame with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    """
    if ohlcv is None or ohlcv.empty or len(ohlcv) < slow + 5:
        return "hold"

    close = ohlcv["close"].astype(float)
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    rsi = compute_rsi(close, period=rsi_period)

    # Crossover
    if ema_fast.iloc[-2] <= ema_slow.iloc[-2] and ema_fast.iloc[-1] > ema_slow.iloc[-1] and rsi.iloc[-1] < rsi_high:
        return "buy"
    if ema_fast.iloc[-2] >= ema_slow.iloc[-2] and ema_fast.iloc[-1] < ema_slow.iloc[-1] and rsi.iloc[-1] > rsi_low:
        return "sell"

    return "hold"
