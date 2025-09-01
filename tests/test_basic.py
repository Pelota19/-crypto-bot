"""Basic tests for the crypto bot functionality."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, Mock
from core.risk_manager import RiskManager
from strategies.scalping_ema_rsi import ScalpingEmaRsiStrategy
from models.analyzer import MarketAnalyzer
from config.settings import MAX_INVESTMENT, MAX_RISK_PER_TRADE, MAX_OPEN_TRADES

class TestRiskManager:
    """Test risk management functionality."""
    
    def test_position_sizing(self):
        """Test position size calculation."""
        rm = RiskManager()
        
        # Test basic position sizing
        entry_price = 100.0
        stop_loss = 98.0  # 2% risk
        position_size = rm.calculate_position_size(entry_price, stop_loss, "BTC/USDT")
        
        # Expected: (MAX_INVESTMENT * MAX_RISK_PER_TRADE / 100) / (entry - sl)
        expected_size = (MAX_INVESTMENT * MAX_RISK_PER_TRADE / 100) / (entry_price - stop_loss)
        assert abs(position_size - expected_size) < 0.001
    
    def test_can_open_position(self):
        """Test position opening constraints."""
        rm = RiskManager()
        
        # Should be able to open first position
        assert rm.can_open_position("BTC/USDT") == True
        
        # Open max positions
        for i in range(MAX_OPEN_TRADES):
            rm.open_position(f"PAIR{i}", "buy", 100.0, 98.0, 102.0, 1.0)
        
        # Should not allow more positions
        assert rm.can_open_position("ETH/USDT") == False

class TestStrategy:
    """Test trading strategy."""
    
    def create_test_data(self, length=100):
        """Create test OHLCV data."""
        dates = pd.date_range('2023-01-01', periods=length, freq='1min')
        
        # Create trending data
        base_price = 100.0
        prices = []
        for i in range(length):
            # Add some trend and noise
            trend = i * 0.05
            noise = np.random.normal(0, 0.5)
            price = base_price + trend + noise
            prices.append(price)
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'close': prices,
            'volume': [1000 + np.random.normal(0, 100) for _ in range(length)]
        })
        
        return df
    
    def test_strategy_indicators(self):
        """Test indicator calculations."""
        strategy = ScalpingEmaRsiStrategy()
        df = self.create_test_data()
        
        df_with_indicators = strategy.calculate_indicators(df)
        
        # Check that indicators are calculated
        assert 'ema_20' in df_with_indicators.columns
        assert 'ema_50' in df_with_indicators.columns
        assert 'ema_100' in df_with_indicators.columns
        assert 'rsi' in df_with_indicators.columns
        
        # Check that values are reasonable
        assert not df_with_indicators['ema_20'].isna().all()
        assert not df_with_indicators['rsi'].isna().all()
        assert df_with_indicators['rsi'].max() <= 100
        assert df_with_indicators['rsi'].min() >= 0
    
    def test_signal_generation(self):
        """Test signal generation."""
        strategy = ScalpingEmaRsiStrategy()
        df = self.create_test_data()
        
        signal = strategy.generate_signal(df)
        
        # Should return a valid signal structure
        assert 'signal' in signal
        assert signal['signal'] in ['buy', 'sell', 'hold']
        assert 'reason' in signal

class TestAnalyzer:
    """Test market analyzer."""
    
    def create_test_data(self):
        """Create test data for analyzer."""
        dates = pd.date_range('2023-01-01', periods=100, freq='1min')
        prices = [100 + i * 0.1 + np.random.normal(0, 0.5) for i in range(100)]
        
        return pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'close': prices,
            'volume': [1000 + np.random.normal(0, 100) for _ in range(100)]
        })
    
    def test_indicator_computation(self):
        """Test indicator computation."""
        analyzer = MarketAnalyzer()
        df = self.create_test_data()
        
        indicators = analyzer.compute_indicators(df)
        
        assert 'ema20' in indicators
        assert 'ema50' in indicators
        assert 'atr' in indicators
        assert 'current_price' in indicators
        assert 'volume_ratio' in indicators
    
    def test_ai_prediction(self):
        """Test AI prediction."""
        analyzer = MarketAnalyzer()
        df = self.create_test_data()
        
        indicators = analyzer.compute_indicators(df)
        prediction = analyzer.ai_prediction(df, indicators)
        
        assert 'prediction' in prediction
        assert 'confidence' in prediction
        assert 'reason' in prediction
        assert prediction['prediction'] in ['bullish', 'bearish', 'neutral']
        assert 0.0 <= prediction['confidence'] <= 1.0

if __name__ == "__main__":
    # Run basic tests
    test_rm = TestRiskManager()
    test_rm.test_position_sizing()
    test_rm.test_can_open_position()
    
    test_strategy = TestStrategy()
    test_strategy.test_strategy_indicators()
    test_strategy.test_signal_generation()
    
    test_analyzer = TestAnalyzer()
    test_analyzer.test_indicator_computation()
    test_analyzer.test_ai_prediction()
    
    print("All tests passed!")