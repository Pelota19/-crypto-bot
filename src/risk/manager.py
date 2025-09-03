"""
Risk manager utilities.
- Enforce CAPITAL_MAX_USDT cap
- Provide simple position sizing helpers
"""
from __future__ import annotations
from typing import Optional
from config.settings import CAPITAL_MAX_USDT, MAX_RISK_PER_TRADE
from src.state import bot_state

def cap_equity(equity_usdt: float) -> float:
    """Cap the usable equity to CAPITAL_MAX_USDT."""
    return min(max(0.0, equity_usdt), float(CAPITAL_MAX_USDT))

def usd_to_base(amount_usd: float, price: float) -> float:
    """Convert USD value to base asset units (e.g., USD -> BTC)."""
    if price <= 0 or amount_usd <= 0:
        return 0.0
    return amount_usd / price

def position_size_from_risk(equity_usdt: float, risk_pct: float) -> float:
    """
    Given equity and risk percentage (0..100), return USD allocation for a trade.
    Ensures we don't exceed the capital cap.
    """
    usable = cap_equity(equity_usdt)
    pct = max(0.0, min(100.0, float(risk_pct)))
    return usable * (pct / 100.0)

class RiskManager:
    """Simple Risk Manager placeholder with basic checks."""

    def can_open_new_trade(self, pair: str) -> bool:
        """Placeholder: don't open if bot is paused or we've reached max open trades (caller checks LIMIT)."""
        if bot_state.is_paused:
            return False
        return True

    def calculate_position_size_usd(self, equity_usdt: float) -> float:
        """Return USD to allocate based on configured MAX_RISK_PER_TRADE and capital cap."""
        return position_size_from_risk(equity_usdt, MAX_RISK_PER_TRADE)
