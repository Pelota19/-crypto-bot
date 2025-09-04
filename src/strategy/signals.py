# src/strategy/signals.py
"""
Indicator calculations and entry signal detection.
EMA, RSI, ATR usage using pandas.
"""

import pandas as pd
import numpy as np

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = -delta.clip(upper=0).rolling(period).mean()
    rs = up / (down.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean().fillna(0)

def compute_indicators(df_1m: pd.DataFrame, df_15m: pd.DataFrame) -> dict:
    """
    Expects dataframes with numeric close, high, low columns.
    Returns dict with ema9, ema21, ema50_15m (last values), rsi14, atr14_15m, etc.
    """
    close1 = pd.to_numeric(df_1m["close"])
    close15 = pd.to_numeric(df_15m["close"])

    ema9 = ema(close1, 9).iloc[-1]
    ema21 = ema(close1, 21).iloc[-1]
    rsi14 = rsi(close1, 14).iloc[-1]
    ema50_15 = ema(close15, 50).iloc[-1]
    atr15 = atr(df_15m, 14).iloc[-1]
    last_price = float(close1.iloc[-1])

    return {
        "ema9": ema9,
        "ema21": ema21,
        "ema50_15": ema50_15,
        "rsi14": rsi14,
        "atr15": atr15,
        "last_price": last_price
    }

def is_long_signal(indicators: dict) -> bool:
    return (indicators["last_price"] > indicators["ema50_15"] and
            indicators["ema9"] > indicators["ema21"] and
            indicators["rsi14"] < 65)

def is_short_signal(indicators: dict) -> bool:
    return (indicators["last_price"] < indicators["ema50_15"] and
            indicators["ema9"] < indicators["ema21"] and
            indicators["rsi14"] > 35)
