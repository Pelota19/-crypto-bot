from __future__ import annotations
try:
    from src.config import CAPITAL_MAX_USDT
except ImportError:
    CAPITAL_MAX_USDT = 2000.0

def position_size_in_base(equity_usdt: float, pct: float, price: float) -> float:
    # pct expresado 0..1
    # Cap the equity at CAPITAL_MAX_USDT for position sizing
    capped_equity = min(equity_usdt, CAPITAL_MAX_USDT)
    usd = max(0.0, capped_equity * max(0.0, min(1.0, pct)))
    if price <= 0:
        return 0.0
    return usd / price

class RiskManager:
    """Placeholder risk manager."""
    
    def can_open_new_trade(self, pair: str) -> bool:
        """Check if a new trade can be opened for the pair."""
        # Placeholder implementation
        return True
    
    def calculate_position_size(self) -> float:
        """Calculate position size in USD."""
        # Placeholder implementation
        return 100.0