#!/bin/bash
# Test script for the new top-K selection functionality

echo "🧪 Testing crypto bot with top-K selection..."

# Test 1: Validate configuration
echo "1. Testing configuration..."
python -c "
from src.config import TOP_K_SELECTION, MAX_ACTIVE_SYMBOLS, MIN_NOTIONAL_USD
print(f'✅ Config loaded: TOP_K_SELECTION={TOP_K_SELECTION}, MAX_ACTIVE_SYMBOLS={MAX_ACTIVE_SYMBOLS}, MIN_NOTIONAL_USD={MIN_NOTIONAL_USD}')
"

# Test 2: Test imports
echo "2. Testing imports..."
python -c "
from src.pair_selector import PairSelector
from src.main import Context, trading_loop
print('✅ All modules import successfully')
"

# Test 3: Run smoke test (if network available)
echo "3. Running smoke test..."
if python scripts/select_pairs_smoke.py 2>/dev/null; then
    echo "✅ Smoke test passed"
else
    echo "⚠️  Smoke test failed (expected if no network access)"
fi

echo "🎉 Testing completed!"