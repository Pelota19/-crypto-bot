# Crypto Scalping Bot with AI Meta-Scorer

Modern scalping bot for cryptocurrency futures trading with lightweight AI scoring, risk management, and Telegram integration. Designed for **Binance Futures (USDM) testnet** with comprehensive position sizing, stop-loss/take-profit handling, and daily profit targets.

## 🚀 Features

- **AI-Assisted Scalping**: SimpleMetaScorer combines EMA, RSI, VWAP, ATR, and micro-trend features into a [-1,1] score
- **Capital Management**: Enforced capital cap of 2000 USDT for position sizing regardless of actual balance
- **Daily Profit Targets**: Stop opening new trades after +50 USD daily profit or maximum daily loss
- **Comprehensive Risk Management**: Dynamic SL/TP based on ATR with min/max bounds
- **Telegram Integration**: Real-time notifications and remote control (/status, /pause, /resume)
- **Exchange Integration**: Full Binance Futures support with testnet capability
- **Position Management**: Automatic bracket orders (SL/TP) as conditional reduceOnly orders
- **Logging Control**: Silent shell logs (WARNING level) with Telegram as primary reporting channel

## 📁 Structure

```
src/
├── config.py           # Centralized configuration with environment variables
├── ai/
│   └── scorer.py       # SimpleMetaScorer with persistent weights
├── strategy/
│   └── strategy.py     # Technical analysis and trade decision logic
├── exchange/
│   └── binance_client.py  # Binance Futures API wrapper with testnet support
├── orders/
│   └── manager.py      # Order execution and bracket placement
├── risk/
│   └── manager.py      # Position sizing and risk calculations
├── state.py            # Daily PnL tracking and bot state management
├── persistence/
│   └── sqlite_store.py # Trade and balance persistence
├── telegram/
│   └── console.py      # Telegram messaging and command handling
└── main.py             # Main orchestrator with asyncio event loop
```

## 📋 Requirements

- Python 3.8+
- Binance Futures testnet account with API credentials
- Telegram bot token (optional but recommended)

## 🛠 Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Pelota19/crypto_bot.git
   cd crypto_bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables** (copy `.env.example` to `.env`):
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Set up Binance testnet**:
   - Go to [Binance Testnet](https://testnet.binancefuture.com)
   - Create API keys and add to `.env`

5. **Set up Telegram (optional)**:
   - Create a bot via @BotFather
   - Get your chat ID
   - Add credentials to `.env`

## ⚙️ Configuration (.env example)

```bash
# Trading Mode
MODE=paper                           # "paper" or "live" 
BINANCE_TESTNET=true                 # Use testnet (recommended)

# API Credentials
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# Capital & Risk Management  
CAPITAL_MAX_USDT=2000.0             # Capital cap for position sizing
STARTING_BALANCE_USDT=2000.0        # Initial balance for paper trading
POSITION_SIZE_PERCENT=1.0           # 1% position size per trade
DAILY_PROFIT_TARGET_USD=50.0        # Stop after +50 USD daily profit
MAX_DAILY_LOSS_USD=100.0            # Stop after -100 USD daily loss

# Trading Parameters
LEVERAGE=5                          # Leverage for live trading
MARGIN_MODE=ISOLATED                # ISOLATED or CROSSED
TIMEFRAME=1m                        # Trading timeframe
MAX_SYMBOLS=10                      # Maximum symbols to trade
MIN_24H_VOLUME_USDT=5000000         # Minimum 24h volume filter

# Telegram Integration
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Logging & Data
LOG_LEVEL=WARNING                   # Shell log level (WARNING = quiet)
DATA_DIR=data                       # Data directory for persistence
```

## 🚀 Usage

**Start the bot**:
```bash
python src/main.py
```

**Telegram Commands**:
- `/status` - Show bot status, PnL, and settings
- `/pause` - Pause trading (stop opening new positions)
- `/resume` - Resume trading

## 🧪 Testing

**Validate configuration**:
```bash
python validate_config.py
```

**Run basic tests**:
```bash
python test_basic.py
```

**Test with testnet**:
1. Set `BINANCE_TESTNET=true` in `.env`
2. Use testnet API credentials
3. Start with `MODE=paper` for simulation
4. Progress to `MODE=live` on testnet for real orders

## 🎯 AI Meta-Scorer

The SimpleMetaScorer combines multiple technical indicators into a single score:

- **Momentum**: EMA9-EMA21 normalized by price
- **RSI Centered**: (RSI-50)/50 for mean reversion
- **VWAP Deviation**: Distance from VWAP in ATR units
- **ATR Regime**: Volatility normalization
- **Micro-trend**: Short-term price slope

Weights are persisted in JSON and can be adjusted over time for optimization.

## ⚠️ Risk Warnings

- **Testnet Only**: This bot is configured for Binance testnet by default
- **Capital Loss**: Trading involves significant risk of capital loss
- **Code Review**: Thoroughly review and test before live deployment  
- **API Security**: Keep API keys secure and use IP restrictions
- **Position Sizing**: Respect the capital cap and never risk more than you can afford to lose
- **Market Conditions**: Performance varies significantly with market conditions

## 📊 Strategy Details

**Entry Conditions**:
- AI scorer above +0.25 (buy) or below -0.25 (sell)
- EMA agreement: EMA9 > EMA21 + RSI > 50 for buy (opposite for sell)
- Trade feasibility check (minimum quantity requirements)

**Exit Conditions**:
- Dynamic SL/TP based on ATR (0.35x ATR for SL, 0.70x ATR for TP)
- Minimum 0.1% and maximum 1.2% for SL/TP distances
- Bracket orders placed as conditional reduceOnly orders

**Risk Management**:
- Position sizing capped at CAPITAL_MAX_USDT regardless of actual balance
- Daily profit/loss limits with automatic trading halt
- Per-trade position size as percentage of effective capital

## 🔧 Development

**Code quality tools**:
```bash
# Linting
python -m ruff check .

# Formatting  
python -m black .

# Type checking
python -m mypy src --ignore-missing-imports
```

## 📝 License

This project is for educational and testing purposes. Use at your own risk.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly on testnet
5. Submit a pull request

---

**⚠️ Important**: Always test on Binance testnet before considering any live deployment. This bot is provided as-is for educational purposes.