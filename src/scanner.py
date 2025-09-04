# src/scanner.py
"""
Market scanner: actualizar_watchlist() que obtiene símbolos futures USDT-M,
filtra por volumen 24h y por ATR(14) en timeframe 15m.
"""

import asyncio
import logging
from typing import List, Dict, Any, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

async def fetch_all_symbols(exchange_client) -> List[str]:
    """Devuelve lista de símbolos para futuros USDT-M (filtrados por quote USDT)."""
    try:
        markets = await exchange_client.exchange.load_markets()
        # markets is dict: symbol -> market
        res = []
        for sym, info in markets.items():
            try:
                # keep only USDT-M futures typical symbols like BTC/USDT
                if info.get("future") or info.get("type") == "future" or "USDT" in sym:
                    # enforce symbol format like "BTC/USDT"
                    if sym.endswith("/USDT"):
                        res.append(sym)
            except Exception:
                continue
        return sorted(list(set(res)))
    except Exception as e:
        logger.exception("fetch_all_symbols error: %s", e)
        return []

def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Simple ATR calculation (returns last ATR value)."""
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return float(atr.iloc[-1]) if not atr.empty else 0.0

async def symbol_24h_volume_usdt(exchange_client, symbol: str) -> float:
    """Try to read 24h quoteVolume or use ticker quoteVolume."""
    try:
        ticker = await exchange_client.fetch_ticker(symbol)
        # prefer quoteVolume or baseVolume * last price
        qv = ticker.get("quoteVolume") or ticker.get("quoteVolume24h") or 0
        if qv:
            return float(qv)
        # fallback compute from OHLCV
        return 0.0
    except Exception:
        return 0.0

async def symbol_atr_ratio(exchange_client, symbol: str, timeframe: str = "15m") -> Tuple[float, float]:
    """
    Return (ATR, last close) for symbol using timeframe.
    If error returns (0,0).
    """
    try:
        raw = await exchange_client.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        if not raw:
            return 0.0, 0.0
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df["close"] = pd.to_numeric(df["close"])
        atr = compute_atr(df, period=14)
        last_close = float(df["close"].iloc[-1])
        return float(atr), last_close
    except Exception as e:
        logger.warning("symbol_atr_ratio error %s %s", symbol, e)
        return 0.0, 0.0

async def actualizar_watchlist(exchange_client,
                              min_volume_usdt: float = 50_000_000.0,
                              atr_ratio_threshold: float = 0.005,
                              max_symbols: int = 15) -> List[str]:
    """
    Returns list of top symbols filtered by volume and ATR ratio.
    Runs full scan and returns top `max_symbols` by 24h volume.
    """
    logger.info("Starting market scan for watchlist")
    all_syms = await fetch_all_symbols(exchange_client)
    candidates = []

    # We'll run symbol tasks concurrently but in controlled batches to not exhaust rate limits.
    sem = asyncio.Semaphore(12)  # tune depending on rate-limit
    async def _check(sym):
        async with sem:
            vol = await symbol_24h_volume_usdt(exchange_client, sym)
            if vol < min_volume_usdt:
                return None
            atr, last = await symbol_atr_ratio(exchange_client, sym, timeframe="15m")
            if last <= 0:
                return None
            ratio = (atr / last) if last else 0.0
            if ratio < atr_ratio_threshold:
                return None
            return (sym, vol, ratio)

    tasks = [asyncio.create_task(_check(s)) for s in all_syms]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, tuple):
            candidates.append(r)

    # sort by volume desc
    candidates.sort(key=lambda x: x[1], reverse=True)
    watch = [c[0] for c in candidates[:max_symbols]]
    logger.info("Watchlist updated: %s", watch)
    return watch
