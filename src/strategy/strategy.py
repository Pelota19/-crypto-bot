import pandas as pd
import numpy as np

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def decide_signal(ohlcv: pd.DataFrame) -> str:
    # Espera columnas: ["timestamp","open","high","low","close","volume"]
    if ohlcv is None or len(ohlcv) < 30:
        return "hold"
    close = ohlcv["close"]
    fast = ema(close, 9)
    slow = ema(close, 21)
    rsi = compute_rsi(close, 14)

    last_fast = fast.iloc[-1]
    last_slow = slow.iloc[-1]
    last_rsi = rsi.iloc[-1]

    # Filtro rsi y cruce EMA
    if last_fast > last_slow and last_rsi > 55:
        return "buy"
    if last_fast < last_slow and last_rsi < 45:
        return "sell"
    return "hold"
