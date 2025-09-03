# Crypto Scalping Bot

Advanced cryptocurrency scalping bot with AI-enabled strategy, dynamic risk management, and Telegram integration. Designed for **Binance Futures (USDM) testnet** with strict capital controls and daily profit targets.

## 🚀 Features

- **IA-Light Meta-Scorer**: Combines EMA9/21, RSI, VWAP deviation, ATR, and micro-trend analysis
- **Dynamic SL/TP**: ATR-based stop-loss and take-profit calculations
- **Capital Management**: Capped at 2000 USDT with 1% position sizing
- **Daily Targets**: 50 USD profit target with automatic entry blocking
- **Telegram Integration**: Primary interface for monitoring and control
- **Exchange Hardening**: Proper amount/price rounding, minQty validation
- **Risk Controls**: Leverage/margin setup, feasibility checks, reduce-only orders

## 📋 Requirements

- Python 3.10+
- Binance Futures (USDM) testnet account and API keys
- Telegram bot token and chat ID (recommended)

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Pelota19/crypto_bot.git
   cd crypto_bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Set up Binance testnet**:
   - Go to https://testnet.binancefuture.com/
   - Create account and generate API keys
   - Add keys to `.env` file

5. **Set up Telegram bot** (optional but recommended):
   - Create bot via @BotFather on Telegram
   - Get your chat ID via @userinfobot
   - Add token and chat ID to `.env` file

## ⚙️ Configuration

Key environment variables in `.env`:

```bash
# Trading Mode
MODE=live                      # "paper" or "live"
BINANCE_TESTNET=true          # Always use testnet for safety

# API Keys
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here

# Risk Management
CAPITAL_MAX_USDT=2000.0       # Maximum capital (hard cap)
POSITION_SIZE_PERCENT=1.0     # 1% position size
DAILY_PROFIT_TARGET_USD=50.0  # Daily profit target
MAX_DAILY_LOSS_USD=100.0      # Daily loss limit

# Telegram
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Logging
LOG_LEVEL=WARNING             # Quiet console logging
```

## 🚀 Running the Bot

**Start the bot**:
```bash
python -m src.main
```

The bot will:
1. Initialize and connect to Binance testnet
2. Set leverage and margin mode for symbols
3. Send startup message to Telegram
4. Begin trading loop with symbol analysis

## 📱 Telegram Commands

Control the bot via Telegram:

- `/status` - Show current equity, PnL, and bot status
- `/pause` - Pause trading (stops new entries)
- `/resume` - Resume trading

## 🧠 Strategy Overview

The bot uses a hybrid scalping strategy:

1. **Technical Indicators**:
   - EMA9/21 crossover for trend direction
   - RSI for momentum confirmation
   - VWAP deviation for mean reversion
   - ATR for volatility assessment

2. **AI Meta-Scorer**:
   - Combines normalized features into single score [-1,1]
   - Weights: momentum (1.2), RSI-centered (0.8), VWAP-dev (0.7), etc.
   - Persists learning to `data/ai_model.json`

3. **Risk Management**:
   - Dynamic SL: 0.35x ATR distance
   - Dynamic TP: 0.70x ATR distance
   - Position sizing: 1% of capped equity
   - Order validation: minQty and feasibility checks

## 🔧 Architecture

```
src/
├── main.py              # Main orchestration loop
├── config.py            # Environment configuration
├── ai/
│   └── scorer.py        # AI meta-scorer implementation
├── strategy/
│   └── strategy.py      # Trading strategy logic
├── exchange/
│   └── binance_client.py # Exchange API wrapper
├── orders/
│   └── manager.py       # Order placement and management
├── telegram/
│   └── console.py       # Telegram interface
└── persistence/
    └── sqlite_store.py  # Data persistence
```

## ⚠️ Important Warnings

- **TESTNET ONLY**: This bot is configured for Binance testnet. Never use production API keys.
- **MinQty Handling**: The bot automatically skips orders below exchange minimum quantities.
- **Capital Limits**: All position sizing is capped at `CAPITAL_MAX_USDT` regardless of actual balance.
- **Daily Limits**: Trading stops when daily profit target (+50 USD) or max loss (-100 USD) is reached.

## 🔍 Monitoring

The bot provides comprehensive logging:

- **Console**: WARNING level (minimal noise)
- **Telegram**: All trades, PnL updates, status messages
- **Database**: Order history in SQLite
- **State**: Daily PnL and flags in JSON

## 🧪 Testing

Run basic validation:
```bash
python test_basic.py
```

**Test checklist**:
- [ ] Bot starts with `MODE=live` and `BINANCE_TESTNET=true`
- [ ] Sets leverage/margin for symbols
- [ ] Sends Telegram startup message
- [ ] Skips orders below minQty (no InvalidOrder exceptions)
- [ ] Stops new entries when +50 USD daily PnL reached

## 🤝 Development

To extend the bot:

1. **Strategy**: Modify `src/strategy/strategy.py` for new signals
2. **AI Scorer**: Update weights in `src/ai/scorer.py`
3. **Risk Management**: Adjust parameters in `src/config.py`
4. **Exchange**: Enhance `src/exchange/binance_client.py` for new order types

## 📊 Performance

The bot aims for:
- **Daily Target**: +50 USD profit
- **Risk Control**: Max -100 USD daily loss
- **Position Size**: 1% of equity per trade
- **Win Rate**: Optimized via AI meta-scorer
- **Execution**: Sub-second order placement

## 🐛 Troubleshooting

**Common issues**:

1. **Network errors**: Check internet and testnet connectivity
2. **API errors**: Verify API keys and permissions
3. **MinQty errors**: Bot should auto-skip, check logs
4. **Telegram silence**: Verify bot token and chat ID
5. **No trades**: Check daily limits and symbol volume filters

## 📄 License

MIT License - See LICENSE file for details.

---

**Disclaimer**: This software is for educational purposes. Cryptocurrency trading involves significant risk. Use at your own discretion and never risk more than you can afford to lose.