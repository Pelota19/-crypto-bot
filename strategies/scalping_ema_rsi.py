"""Scalping strategy using EMA cross + RSI confirmation."""
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from config.settings import RISK_REWARD_RATIO
from utils.logger import get_logger

logger = get_logger(__name__)

class ScalpingEmaRsiStrategy:
    """EMA crossover + RSI confirmation scalping strategy."""
    
    def __init__(self, ema_short: int = 20, ema_medium: int = 50, ema_long: int = 100, 
                 rsi_period: int = 14, rsi_oversold: int = 30, rsi_overbought: int = 70):
        """Initialize strategy parameters."""
        self.ema_short = ema_short
        self.ema_medium = ema_medium  
        self.ema_long = ema_long
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        if df.empty or len(df) < self.ema_long:
            return df
        
        # Calculate EMAs
        df[f'ema_{self.ema_short}'] = df['close'].ewm(span=self.ema_short).mean()
        df[f'ema_{self.ema_medium}'] = df['close'].ewm(span=self.ema_medium).mean()
        df[f'ema_{self.ema_long}'] = df['close'].ewm(span=self.ema_long).mean()
        
        # Calculate RSI
        df['rsi'] = self._calculate_rsi(df['close'], self.rsi_period)
        
        # Calculate volume moving average for volume uptick detection
        df['volume_ma'] = df['volume'].rolling(window=10).mean()
        
        return df
    
    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on strategy rules."""
        if df.empty or len(df) < self.ema_long + 10:
            return {"signal": "hold", "reason": "insufficient_data"}
        
        # Calculate indicators
        df = self.calculate_indicators(df)
        
        # Get latest values
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        ema_short_current = current[f'ema_{self.ema_short}']
        ema_medium_current = current[f'ema_{self.ema_medium}']
        ema_long_current = current[f'ema_{self.ema_long}']
        
        ema_short_prev = previous[f'ema_{self.ema_short}']
        ema_medium_prev = previous[f'ema_{self.ema_medium}']
        
        rsi_current = current['rsi']
        rsi_prev = previous['rsi']
        
        price_current = current['close']
        volume_current = current['volume']
        volume_ma = current['volume_ma']
        
        # Check for BUY signal
        ema_cross_bull = (ema_short_prev <= ema_medium_prev and 
                         ema_short_current > ema_medium_current)
        
        price_above_long_ema = price_current > ema_long_current
        
        rsi_cross_from_oversold = (rsi_prev <= self.rsi_oversold and 
                                  rsi_current > self.rsi_oversold)
        
        volume_uptick = volume_current > volume_ma * 1.2  # 20% above average
        
        if ema_cross_bull and price_above_long_ema and rsi_cross_from_oversold and volume_uptick:
            # Calculate entry, SL, and TP
            entry_price = price_current
            stop_loss, take_profit = self._calculate_levels(df, "buy", entry_price)
            
            return {
                "signal": "buy",
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "reason": "ema_cross_bull_rsi_oversold_volume_uptick"
            }
        
        # For now, we'll focus on BUY signals only for simplicity
        # Could add SELL signals for short positions in futures
        
        return {"signal": "hold", "reason": "no_setup"}
    
    def _calculate_levels(self, df: pd.DataFrame, side: str, entry_price: float) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels."""
        if side == "buy":
            # Stop loss: recent local low or 1% below entry (whichever is tighter)
            recent_low = df['low'].tail(20).min()
            percentage_sl = entry_price * 0.99  # 1% below entry
            
            stop_loss = max(recent_low, percentage_sl)
            
            # Take profit: entry + risk * risk_reward_ratio
            risk = entry_price - stop_loss
            take_profit = entry_price + (risk * RISK_REWARD_RATIO)
            
        else:  # sell (for short positions)
            # Stop loss: recent local high or 1% above entry
            recent_high = df['high'].tail(20).max()
            percentage_sl = entry_price * 1.01  # 1% above entry
            
            stop_loss = min(recent_high, percentage_sl)
            
            # Take profit for short
            risk = stop_loss - entry_price
            take_profit = entry_price - (risk * RISK_REWARD_RATIO)
        
        return stop_loss, take_profit
    
    def validate_signal(self, signal: Dict, current_price: float) -> bool:
        """Validate that the signal is still valid."""
        if signal["signal"] == "hold":
            return True
        
        # Check if price hasn't moved too far from entry
        entry_price = signal["entry_price"]
        price_change = abs(current_price - entry_price) / entry_price
        
        # If price moved more than 0.5% from entry, signal is stale
        if price_change > 0.005:
            logger.warning(f"Signal stale: price moved {price_change*100:.2f}% from entry")
            return False
        
        return True