"""
Pair selector module.
Analyzes symbols and returns top candidates for trading.
"""

import logging
import asyncio
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)


class PairSelector:
    """Selects top trading pairs based on simple heuristics (momentum, volatility, volume)."""

    def __init__(self, exchange):
        self.exchange = exchange

    async def analyze_symbol(self, symbol: str) -> Tuple[str, Dict]:
        """Analyze a single symbol and return metrics dict."""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe="1m", limit=100)
            if not ohlcv:
                return symbol, {}

            closes = [c[4] for c in ohlcv]  # close prices
            mom = closes[-1] - closes[0]
            vol = sum([c[5] for c in ohlcv])
            rsi_centered = 0.0
            if len(closes) >= 2:
                deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
                up = sum([d for d in deltas if d > 0])
                down = -sum([d for d in deltas if d < 0]) or 1
                rs = up / down
                rsi_centered = rs - 1.0

            metrics = {"mom": mom, "rsi_centered": rsi_centered, "volume": vol}
            return symbol, metrics

        except Exception as e:
            logger.warning("Failed to analyze symbol %s: %s", symbol, e)
            return symbol, {}

    def select_top_symbols(
        self, symbols: List[str], position_size_percent: float, top_n: int = 5
    ) -> List[Tuple[str, Dict]]:
        """Return top N symbols sorted by momentum and volume."""
        loop = asyncio.get_event_loop()
        tasks = [self.analyze_symbol(sym) for sym in symbols]
        results = loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

        candidates: List[Tuple[str, Dict]] = []
        for r in results:
            if isinstance(r, tuple):
                candidates.append(r)

        # Filter out empty metrics
        candidates = [(s, m) for s, m in candidates if m]

        # Sort by simple score: momentum * volume
        candidates.sort(key=lambda x: x[1].get("mom", 0) * x[1].get("volume", 0), reverse=True)

        # Return top N
        return candidates[:top_n]
