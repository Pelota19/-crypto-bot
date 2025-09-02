"""
Dynamic universe selector for liquidity-aware symbol selection.
Selects trading symbols based on volume, spread, depth, and volatility criteria.
"""
from __future__ import annotations
import logging
import time
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

log = logging.getLogger(__name__)

@dataclass
class SymbolMetrics:
    """Metrics for a trading symbol."""
    symbol: str
    quote_volume_24h_usdt: float
    spread_bps: float
    depth_usdt_within_5bps: float
    rvol_1m_bps: float
    last_price: float
    bid: float
    ask: float

class UniverseSelector:
    """Selects trading universe based on liquidity and volatility criteria."""
    
    def __init__(self, plan_loader):
        self.plan_loader = plan_loader
        self._cached_symbols: Optional[List[str]] = None
        self._last_refresh: Optional[float] = None
        self._symbol_metrics: Dict[str, SymbolMetrics] = {}

    def get_active_symbols(self, exchange_client) -> List[str]:
        """Get active symbols based on plan configuration."""
        plan = self.plan_loader.get_plan()
        
        if plan.universe.mode == "static":
            # Return static symbols excluding any excluded ones
            symbols = [s for s in plan.universe.static_symbols if s not in plan.universe.exclude_symbols]
            log.debug(f"Using static universe: {symbols}")
            return symbols
        
        elif plan.universe.mode == "dynamic":
            return self._get_dynamic_symbols(exchange_client)
        
        else:
            # Fallback to static symbols
            symbols = [s for s in plan.universe.static_symbols if s not in plan.universe.exclude_symbols]
            log.warning(f"Unknown universe mode '{plan.universe.mode}', using static fallback: {symbols}")
            return symbols

    def _get_dynamic_symbols(self, exchange_client) -> List[str]:
        """Get dynamically selected symbols based on liquidity metrics."""
        plan = self.plan_loader.get_plan()
        selector_config = plan.universe.dynamic_selector
        
        # Check if refresh is needed
        now = time.time()
        refresh_interval_sec = selector_config.refresh_interval_min * 60
        
        if (self._cached_symbols is not None and 
            self._last_refresh is not None and 
            now - self._last_refresh < refresh_interval_sec):
            log.debug(f"Using cached dynamic universe: {self._cached_symbols}")
            return self._cached_symbols
        
        try:
            log.info("Refreshing dynamic universe selection...")
            
            # Get available symbols
            available_symbols = self._get_available_symbols(exchange_client)
            
            # Filter out excluded symbols
            available_symbols = [s for s in available_symbols if s not in plan.universe.exclude_symbols]
            
            # Compute metrics for each symbol
            symbol_metrics = self._compute_symbol_metrics(available_symbols, exchange_client)
            
            # Apply filters
            filtered_symbols = self._apply_filters(symbol_metrics, selector_config)
            
            # Limit to max symbols
            selected_symbols = filtered_symbols[:selector_config.max_symbols]
            
            # Cache results
            self._cached_symbols = selected_symbols
            self._last_refresh = now
            self._symbol_metrics = {s.symbol: s for s in symbol_metrics if s.symbol in selected_symbols}
            
            log.info(f"Selected {len(selected_symbols)} symbols for dynamic universe: {selected_symbols}")
            return selected_symbols
            
        except Exception as e:
            log.error(f"Error in dynamic symbol selection: {e}")
            # Fallback to static symbols
            fallback_symbols = [s for s in plan.universe.static_symbols if s not in plan.universe.exclude_symbols]
            log.warning(f"Falling back to static universe: {fallback_symbols}")
            return fallback_symbols

    def _get_available_symbols(self, exchange_client) -> List[str]:
        """Get list of available USDT perpetual symbols from exchange."""
        try:
            # Use existing method from exchange client
            symbols = exchange_client.get_usdt_perp_symbols(min_volume=0, max_symbols=1000)
            log.debug(f"Found {len(symbols)} available USDT perpetual symbols")
            return symbols
        except Exception as e:
            log.error(f"Error fetching available symbols: {e}")
            # Fallback to common symbols
            return ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT"]

    def _compute_symbol_metrics(self, symbols: List[str], exchange_client) -> List[SymbolMetrics]:
        """Compute liquidity and volatility metrics for symbols."""
        metrics = []
        
        for symbol in symbols:
            try:
                # Get ticker data
                ticker = self._get_ticker_safe(symbol, exchange_client)
                if not ticker:
                    continue
                
                # Extract basic data
                last_price = float(ticker.get('last', 0))
                bid = float(ticker.get('bid', 0))
                ask = float(ticker.get('ask', 0))
                quote_volume_24h = float(ticker.get('quoteVolume', 0))
                
                if last_price <= 0 or bid <= 0 or ask <= 0:
                    log.debug(f"Invalid price data for {symbol}, skipping")
                    continue
                
                # Compute spread in basis points
                spread_bps = ((ask - bid) / last_price) * 10000 if last_price > 0 else float('inf')
                
                # Compute realized volatility (simplified)
                rvol_1m_bps = self._compute_realized_volatility(symbol, exchange_client)
                
                # Get order book depth (best effort)
                depth_usdt = self._compute_depth_within_5bps(symbol, last_price, exchange_client)
                
                metrics.append(SymbolMetrics(
                    symbol=symbol,
                    quote_volume_24h_usdt=quote_volume_24h,
                    spread_bps=spread_bps,
                    depth_usdt_within_5bps=depth_usdt,
                    rvol_1m_bps=rvol_1m_bps,
                    last_price=last_price,
                    bid=bid,
                    ask=ask
                ))
                
            except Exception as e:
                log.debug(f"Error computing metrics for {symbol}: {e}")
                continue
        
        log.debug(f"Computed metrics for {len(metrics)} symbols")
        return metrics

    def _get_ticker_safe(self, symbol: str, exchange_client) -> Optional[Dict]:
        """Safely get ticker data for a symbol."""
        try:
            # Use ccxt to fetch ticker
            if hasattr(exchange_client, 'exchange'):
                ticker = exchange_client.exchange.fetch_ticker(symbol)
                return ticker
            else:
                log.debug(f"Exchange client doesn't have expected interface for {symbol}")
                return None
        except Exception as e:
            log.debug(f"Error fetching ticker for {symbol}: {e}")
            return None

    def _compute_realized_volatility(self, symbol: str, exchange_client) -> float:
        """Compute realized volatility in basis points (simplified implementation)."""
        try:
            # Fetch recent OHLCV data
            df = exchange_client.fetch_ohlcv_df(symbol, timeframe="1m", limit=30)
            if df.empty or len(df) < 10:
                return 0.0
            
            # Compute returns
            returns = df['close'].pct_change().dropna()
            if len(returns) < 5:
                return 0.0
            
            # Compute realized volatility as standard deviation of returns
            rvol = returns.std() * np.sqrt(60)  # Annualize to 1 hour
            rvol_bps = rvol * 10000  # Convert to basis points
            
            return max(0.0, rvol_bps)
            
        except Exception as e:
            log.debug(f"Error computing realized volatility for {symbol}: {e}")
            return 0.0

    def _compute_depth_within_5bps(self, symbol: str, price: float, exchange_client) -> float:
        """Compute order book depth within 5 basis points (best effort)."""
        try:
            # This is a simplified implementation
            # In practice, you would fetch the order book and sum liquidity
            # within the specified price range
            
            # For now, return a placeholder based on symbol popularity
            popular_symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]
            if symbol in popular_symbols:
                return 100000.0  # Assume good depth for popular symbols
            else:
                return 50000.0   # Assume moderate depth for others
                
        except Exception as e:
            log.debug(f"Error computing depth for {symbol}: {e}")
            return 0.0

    def _apply_filters(self, metrics: List[SymbolMetrics], config) -> List[str]:
        """Apply liquidity and volatility filters to symbol metrics."""
        filtered = []
        
        for metric in metrics:
            # Filter by minimum 24h quote volume
            if metric.quote_volume_24h_usdt < config.min_quote_volume_24h_usdt:
                log.debug(f"{metric.symbol}: volume {metric.quote_volume_24h_usdt:.0f} < {config.min_quote_volume_24h_usdt:.0f}")
                continue
            
            # Filter by maximum spread
            if metric.spread_bps > config.max_spread_bps:
                log.debug(f"{metric.symbol}: spread {metric.spread_bps:.2f}bps > {config.max_spread_bps:.2f}bps")
                continue
            
            # Filter by minimum depth (if available)
            if metric.depth_usdt_within_5bps < config.min_depth_usdt_within_5bps:
                log.debug(f"{metric.symbol}: depth {metric.depth_usdt_within_5bps:.0f} < {config.min_depth_usdt_within_5bps:.0f}")
                continue
            
            # Filter by minimum realized volatility
            if metric.rvol_1m_bps < config.min_rvol_1m_bps:
                log.debug(f"{metric.symbol}: rvol {metric.rvol_1m_bps:.2f}bps < {config.min_rvol_1m_bps:.2f}bps")
                continue
            
            filtered.append(metric.symbol)
        
        # Sort by 24h volume descending
        volume_map = {m.symbol: m.quote_volume_24h_usdt for m in metrics}
        filtered.sort(key=lambda s: volume_map.get(s, 0), reverse=True)
        
        log.debug(f"Applied filters: {len(filtered)} symbols passed from {len(metrics)} candidates")
        return filtered

    def get_symbol_metrics(self, symbol: str) -> Optional[SymbolMetrics]:
        """Get cached metrics for a symbol."""
        return self._symbol_metrics.get(symbol)

    def force_refresh(self) -> None:
        """Force refresh of symbol selection on next call."""
        self._cached_symbols = None
        self._last_refresh = None
        log.info("Forced refresh of dynamic universe selection")

# Global instance for easy access
_universe_selector: Optional[UniverseSelector] = None

def get_universe_selector(plan_loader=None) -> UniverseSelector:
    """Get global universe selector instance."""
    global _universe_selector
    if _universe_selector is None:
        if plan_loader is None:
            from src.config.plan_loader import get_plan_loader
            plan_loader = get_plan_loader()
        _universe_selector = UniverseSelector(plan_loader)
    return _universe_selector