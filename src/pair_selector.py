import logging
import pandas as pd
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class PairSelector:
    """
    Selecciona los mejores símbolos basados en criterios de análisis técnico.
    """

    def __init__(self):
        pass

    def analyze_symbol(self, symbol: str, ohlcv: List[List[Any]]) -> Dict[str, Any]:
        """
        Analiza un símbolo y retorna métricas básicas.
        ohlcv: [[timestamp, open, high, low, close, volume], ...]
        """
        try:
            if not ohlcv or len(ohlcv) < 10:
                return None

            df = pd.DataFrame(
                ohlcv, columns=["ts", "open", "high", "low", "close", "volume"]
            )
            df["close"] = pd.to_numeric(df["close"], errors="coerce")

            sma_fast = df["close"].rolling(window=5).mean().iloc[-1]
            sma_slow = df["close"].rolling(window=20).mean().iloc[-1]
            momentum = df["close"].iloc[-1] / df["close"].iloc[-5] - 1

            return {
                "symbol": symbol,
                "sma_fast": sma_fast,
                "sma_slow": sma_slow,
                "momentum": momentum,
            }
        except Exception as e:
            logger.warning("Failed to analyze symbol %s: %s", symbol, e)
            return None

    def select_top_symbols(
        self, pairs: List[str], max_symbols: int, position_size_percent: float
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Selecciona los mejores símbolos para operar.
        - pairs: lista de símbolos
        - max_symbols: número máximo de símbolos a devolver
        - position_size_percent: tamaño de posición relativo
        """
        candidates = []

        for sym in pairs:
            try:
                # En esta versión se asume que el análisis ya fue hecho en otro lado
                # o será extendido aquí.
                # Placeholder: momentum positivo simulado
                metric = {"symbol": sym, "score": 1.0}
                candidates.append((sym, metric))
            except Exception as e:
                logger.warning("Error procesando símbolo %s: %s", sym, e)

        # Ordenar por score descendente (aquí fijo porque es placeholder)
        candidates = sorted(candidates, key=lambda x: x[1].get("score", 0), reverse=True)

        # Limitar cantidad de símbolos
        selected = candidates[:max_symbols]

        return selected
