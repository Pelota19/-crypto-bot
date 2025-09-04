"""
Pair selection and analysis module.
Analyzes symbols and returns top candidates based on momentum/volume scoring.
Fully async.
"""
import asyncio
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

class PairSelector:
    """Select top symbols based on analysis."""

    def __init__(self, exchange):
        self.exchange = exchange

    async def analyze_symbol(self, symbol: str) -> Tuple[str, Dict]:
        """Fetch data and calculate simple metrics like momentum and volume."""
        try:
            raw = await self.exchange.fetch_ohlcv(symbol, timeframe="1m", limit=200)
            if not raw:
                return (symbol, {})
            import pandas as pd
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            mom = df["close"].iloc[-1] - df["close"].iloc[-2]
            volume = df["volume"].sum()
            return (symbol, {"mom": mom, "volume": volume})
        except Exception as e:
            logger.warning("Failed to analyze symbol %s: %s", symbol, e)
            return (symbol, {})

    async def select_top_symbols_async(
        self, symbols: List[str], position_size_percent: float, top_n: int = 5
    ) -> List[Tuple[str, Dict]]:
        """Return top N symbols sorted by momentum * volume."""
        tasks = [self.analyze_symbol(sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: List[Tuple[str, Dict]] = []
        for r in results:
            if isinstance(r, tuple) and r[1]:
                candidates.append(r)

        candidates.sort(key=lambda x: x[1].get("mom", 0) * x[1].get("volume", 0), reverse=True)

        return candidates[:top_n]
