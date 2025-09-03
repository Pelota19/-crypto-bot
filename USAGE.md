# Crypto Bot - Usage Guide

## Quick Start

### 1. Environment Setup
Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

Key variables to set:
- `BINANCE_API_KEY` and `BINANCE_API_SECRET` 
- `CAPITAL_MAX_USDT` - Maximum capital to use for position sizing
- `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` for notifications
- `MODE` - Set to "paper" for simulation or "live" for real trading

### 2. Running the Bot

#### Testnet Mode (Recommended for testing)
```bash
./scripts/run_testnet.sh
```

#### Manual Run
```bash
python -m src.main
```

### 3. Test Connection
Validate your API credentials work:
```bash
python scripts/check_connection.py
```

## New Features

### Enhanced Strategy Integration
- Now uses `decide_trade()` which returns signal, stop loss, take profit, and confidence score
- ATR-based stop loss and take profit calculations
- Better risk-adjusted position sizing

### Improved Risk Management  
- Capital capping with `CAPITAL_MAX_USDT`
- Daily profit/loss targets with automatic trading pause
- Trade feasibility checking before placing orders

### Better Order Management
- Uses exchange wrapper methods for reliable order placement
- Graceful handling of failed orders
- Actual order amounts used for bracket orders

### Operational Improvements
- Reduced console logging (use Telegram for monitoring)
- Better error handling and rate limiting
- Concurrent command processing
- Enhanced status messages

## Telegram Commands
- `/status` - Show current bot status and PnL
- `/pause` - Pause trading
- `/resume` - Resume trading

## Configuration
See `.env.example` for all available configuration options.