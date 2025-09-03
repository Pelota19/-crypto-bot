#!/bin/bash
# Quick helper to run the crypto bot in testnet mode

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Load environment variables from .env if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Set testnet mode
export BINANCE_TESTNET=true
export MODE=paper

echo "Starting crypto bot in testnet mode..."
python -m src.main