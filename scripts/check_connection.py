#!/usr/bin/env python3
"""
Simple connection check script for manual validation.
Tests if the exchange client can fetch basic OHLCV data.
"""

import sys
import os
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from exchange.binance_client import BinanceFuturesClient

def check_connection():
    """Test connection to Binance testnet."""
    try:
        # Load environment variables
        load_dotenv()
        
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() in ("true", "1", "yes")
        
        print(f"Testing connection to Binance {'testnet' if testnet else 'mainnet'}...")
        
        # Create client
        client = BinanceFuturesClient(api_key, api_secret, testnet=testnet)
        
        # Test basic OHLCV fetch
        print("Fetching BTC/USDT:USDT 1m data...")
        df = client.fetch_ohlcv_df("BTC/USDT:USDT", timeframe="1m", limit=1)
        
        if df.empty:
            print("❌ FAILED: Received empty data")
            return False
        
        print(f"✅ SUCCESS: Received {len(df)} candle(s)")
        print(f"   Latest close: {df['close'].iloc[-1]:.2f}")
        print(f"   Timestamp: {df['timestamp'].iloc[-1]}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

if __name__ == "__main__":
    success = check_connection()
    sys.exit(0 if success else 1)