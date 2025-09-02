import sys
import pandas as pd
import numpy as np

from src.strategy.strategy import decide_signal
from src.exchange.binance_client import BinanceFuturesClient
from src.config import BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET

def test_strategy_on_synthetic():
    # Simple synthetic OHLCV to check function wiring
    n = 60
    ts = pd.date_range("2024-01-01", periods=n, freq="T")
    close = pd.Series(np.linspace(100, 101, n)) + np.random.normal(0, 0.05, n)
    df = pd.DataFrame({
        "timestamp": ts,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "volume": np.random.randint(50, 150, n),
    })
    sig = decide_signal(df)
    assert sig in {"buy", "sell", "hold"}

def test_public_ohlcv():
    ex = BinanceFuturesClient(BINANCE_API_KEY or "", BINANCE_API_SECRET or "", testnet=BINANCE_TESTNET)
    df = ex.fetch_ohlcv_df("BTC/USDT", timeframe="1m", limit=50)
    assert not df.empty

if __name__ == "__main__":
    # Lightweight runner without pytest
    try:
        test_strategy_on_synthetic()
        test_public_ohlcv()
        print("All basic tests passed ✅")
        sys.exit(0)
    except AssertionError as e:
        print("Test failed:", e)
        sys.exit(1)