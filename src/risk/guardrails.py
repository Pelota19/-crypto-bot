"""
Risk guardrails for enforcing trading limits and risk management.
Integrates with the plan-driven configuration system.
"""
from __future__ import annotations
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, date

log = logging.getLogger(__name__)

@dataclass
class TradeContext:
    """Context information for a potential trade."""
    symbol: str
    side: str  # buy/sell
    entry_price: float
    position_size_usd: float
    equity_usd: float
    current_positions: int = 0
    daily_pnl: float = 0.0

@dataclass
class RiskState:
    """Tracks current risk state across trading session."""
    daily_pnl: float = 0.0
    current_positions: int = 0
    last_reset_date: Optional[date] = None
    trade_count_today: int = 0
    max_daily_loss_hit: bool = False

class RiskGuardrails:
    """Risk management system that enforces plan-driven limits."""
    
    def __init__(self, plan_loader):
        self.plan_loader = plan_loader
        self.state = RiskState()
        self._reset_if_new_day()

    def _reset_if_new_day(self) -> None:
        """Reset daily tracking if it's a new day."""
        today = date.today()
        if self.state.last_reset_date != today:
            log.info(f"New trading day detected, resetting daily risk tracking")
            self.state.daily_pnl = 0.0
            self.state.trade_count_today = 0
            self.state.max_daily_loss_hit = False
            self.state.last_reset_date = today

    def should_open_trade(self, context: TradeContext) -> Dict[str, Any]:
        """
        Check if a trade should be opened based on risk guardrails.
        
        Returns:
            Dict with 'allowed' bool and optional 'reason' string
        """
        self._reset_if_new_day()
        plan = self.plan_loader.get_plan()

        # Check max concurrent positions
        if context.current_positions >= plan.risk.max_concurrent_positions:
            return {
                'allowed': False,
                'reason': f'Max concurrent positions reached ({plan.risk.max_concurrent_positions})'
            }

        # Check max daily loss
        max_daily_loss_usd = context.equity_usd * (plan.risk.max_daily_loss_pct / 100.0)
        if self.state.daily_pnl <= -max_daily_loss_usd:
            self.state.max_daily_loss_hit = True
            return {
                'allowed': False,
                'reason': f'Max daily loss reached ({plan.risk.max_daily_loss_pct}%)'
            }

        # Check position size against max risk per trade
        max_risk_usd = context.equity_usd * (plan.risk.max_risk_per_trade_pct / 100.0)
        if context.position_size_usd > max_risk_usd:
            return {
                'allowed': False,
                'reason': f'Position size exceeds max risk per trade ({plan.risk.max_risk_per_trade_pct}%)'
            }

        # All checks passed
        return {'allowed': True}

    def on_trade_opened(self, context: TradeContext) -> None:
        """Update state when a trade is opened."""
        self._reset_if_new_day()
        self.state.current_positions += 1
        self.state.trade_count_today += 1
        log.info(f"Trade opened: {context.symbol} {context.side}, positions: {self.state.current_positions}")

    def on_trade_closed(self, symbol: str, pnl_usd: float) -> None:
        """Update state when a trade is closed."""
        self._reset_if_new_day()
        
        # Update position count
        self.state.current_positions = max(0, self.state.current_positions - 1)
        
        # Update daily PnL
        self.state.daily_pnl += pnl_usd
        
        log.info(f"Trade closed: {symbol}, PnL: ${pnl_usd:.2f}, Daily PnL: ${self.state.daily_pnl:.2f}, positions: {self.state.current_positions}")

    def validate_position_size(self, equity_usd: float, requested_pct: float) -> float:
        """
        Validate and potentially adjust position size based on risk limits.
        
        Args:
            equity_usd: Current account equity
            requested_pct: Requested position size as percentage (0-100)
            
        Returns:
            Adjusted position size percentage (0-1 decimal)
        """
        plan = self.plan_loader.get_plan()
        
        # Convert to decimal if needed
        if requested_pct >= 1:
            requested_pct = requested_pct / 100.0
        
        # Cap at plan maximum
        max_size_pct = plan.risk.position_size_pct / 100.0
        if requested_pct > max_size_pct:
            log.warning(f"Requested position size {requested_pct*100:.2f}% exceeds plan maximum {plan.risk.position_size_pct}%, capping")
            requested_pct = max_size_pct
        
        # Ensure it doesn't exceed max risk per trade
        max_risk_pct = plan.risk.max_risk_per_trade_pct / 100.0
        if requested_pct > max_risk_pct:
            log.warning(f"Requested position size {requested_pct*100:.2f}% exceeds max risk per trade {plan.risk.max_risk_per_trade_pct}%, capping")
            requested_pct = max_risk_pct
        
        return requested_pct

    def get_risk_status(self) -> Dict[str, Any]:
        """Get current risk status for monitoring."""
        self._reset_if_new_day()
        plan = self.plan_loader.get_plan()
        
        return {
            'daily_pnl': self.state.daily_pnl,
            'current_positions': self.state.current_positions,
            'max_positions': plan.risk.max_concurrent_positions,
            'trade_count_today': self.state.trade_count_today,
            'max_daily_loss_hit': self.state.max_daily_loss_hit,
            'last_reset_date': self.state.last_reset_date.isoformat() if self.state.last_reset_date else None
        }

    def check_exchange_filters(self, symbol: str, amount: float, price: float, 
                             exchange_client) -> Dict[str, Any]:
        """
        Check if trade parameters comply with exchange filters.
        
        Returns:
            Dict with 'valid' bool and adjusted 'amount'/'price' if needed
        """
        try:
            # This is a placeholder for exchange filter validation
            # In a real implementation, you would check:
            # - LOT_SIZE filter for minimum/maximum quantity
            # - MIN_NOTIONAL filter for minimum notional value
            # - PRICE_FILTER for price precision
            # - Other exchange-specific filters
            
            # For now, just ensure positive values
            if amount <= 0 or price <= 0:
                return {
                    'valid': False,
                    'reason': 'Invalid amount or price',
                    'amount': amount,
                    'price': price
                }
            
            return {
                'valid': True,
                'amount': amount,
                'price': price
            }
            
        except Exception as e:
            log.error(f"Error checking exchange filters for {symbol}: {e}")
            return {
                'valid': False,
                'reason': f'Filter validation error: {e}',
                'amount': amount,
                'price': price
            }

# Global instance for easy access
_guardrails: Optional[RiskGuardrails] = None

def get_guardrails(plan_loader=None) -> RiskGuardrails:
    """Get global risk guardrails instance."""
    global _guardrails
    if _guardrails is None:
        if plan_loader is None:
            from src.config.plan_loader import get_plan_loader
            plan_loader = get_plan_loader()
        _guardrails = RiskGuardrails(plan_loader)
    return _guardrails