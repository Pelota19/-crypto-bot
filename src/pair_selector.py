
import logging
from collections import namedtuple

logger = logging.getLogger(__name__)
Candidate = namedtuple("Candidate", ["symbol", "score", "signal"])

class PairSelector:
    def __init__(self, exchange, position_pct):
        self.exchange = exchange
        self.position_pct = position_pct

    def select_top_symbols(self, symbols):
        candidates = []
        for sym in symbols:
            candidates.append(Candidate(symbol=sym, score=1.0, signal="buy"))
        return candidates
