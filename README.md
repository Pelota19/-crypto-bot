# Crypto Scalping Bot

A modular crypto scalping bot that runs on **Binance Futures Testnet** by default, with comprehensive risk management, Telegram notifications, market analysis, and daily profit targets.

## Features

- **Exchange**: Binance Futures Testnet via CCXT with sandbox mode
- **Strategy**: EMA crossover + RSI confirmation for BUY signals
- **Risk Management**: Position sizing, max trades, daily drawdown protection
- **Daily Targets**: Automatic pause when profit target reached until next day
- **Telegram Notifications**: Real-time updates on orders, PnL, errors, and status
- **Market Analysis**: Basic indicators (EMA20/EMA50, ATR) with lightweight AI prediction
- **Structured Logging**: Rotating file logs with console output

## Project Structure

```
.
├── config/                 # Configuration modules
│   ├── __init__.py
│   └── settings.py        # Environment-based configuration
├── core/                  # Core bot logic
│   ├── __init__.py
│   ├── bot.py            # Main bot orchestration
│   └── risk_manager.py   # Risk management and position sizing
├── exchanges/             # Exchange implementations
│   ├── __init__.py
│   ├── factory.py        # Exchange factory
│   └── binance.py        # Binance Futures implementation
├── strategies/            # Trading strategies
│   ├── __init__.py
│   ├── factory.py        # Strategy factory
│   └── scalping_ema_rsi.py # EMA cross + RSI strategy
├── models/                # Analysis models
│   ├── __init__.py
│   └── analyzer.py       # Market analyzer with indicators
├── telegram/              # Telegram integration
│   ├── __init__.py
│   └── client.py         # Telegram notifications
├── utils/                 # Utilities
│   ├── __init__.py
│   └── logger.py         # Logging configuration
├── data/                  # Data storage (.gitkeep)
├── tests/                 # Test files
├── logs/                  # Runtime logs (created automatically)
├── main.py               # Entry point
├── requirements.txt      # Dependencies
├── .env.example         # Environment template
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Requirements

- Python 3.8+
- Binance Futures Testnet account with API keys
- Telegram Bot Token and Chat ID (optional but recommended)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd crypto_bot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

## Configuration

Edit `.env` file with your settings:

### Exchange Configuration
```env
EXCHANGE=binance
API_KEY=your_binance_testnet_api_key
API_SECRET=your_binance_testnet_secret
USE_TESTNET=True
```

### Trading Configuration
```env
DAILY_PROFIT_TARGET=30.0          # Daily profit target in USD
MAX_INVESTMENT=2000.0             # Maximum capital to use
TRADING_PAIRS=BTC/USDT,ETH/USDT   # Comma-separated trading pairs
STRATEGY=scalping_ema_rsi         # Strategy to use
```

### Risk Management
```env
MAX_RISK_PER_TRADE=1.0           # Max risk per trade (%)
MAX_OPEN_TRADES=5                # Maximum simultaneous positions
MAX_DAILY_DRAWDOWN=5.0           # Daily drawdown limit (%)
RISK_REWARD_RATIO=2.0            # Risk:reward ratio for TP
```

### Telegram Notifications
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Strategy Details

### EMA Cross + RSI Strategy

**BUY Conditions (all must be met):**
- EMA20 crosses above EMA50
- Current price is above EMA100
- RSI crosses up from oversold (< 30)
- Volume is 20% above recent average

**Risk Management:**
- **Stop Loss**: Recent local low OR 1% below entry (whichever is tighter)
- **Take Profit**: Entry + (Risk × Risk:Reward Ratio)
- **Position Size**: Calculated based on risk per trade and stop loss distance

## Operation

### Daily Cycle
1. Bot monitors configured trading pairs every minute
2. Generates signals using EMA + RSI strategy
3. Places orders when risk management allows
4. Monitors stop loss and take profit orders
5. When daily target reached, pauses until midnight
6. At midnight, resets daily metrics and resumes

### Notifications
The bot sends Telegram messages for:
- Bot start/stop
- Order placements
- Stop loss/take profit hits
- Daily target reached
- Daily reset
- Errors and warnings

### Logging
- **Console**: INFO level messages
- **File**: `logs/crypto_bot.log` (DEBUG level, rotating)
- **Errors**: `logs/crypto_bot_error.log` (ERROR level, rotating)

## Testing

To test the bot safely:

1. **Use Testnet**: Ensure `USE_TESTNET=True` in your `.env`
2. **Small Amounts**: Start with low `MAX_INVESTMENT` and `DAILY_PROFIT_TARGET`
3. **Monitor Logs**: Watch the logs for any issues
4. **Telegram Setup**: Configure Telegram to receive real-time updates

## Safety Features

- **Testnet by Default**: Runs on Binance Futures Testnet to prevent real losses
- **Risk Limits**: Multiple layers of risk management
- **Daily Caps**: Automatic shutdown when targets/limits reached
- **Error Handling**: Comprehensive error handling with notifications
- **Position Limits**: Maximum number of simultaneous trades
- **Capital Protection**: Position sizing based on available capital

## Customization

### Adding New Strategies
1. Create new strategy class in `strategies/`
2. Implement `generate_signal()` method
3. Add to strategy factory

### Adding New Exchanges
1. Create exchange class in `exchanges/`
2. Implement required methods
3. Add to exchange factory

### Extending Analysis
1. Modify `models/analyzer.py` for new indicators
2. Update AI prediction logic as needed

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running from the project root directory
2. **API Errors**: Verify your Binance Testnet credentials
3. **No Data**: Check if trading pairs are available on testnet
4. **Telegram Fails**: Verify bot token and chat ID

### Getting Help

Check the logs in `logs/` directory for detailed error messages. The bot logs all operations including API calls, signal generation, and order management.

## Disclaimer

This bot is for educational and testing purposes. Always:
- Test thoroughly on testnet before considering live trading
- Understand the risks involved in cryptocurrency trading
- Never invest more than you can afford to lose
- Monitor the bot's performance regularly

## License

This project is provided as-is for educational purposes.