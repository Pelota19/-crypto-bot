# AI-Assisted Crypto Scalping Bot

A modern, AI-assisted cryptocurrency scalping bot designed for Binance Futures (USDM). Features lightweight AI meta-scoring, capital management, risk controls, and Telegram-based monitoring.

## 🚀 Key Features

- **AI-Assisted Trading**: Lightweight meta-scorer combines multiple technical indicators for enhanced decision making
- **Modern Scalping Strategy**: EMA9/EMA21 crossovers, RSI(14), ATR(14), VWAP(30), and micro-trend analysis
- **Capital Management**: Enforced 2000 USDT capital cap for position sizing, regardless of actual balance
- **Daily Profit Targets**: Stops opening new trades after reaching +50 USD daily profit target
- **Risk Management**: Dynamic SL/TP based on ATR, respects market minQty and stepSize constraints
- **Testnet-First**: Designed for Binance Futures testnet with explicit mainnet warnings
- **Telegram Integration**: Complete bot control and notifications via Telegram
- **Quiet Operation**: LOG_LEVEL WARNING by default - Telegram is the primary interface

## 📁 Project Structure

```
.
├── src/
│   ├── config.py              # Centralized configuration
│   ├── main.py                # Main orchestrator with async loop
│   ├── ai/
│   │   └── scorer.py          # Lightweight AI meta-scorer
│   ├── strategy/
│   │   └── strategy.py        # Modern scalping strategy
│   ├── exchange/
│   │   └── binance_client.py  # Binance Futures API wrapper
│   ├── orders/
│   │   └── manager.py         # Order management with brackets
│   ├── risk/
│   │   └── manager.py         # Position sizing and risk controls
│   ├── state.py               # Daily state management
│   ├── persistence/
│   │   └── sqlite_store.py    # Trade and balance persistence
│   └── telegram/
│       └── console.py         # Telegram bot interface
├── .env.example               # Environment variables template
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## 🛠️ Installation

1. **Clone and setup environment:**
```bash
git clone https://github.com/Pelota19/crypto_bot.git
cd crypto_bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. **Install dependencies:**
```bash
python src/main.py
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration (see below)
```

4. **Run the bot:**
```bash
python -m src.main
```

## ⚙️ Configuration (.env file)

```bash
# =========================
#   CRYPTO SCALPING BOT
#   Binance Futures (USDM) - TESTNET
# =========================

# --- Mode ---
MODE=paper                    # "paper" or "live"

# --- Binance Futures Testnet ---
BINANCE_TESTNET=true          # ALWAYS true for safety
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_secret

# --- Capital and Sizing ---
CAPITAL_MAX_USDT=2000.0       # Maximum capital for position sizing
STARTING_BALANCE_USDT=2000.0  # Starting balance for paper mode

# --- Trading Parameters ---
POSITION_SIZE_PERCENT=1.0     # 1% position size
DAILY_PROFIT_TARGET_USD=50.0  # Stop trading after +50 USD profit
MAX_DAILY_LOSS_USD=100.0      # Stop trading after -100 USD loss

# --- Leverage/Margin (Live Mode Only) ---
LEVERAGE=5                    # 1-125x leverage
MARGIN_MODE=ISOLATED          # ISOLATED or CROSSED

# --- Strategy Settings ---
TIMEFRAME=1m                  # Trading timeframe
MAX_SYMBOLS=10                # Maximum symbols to trade
MIN_24H_VOLUME_USDT=5000000   # Minimum 24h volume filter

# --- Telegram Bot ---
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# --- Logging ---
LOG_LEVEL=WARNING             # Keep console quiet
```

## 🤖 AI Meta-Scorer

The bot uses a lightweight AI system that combines multiple technical indicators:

- **Momentum**: EMA9-EMA21 normalized difference
- **RSI Centered**: (RSI-50)/50 for mean reversion signals  
- **VWAP Deviation**: Price deviation from VWAP in ATR units
- **ATR Regime**: Volatility regime detection
- **Micro-trend**: Short-term price slope analysis

The scorer outputs values from -1 to +1, with thresholds at ±0.25 for trade signals.

## 📊 Trading Strategy

### Entry Conditions
- **Buy**: AI score ≥ +0.25 AND EMA9 > EMA21 AND RSI > 50
- **Sell**: AI score ≤ -0.25 AND EMA9 < EMA21 AND RSI < 50

### Risk Management
- **Stop Loss**: 0.35x ATR with 0.1%-1.2% price limits
- **Take Profit**: 0.70x ATR with 0.2%-2.4% price limits
- **Position Sizing**: Capped at 2000 USDT regardless of actual balance
- **Market Constraints**: Respects minQty, stepSize, and tickSize

### Daily Controls
- Stops new trades after +50 USD daily profit
- Stops new trades after -100 USD daily loss
- Resets at 00:00 UTC daily

## 📱 Telegram Commands

Once configured, control the bot via Telegram:

- `/status` - View current status, balance, and daily PnL
- `/pause` - Pause new trade entries
- `/resume` - Resume trading (if within daily limits)

## 🔧 Development & Testing

**Validate configuration:**
```bash
python validate_config.py
```

**Run basic tests:**
```bash
python test_basic.py
```

**Code quality checks:**
```bash
# Linting
python -m ruff check .

# Formatting  
python -m black .
```

## ⚠️ Safety & Warnings

### Testnet First
- **ALWAYS** test on Binance Futures testnet first
- Set `BINANCE_TESTNET=true` in your .env file
- Get testnet API keys from [Binance Testnet](https://testnet.binancefuture.com/)

### Mainnet Usage
- **NEVER** use mainnet without thorough testing
- Requires explicit `BINANCE_TESTNET=false` AND `MODE=live`
- Start with small capital amounts
- Monitor closely for the first few hours

### Risk Disclaimers
- Cryptocurrency trading involves substantial risk
- Past performance does not guarantee future results
- Only trade with capital you can afford to lose
- This software is provided "as-is" without warranties

## 🏗️ Architecture Notes

### Capital Management
- Position sizing uses `min(actual_balance, CAPITAL_MAX_USDT)`
- Prevents over-leveraging even with larger account balances
- Daily PnL tracking via balance snapshots

### Order Execution
- Market orders with immediate SL/TP bracket placement
- Respects exchange minQty/stepSize constraints
- Graceful handling of rejected orders below minimum size

### State Management
- Persistent daily state with automatic UTC reset
- SQLite storage for trades and balance history
- Robust error handling and recovery

## 📈 Performance Monitoring

The bot tracks:
- Individual trade PnL with fees
- Daily cumulative PnL
- Win/loss ratios (via SQLite logs)
- Order execution statistics

Access trade history via SQLite:
```bash
sqlite3 data/crypto_bot.db
.tables
SELECT * FROM orders ORDER BY ts DESC LIMIT 10;
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly on testnet
4. Submit a pull request

## 📄 License

This project is open source. Use at your own risk.

---

**Remember**: Always test on testnet first. Never risk more than you can afford to lose.