#!/usr/bin/env python3
"""
Smoke test script for pair selection functionality.
Tests the top-K symbol selection without running the full trading loop.
"""
import sys
import asyncio
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.config import (
    BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET,
    MIN_24H_VOLUME_USDT, MAX_SYMBOLS, POSITION_SIZE_PERCENT,
    MAX_ACTIVE_SYMBOLS, LOG_LEVEL
)
from src.exchange.binance_client import BinanceFuturesClient
from src.pair_selector import PairSelector
from src.telegram.console import send_message

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("smoke_test")


def mock_get_equity() -> float:
    """Mock equity function for testing."""
    return 2000.0  # Mock $2000 balance


async def main():
    """Run the smoke test."""
    print("🔍 Starting pair selection smoke test...")
    
    try:
        # Initialize exchange client
        print(f"📡 Connecting to Binance (testnet={BINANCE_TESTNET})...")
        exchange = BinanceFuturesClient(
            BINANCE_API_KEY or "", 
            BINANCE_API_SECRET or "", 
            testnet=BINANCE_TESTNET
        )
        
        # Get universe of symbols
        print(f"📊 Getting symbol universe (min volume: ${MIN_24H_VOLUME_USDT:,.0f})...")
        symbols = exchange.get_usdt_perp_symbols(MIN_24H_VOLUME_USDT, MAX_SYMBOLS)
        print(f"Found {len(symbols)} symbols: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}")
        
        # Initialize pair selector
        pair_selector = PairSelector(exchange, mock_get_equity)
        
        # Test single symbol analysis
        if symbols:
            test_symbol = symbols[0]
            print(f"\n🔬 Testing single symbol analysis: {test_symbol}")
            candidate = pair_selector.analyze_symbol(test_symbol, POSITION_SIZE_PERCENT)
            print(f"  Signal: {candidate.signal}")
            print(f"  Score: {candidate.score:.4f}")
            print(f"  Price: ${candidate.last_price:.2f}")
            print(f"  Feasible: {candidate.is_feasible} ({candidate.feasible_reason})")
            print(f"  Volume 24h: ${candidate.volume_24h_usd:,.0f}")
        
        # Test top-K selection
        print(f"\n🎯 Testing top-{MAX_ACTIVE_SYMBOLS} selection...")
        selected = pair_selector.select_top_symbols(
            symbols, POSITION_SIZE_PERCENT, MAX_ACTIVE_SYMBOLS
        )
        
        # Format and display results
        summary = pair_selector.format_selection_summary(selected, len(symbols))
        print(f"\n📋 Selection Summary:")
        print(summary)
        
        # Test detailed output
        if selected:
            print(f"\n📈 Detailed Results:")
            for i, candidate in enumerate(selected, 1):
                print(f"  {i}. {candidate.symbol}:")
                print(f"     Signal: {candidate.signal} | Score: {candidate.score:.4f}")
                print(f"     Price: ${candidate.last_price:.2f} | Notional: ${candidate.notional_usd:.2f}")
                print(f"     SL: ${candidate.sl:.2f} | TP: ${candidate.tp:.2f}")
                print(f"     Volume: ${candidate.volume_24h_usd:,.0f}")
                print(f"     Feasible: {candidate.feasible_reason}")
        
        # Try to send to Telegram if configured
        try:
            if summary and selected:
                await send_message(f"🧪 SMOKE TEST\n{summary}")
                print(f"\n✅ Telegram message sent successfully")
        except Exception as e:
            print(f"\n⚠️  Telegram failed (expected if not configured): {e}")
        
        print(f"\n✅ Smoke test completed successfully!")
        print(f"   - Analyzed {len(symbols)} symbols")
        print(f"   - Selected {len(selected)} candidates")
        if selected:
            best = selected[0]
            print(f"   - Best: {best.symbol} ({best.signal}, score={best.score:.3f})")
    
    except Exception as e:
        print(f"\n❌ Smoke test failed: {e}")
        log.exception("Smoke test error")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())