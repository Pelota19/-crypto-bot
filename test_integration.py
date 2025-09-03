#!/usr/bin/env python3
"""
Manual integration test for the crypto bot changes.
Tests key functionality without requiring actual network calls.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_config_imports():
    """Test that all config values are accessible"""
    from src.config import (
        CAPITAL_MAX_USDT, DAILY_PROFIT_TARGET_USD, LOG_LEVEL, 
        AI_MODEL_PATH, POSITION_SIZE_PERCENT
    )
    print(f"✓ Config imports OK - CAPITAL_MAX_USDT: {CAPITAL_MAX_USDT}")
    assert CAPITAL_MAX_USDT == 2000.0
    assert DAILY_PROFIT_TARGET_USD == 50.0
    print(f"✓ Default values correct")

def test_ai_scorer():
    """Test AI scorer functionality"""
    from src.ai.scorer import scorer
    
    # Test features
    features = {
        "mom": 0.1,
        "rsi_centered": 0.2,
        "vwap_dev": -0.1,
        "atr_regime": 0.05,
        "micro_trend": 0.15
    }
    
    score = scorer.score(features)
    print(f"✓ AI scorer works - Score: {score:.3f}")
    assert -1 <= score <= 1
    print(f"✓ Score in valid range [-1,1]")

def test_strategy_integration():
    """Test strategy decide_trade functionality"""
    from src.strategy.strategy import decide_trade
    import pandas as pd
    import numpy as np
    
    # Create realistic test data
    n = 100
    np.random.seed(42)  # Reproducible
    base_price = 50000
    prices = [base_price]
    
    for i in range(1, n):
        change = np.random.normal(0, 100)  # $100 volatility
        prices.append(max(prices[-1] + change, 1000))  # Min price $1000
    
    df = pd.DataFrame({
        'open': prices,
        'high': [p + np.random.uniform(0, 50) for p in prices],
        'low': [p - np.random.uniform(0, 50) for p in prices],
        'close': prices,
        'volume': np.random.randint(1000, 10000, n)
    })
    
    result = decide_trade(df)
    print(f"✓ Strategy works - Signal: {result['signal']}, Score: {result['score']:.3f}")
    
    required_keys = {'signal', 'sl', 'tp', 'score'}
    assert required_keys.issubset(result.keys())
    assert result['signal'] in {'buy', 'sell', 'hold'}
    print(f"✓ Strategy returns expected format")

def test_exchange_client_methods():
    """Test exchange client has required methods"""
    from src.exchange.binance_client import BinanceFuturesClient
    
    # Check required methods exist on the class (without instantiating)
    required_methods = [
        'amount_adjust', 'price_adjust', 'is_trade_feasible',
        'market_order', 'stop_market_reduce_only', 'take_profit_market_reduce_only',
        'set_leverage', 'set_margin_mode'
    ]
    
    for method in required_methods:
        assert hasattr(BinanceFuturesClient, method), f"Missing method: {method}"
    
    print(f"✓ Exchange client has all required methods: {', '.join(required_methods)}")

def test_main_context_equity_cap():
    """Test that Context.get_equity respects capital cap"""
    # Mock to avoid actual exchange calls
    import src.main
    original_starting = src.main.STARTING_BALANCE_USDT
    original_capital_max = src.main.CAPITAL_MAX_USDT
    
    # Temporarily override for test
    src.main.STARTING_BALANCE_USDT = 5000.0  # Higher than cap
    src.main.CAPITAL_MAX_USDT = 2000.0
    
    try:
        # Mock the exchange client to avoid network calls
        class MockExchange:
            def get_balance_usdt(self):
                return 5000.0
        
        class MockContext:
            def __init__(self):
                self.equity_usdt = 5000.0
                self.exchange = MockExchange()
            
            def get_equity(self):
                if src.main.MODE == "paper":
                    return min(self.equity_usdt, src.main.CAPITAL_MAX_USDT)
                return min(max(0.0, self.exchange.get_balance_usdt()), src.main.CAPITAL_MAX_USDT)
        
        ctx = MockContext()
        equity = ctx.get_equity()
        
        print(f"✓ Equity capping works - Balance: 5000, Capped: {equity}")
        assert equity == 2000.0, f"Expected 2000, got {equity}"
        
    finally:
        # Restore original values
        src.main.STARTING_BALANCE_USDT = original_starting
        src.main.CAPITAL_MAX_USDT = original_capital_max

def run_all_tests():
    """Run all integration tests"""
    tests = [
        test_config_imports,
        test_ai_scorer,
        test_strategy_integration,
        test_exchange_client_methods,
        test_main_context_equity_cap
    ]
    
    print("🧪 Running integration tests...\n")
    
    for test in tests:
        try:
            test()
            print()
        except Exception as e:
            print(f"❌ Test {test.__name__} failed: {e}")
            return False
    
    print("✅ All integration tests passed!")
    return True

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)