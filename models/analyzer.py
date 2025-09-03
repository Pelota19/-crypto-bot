"""Market analyzer for computing indicators and AI predictions."""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

class MarketAnalyzer:
    """Provides market analysis with basic indicators and AI prediction stub."""
    
    def __init__(self):
        """Initialize the market analyzer."""
        pass
    
    def compute_indicators(self, df: pd.DataFrame) -> Dict:
        """Compute basic market indicators."""
        if df.empty or len(df) < 50:
            return {"error": "insufficient_data"}
        
        try:
            # EMA indicators
            ema20 = df['close'].ewm(span=20).mean().iloc[-1]
            ema50 = df['close'].ewm(span=50).mean().iloc[-1]
            
            # ATR (Average True Range)
            atr = self._calculate_atr(df, period=14)
            
            # Current price
            current_price = df['close'].iloc[-1]
            
            # Price position relative to EMAs
            price_vs_ema20 = (current_price - ema20) / ema20 * 100
            price_vs_ema50 = (current_price - ema50) / ema50 * 100
            
            # Volume analysis
            volume_sma = df['volume'].rolling(window=20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / volume_sma if volume_sma > 0 else 1.0
            
            # Volatility measure
            volatility = df['close'].pct_change().rolling(window=20).std().iloc[-1] * 100
            
            return {
                "ema20": round(ema20, 4),
                "ema50": round(ema50, 4),
                "atr": round(atr, 4),
                "current_price": round(current_price, 4),
                "price_vs_ema20_pct": round(price_vs_ema20, 2),
                "price_vs_ema50_pct": round(price_vs_ema50, 2),
                "volume_ratio": round(volume_ratio, 2),
                "volatility_pct": round(volatility, 2),
                "timestamp": df['timestamp'].iloc[-1].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error computing indicators: {e}")
            return {"error": str(e)}
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else 0.0
    
    def ai_prediction(self, df: pd.DataFrame, indicators: Dict) -> Dict:
        """Stub AI prediction (no heavy ML dependencies)."""
        if df.empty or 'error' in indicators:
            return {
                "prediction": "neutral",
                "confidence": 0.0,
                "reason": "insufficient_data"
            }
        
        try:
            # Simple rule-based "AI" prediction
            price_vs_ema20 = indicators.get("price_vs_ema20_pct", 0)
            price_vs_ema50 = indicators.get("price_vs_ema50_pct", 0) 
            volume_ratio = indicators.get("volume_ratio", 1.0)
            volatility = indicators.get("volatility_pct", 0)
            
            # Bullish conditions
            bullish_score = 0
            bearish_score = 0
            
            # Price above EMAs
            if price_vs_ema20 > 0:
                bullish_score += 1
            else:
                bearish_score += 1
                
            if price_vs_ema50 > 0:
                bullish_score += 1
            else:
                bearish_score += 1
            
            # Volume confirmation
            if volume_ratio > 1.2:  # Above average volume
                if price_vs_ema20 > 0:
                    bullish_score += 1
                else:
                    bearish_score += 1
            
            # Volatility consideration
            if volatility < 2.0:  # Low volatility might precede breakout
                bullish_score += 0.5
            elif volatility > 5.0:  # High volatility - caution
                bearish_score += 0.5
            
            # Recent momentum
            recent_returns = df['close'].pct_change().tail(5).mean()
            if recent_returns > 0.001:  # Recent positive momentum
                bullish_score += 1
            elif recent_returns < -0.001:  # Recent negative momentum
                bearish_score += 1
            
            # Determine prediction
            total_score = bullish_score + bearish_score
            if total_score == 0:
                prediction = "neutral"
                confidence = 0.0
            else:
                if bullish_score > bearish_score:
                    prediction = "bullish"
                    confidence = min(bullish_score / (bullish_score + bearish_score), 0.8)
                elif bearish_score > bullish_score:
                    prediction = "bearish"
                    confidence = min(bearish_score / (bullish_score + bearish_score), 0.8)
                else:
                    prediction = "neutral"
                    confidence = 0.5
            
            reason_parts = []
            if price_vs_ema20 > 0 and price_vs_ema50 > 0:
                reason_parts.append("price_above_emas")
            elif price_vs_ema20 < 0 and price_vs_ema50 < 0:
                reason_parts.append("price_below_emas")
            
            if volume_ratio > 1.2:
                reason_parts.append("high_volume")
            
            if recent_returns > 0.001:
                reason_parts.append("positive_momentum")
            elif recent_returns < -0.001:
                reason_parts.append("negative_momentum")
            
            reason = "_".join(reason_parts) if reason_parts else "mixed_signals"
            
            return {
                "prediction": prediction,
                "confidence": round(confidence, 3),
                "reason": reason,
                "bullish_score": bullish_score,
                "bearish_score": bearish_score
            }
            
        except Exception as e:
            logger.error(f"Error in AI prediction: {e}")
            return {
                "prediction": "neutral",
                "confidence": 0.0,
                "reason": f"error_{str(e)[:20]}"
            }
    
    def analyze_market(self, df: pd.DataFrame) -> Dict:
        """Complete market analysis including indicators and AI prediction."""
        indicators = self.compute_indicators(df)
        ai_pred = self.ai_prediction(df, indicators)
        
        return {
            "indicators": indicators,
            "ai_prediction": ai_pred
        }