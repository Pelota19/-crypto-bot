"""
Pair selector module.
Selecciona los mejores símbolos a operar en Binance Futures.
"""

import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class PairSelector:
    def __init__(self, exchange, position_size_percent: float = 0.01):
        """
        Inicializa el selector de pares.
        - exchange: cliente de exchange (ej. BinanceClient)
        - position_size_percent: porcentaje del equity a usar por trade
        """
        self.exchange = exchange
        self.position_size_percent = position_size_percent

    def select_top_symbols(
        self, pairs: List[str], max_symbols: int
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Selecciona los mejores símbolos para operar.
        - pairs: lista de símbolos
        - max_symbols: número máximo de símbolos a devolver
        """
        candidates = []

        for sym in pairs:
            try:
                # Placeholder simple: asignamos score fijo
                metric = {
                    "symbol": sym,
                    "score": 1.0,
                    "position_size_percent": self.position_size_percent,
                }
                candidates.append((sym, metric))
            except Exception as e:
                logger.warning("Error procesando símbolo %s: %s", sym, e)

        # Ordenamos por score descendente
        candidates = sorted(
            candidates, key=lambda x: x[1].get("score", 0), reverse=True
        )

        return candidates[:max_symbols]
