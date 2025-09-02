#!/usr/bin/env python3
"""
Basic tests to validate core functionality of the crypto bot.
"""
import pandas as pd
import os
import sys
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.strategy.strategy import compute_rsi, decide_signal
from src.persistence.sqlite_store import _ensure_db, save_order, save_balance
from src.config import MODE, STARTING_BALANCE_USDT


def test_rsi_computation():
    """Test RSI computation with known values."""
    # Create test data
    close_prices = pd.Series(
        [
            44,
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.85,
            47.37,
            47.20,
            46.80,
            46.57,
            46.85,
            47.37,
            47.20,
        ]
    )

    rsi = compute_rsi(close_prices, period=14)

    # RSI should be between 0 and 100
    assert all(0 <= val <= 100 for val in rsi.dropna())
    assert len(rsi) == len(close_prices)


def test_strategy_signal():
    """Test strategy signal generation."""
    # Create test OHLCV data
    data = {
        "timestamp": pd.date_range("2023-01-01", periods=50, freq="h"),
        "open": [100 + i * 0.1 for i in range(50)],
        "high": [100 + i * 0.1 + 0.5 for i in range(50)],
        "low": [100 + i * 0.1 - 0.5 for i in range(50)],
        "close": [100 + i * 0.1 + 0.2 for i in range(50)],
        "volume": [1000] * 50,
    }
    ohlcv = pd.DataFrame(data)

    signal = decide_signal(ohlcv)
    assert signal in ["buy", "sell", "hold"]


def test_strategy_signal_insufficient_data():
    """Test strategy with insufficient data."""
    # Create minimal data (less than required)
    data = {
        "timestamp": pd.date_range("2023-01-01", periods=5, freq="h"),
        "open": [100] * 5,
        "high": [101] * 5,
        "low": [99] * 5,
        "close": [100] * 5,
        "volume": [1000] * 5,
    }
    ohlcv = pd.DataFrame(data)

    signal = decide_signal(ohlcv)
    assert signal == "hold"


def test_database_initialization():
    """Test database creation and table setup."""
    # Remove test db if exists
    test_db_path = "data/test_crypto_bot.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Temporarily change DB_PATH for testing
    with patch("src.persistence.sqlite_store.DB_PATH", test_db_path):
        _ensure_db()

        # Check that data directory was created
        assert os.path.exists("data")

        # Check that db file was created
        assert os.path.exists(test_db_path)

        # Test saving an order
        save_order("BTCUSDT", "buy", 50000.0, 0.001, 50.0, "filled_paper")

        # Test saving balance
        save_balance(1000.0)

    # Cleanup
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


def test_config_values():
    """Test that configuration values are loaded properly."""
    assert MODE in ["paper", "live"]
    assert isinstance(STARTING_BALANCE_USDT, (int, float))
    assert STARTING_BALANCE_USDT > 0


if __name__ == "__main__":
    # Run tests directly
    test_rsi_computation()
    test_strategy_signal()
    test_strategy_signal_insufficient_data()
    test_database_initialization()
    test_config_values()
    print("All tests passed!")
