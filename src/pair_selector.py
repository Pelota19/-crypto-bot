"""
Pair Selector module.
Selecciona los mejores pares para operar en Binance Futures (Testnet/Real).
Asíncrono, optimizado para trabajar dentro del event loop.
"""

import logging
import pandas as pd
import asyncio
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class PairSelector:
    def __init__(self, exchange):
        """
        Inicializa el selector de pares.
        :param exchange: Cliente de exchange (BinanceClient)
        """
        self.exchange = exchange

    async def analyze_symbol(self, symbol: str, position_size_percent: float) -> Optional[Tuple[str, float]]:
        """
        Analiza un símbolo individual y devuelve un score.
        Retorna (symbol, score) o None si falla.
        """
        try:
            raw = await self.exchange.fetch_ohlcv(symbol, timeframe="1m", limit=200)
            if not raw:
                return None

            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            # Métricas simples
            df["returns"] = df["close"].pct_change()
            momentum = df["close"].iloc[-1] / df["close"].iloc[0] - 1
            volatility = df["returns"].std()

            # Score simple: momentum positivo y volatilidad moderada
            score = momentum / (volatility + 1e-6)

            return (symbol, score)

        except Exception as e:
            logger.warning("Failed to analyze symbol %s: %s", symbol, e)
            return None

    async def select_top_symbols_async(
        self,
        symbols: List[str],
        position_size_percent: float,
        max_symbols: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Analiza múltiples símbolos de forma asíncrona y selecciona los mejores.
        :param symbols: lista de símbolos (ej. ["BTC/USDT", "ETH/USDT"])
        :param position_size_percent: % del capital por trade
        :param max_symbols: número máximo de símbolos a devolver
        :return: lista [(symbol, score), ...] ordenada por score
        """
        tasks = [
            self.analyze_symbol(sym, position_size_percent)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates = []
        for res in results:
            if isinstance(res, tuple) and len(res) == 2:
                candidates.append(res)

        # Ordenar por score descendente
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:max_symbols]
