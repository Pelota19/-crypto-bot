"""Risk management module."""
from typing import Dict, Optional
from datetime import datetime, date
from config.settings import (
    MAX_INVESTMENT, MAX_RISK_PER_TRADE, MAX_OPEN_TRADES,
    MAX_DAILY_DRAWDOWN, DAILY_PROFIT_TARGET
)
from utils.logger import get_logger

logger = get_logger(__name__)

class RiskManager:
    """Manages trading risk and position sizing."""
    
    def __init__(self):
        """Initialize risk manager."""
        self.open_positions: Dict[str, Dict] = {}
        self.daily_pnl = 0.0
        self.daily_drawdown = 0.0
        self.current_date = date.today()
        self.available_capital = MAX_INVESTMENT
        self.daily_target_reached = False
        
    def reset_daily_metrics(self):
        """Reset daily metrics at midnight."""
        today = date.today()
        if today != self.current_date:
            logger.info("Resetting daily metrics")
            self.current_date = today
            self.daily_pnl = 0.0
            self.daily_drawdown = 0.0
            self.daily_target_reached = False
            # Reset available capital to max investment
            self.available_capital = MAX_INVESTMENT
    
    def can_open_position(self, symbol: str) -> bool:
        """Check if we can open a new position."""
        self.reset_daily_metrics()
        
        # Check if daily target reached
        if self.daily_target_reached or self.daily_pnl >= DAILY_PROFIT_TARGET:
            if not self.daily_target_reached:
                logger.info(f"Daily profit target reached: ${self.daily_pnl:.2f}")
                self.daily_target_reached = True
            return False
        
        # Check daily drawdown limit
        max_daily_loss = MAX_INVESTMENT * (MAX_DAILY_DRAWDOWN / 100)
        if self.daily_drawdown >= max_daily_loss:
            logger.warning(f"Daily drawdown limit reached: ${self.daily_drawdown:.2f}")
            return False
        
        # Check max open trades
        if len(self.open_positions) >= MAX_OPEN_TRADES:
            logger.warning(f"Max open trades limit reached: {len(self.open_positions)}")
            return False
        
        # Check if position already exists for this symbol
        if symbol in self.open_positions:
            logger.warning(f"Position already exists for {symbol}")
            return False
        
        # Check available capital
        if self.available_capital <= 0:
            logger.warning("No available capital for new positions")
            return False
        
        return True
    
    def calculate_position_size(self, entry_price: float, stop_loss: float, symbol: str) -> float:
        """Calculate position size based on risk management rules."""
        if entry_price <= 0 or stop_loss <= 0:
            logger.error("Invalid entry price or stop loss")
            return 0.0
        
        # Calculate risk amount (percentage of max investment)
        max_risk_amount = MAX_INVESTMENT * (MAX_RISK_PER_TRADE / 100)
        
        # Calculate price difference (risk per unit)
        price_diff = abs(entry_price - stop_loss)
        if price_diff == 0:
            logger.error("Entry price equals stop loss")
            return 0.0
        
        # Calculate position size: risk_amount / price_diff
        position_size = max_risk_amount / price_diff
        
        # Cap by available capital
        max_position_value = self.available_capital
        max_position_size = max_position_value / entry_price
        
        final_position_size = min(position_size, max_position_size)
        
        logger.info(
            f"Position sizing for {symbol}: "
            f"entry={entry_price:.4f}, sl={stop_loss:.4f}, "
            f"risk_amount=${max_risk_amount:.2f}, "
            f"position_size={final_position_size:.6f}"
        )
        
        return final_position_size
    
    def open_position(self, symbol: str, side: str, entry_price: float, 
                     stop_loss: float, take_profit: float, position_size: float):
        """Register a new open position."""
        position_value = position_size * entry_price
        
        self.open_positions[symbol] = {
            "side": side,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size": position_size,
            "position_value": position_value,
            "open_time": datetime.now()
        }
        
        # Reduce available capital
        self.available_capital -= position_value
        
        logger.info(
            f"Position opened: {side} {position_size:.6f} {symbol} @ {entry_price:.4f}, "
            f"SL: {stop_loss:.4f}, TP: {take_profit:.4f}, "
            f"value: ${position_value:.2f}"
        )
    
    def close_position(self, symbol: str, exit_price: float, reason: str = "unknown"):
        """Close a position and update PnL."""
        if symbol not in self.open_positions:
            logger.warning(f"No open position found for {symbol}")
            return 0.0
        
        position = self.open_positions[symbol]
        entry_price = position["entry_price"]
        position_size = position["position_size"]
        side = position["side"]
        
        # Calculate PnL
        if side == "buy":
            pnl = (exit_price - entry_price) * position_size
        else:  # sell
            pnl = (entry_price - exit_price) * position_size
        
        # Update daily metrics
        self.daily_pnl += pnl
        if pnl < 0:
            self.daily_drawdown += abs(pnl)
        
        # Free up capital
        self.available_capital += position["position_value"]
        
        # Remove position
        del self.open_positions[symbol]
        
        logger.info(
            f"Position closed: {symbol} @ {exit_price:.4f}, "
            f"PnL: ${pnl:.2f}, reason: {reason}, "
            f"daily_pnl: ${self.daily_pnl:.2f}"
        )
        
        return pnl
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position data for a symbol."""
        return self.open_positions.get(symbol)
    
    def get_daily_stats(self) -> Dict:
        """Get daily trading statistics."""
        self.reset_daily_metrics()
        
        return {
            "daily_pnl": self.daily_pnl,
            "daily_drawdown": self.daily_drawdown,
            "open_positions": len(self.open_positions),
            "available_capital": self.available_capital,
            "target_reached": self.daily_target_reached,
            "target_amount": DAILY_PROFIT_TARGET,
            "max_drawdown": MAX_INVESTMENT * (MAX_DAILY_DRAWDOWN / 100)
        }