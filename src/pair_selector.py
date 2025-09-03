"""
Pair selection and ranking module for top-K symbol selection.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, NamedTuple
from dataclasses import dataclass

from src.strategy.strategy import decide_trade
from src.config import TIMEFRAME, MIN_NOTIONAL_USD, MAX_ACTIVE_SYMBOLS

log = logging.getLogger(__name__)


@dataclass
class SymbolCandidate:
    """Represents a candidate symbol with its analysis results."""
    symbol: str
    signal: str  # "buy", "sell", "hold"
    score: float
    sl: float
    tp: float
    last_price: float
    notional_usd: float
    is_feasible: bool
    feasible_reason: str
    volume_24h_usd: float


class PairSelector:
    """Handles pair selection and ranking logic."""
    
    def __init__(self, exchange, get_equity_func):
        self.exchange = exchange
        self.get_equity = get_equity_func
    
    def analyze_symbol(self, symbol: str, position_size_percent: float) -> SymbolCandidate:
        """
        Analyze a single symbol and return candidate info.
        
        Args:
            symbol: Trading symbol
            position_size_percent: Position size as fraction (e.g. 0.01 for 1%)
            
        Returns:
            SymbolCandidate with all analysis results
        """
        try:
            # Get OHLCV data
            df = self.exchange.fetch_ohlcv_df(symbol, timeframe=TIMEFRAME, limit=200)
            if df.empty or len(df) < 30:
                return SymbolCandidate(
                    symbol=symbol,
                    signal="hold",
                    score=0.0,
                    sl=0.0,
                    tp=0.0,
                    last_price=0.0,
                    notional_usd=0.0,
                    is_feasible=False,
                    feasible_reason="Insufficient OHLCV data",
                    volume_24h_usd=0.0
                )
            
            # Get trading signal and score
            trade_result = decide_trade(df)
            signal = trade_result["signal"]
            score = trade_result["score"]
            sl = trade_result["sl"]
            tp = trade_result["tp"]
            
            # Get price and volume info
            ticker_info = self.exchange.get_ticker_info(symbol)
            last_price = ticker_info["last_price"]
            volume_24h_usd = ticker_info["volume_24h_usd"]
            
            # Calculate notional
            equity = self.get_equity()
            notional_usd = equity * position_size_percent
            
            # Check feasibility
            is_feasible, feasible_reason = self.exchange.is_trade_feasible(
                symbol, notional_usd, last_price
            )
            
            # Additional check for minimum notional
            if is_feasible and notional_usd < MIN_NOTIONAL_USD:
                is_feasible = False
                feasible_reason = f"Notional {notional_usd:.2f} < MIN_NOTIONAL_USD {MIN_NOTIONAL_USD}"
            
            return SymbolCandidate(
                symbol=symbol,
                signal=signal,
                score=score,
                sl=sl,
                tp=tp,
                last_price=last_price,
                notional_usd=notional_usd,
                is_feasible=is_feasible,
                feasible_reason=feasible_reason,
                volume_24h_usd=volume_24h_usd
            )
            
        except Exception as e:
            log.warning(f"Failed to analyze symbol {symbol}: {e}")
            return SymbolCandidate(
                symbol=symbol,
                signal="hold",
                score=0.0,
                sl=0.0,
                tp=0.0,
                last_price=0.0,
                notional_usd=0.0,
                is_feasible=False,
                feasible_reason=f"Analysis failed: {str(e)}",
                volume_24h_usd=0.0
            )
    
    def select_top_symbols(self, symbols: List[str], position_size_percent: float, max_symbols: int = None) -> List[SymbolCandidate]:
        """
        Analyze all symbols and return top K candidates.
        
        Args:
            symbols: List of symbols to analyze
            position_size_percent: Position size as fraction
            max_symbols: Maximum number of symbols to return (defaults to MAX_ACTIVE_SYMBOLS)
            
        Returns:
            List of top SymbolCandidate objects, sorted by score desc, then volume desc
        """
        if max_symbols is None:
            max_symbols = MAX_ACTIVE_SYMBOLS
        
        log.debug(f"Analyzing {len(symbols)} symbols for top-K selection")
        
        candidates = []
        for symbol in symbols:
            candidate = self.analyze_symbol(symbol, position_size_percent)
            
            # Only keep symbols with non-hold signals that are feasible
            if candidate.signal != "hold" and candidate.is_feasible:
                candidates.append(candidate)
            else:
                log.debug(f"Filtered out {symbol}: signal={candidate.signal}, feasible={candidate.is_feasible}, reason={candidate.feasible_reason}")
        
        # Sort by score descending, then by volume descending for ties
        candidates.sort(key=lambda x: (-x.score, -x.volume_24h_usd))
        
        # Return top K
        selected = candidates[:max_symbols]
        
        log.info(f"Selected {len(selected)} symbols from {len(symbols)} candidates")
        for i, candidate in enumerate(selected):
            log.debug(f"  {i+1}. {candidate.symbol}: score={candidate.score:.3f}, signal={candidate.signal}, volume=${candidate.volume_24h_usd:.0f}")
        
        return selected
    
    def format_selection_summary(self, selected: List[SymbolCandidate], total_candidates: int) -> str:
        """
        Format a summary message of the selection results for Telegram.
        """
        if not selected:
            return f"📊 Ciclo: 0/{total_candidates} símbolos seleccionados (sin señales viables)"
        
        lines = [f"📊 Ciclo: {len(selected)}/{total_candidates} símbolos seleccionados"]
        
        for i, candidate in enumerate(selected, 1):
            lines.append(
                f"{i}. {candidate.symbol} {candidate.signal.upper()} "
                f"(score: {candidate.score:.3f}, vol: ${candidate.volume_24h_usd/1e6:.1f}M)"
            )
        
        return "\n".join(lines)