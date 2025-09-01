import os
from dotenv import load_dotenv
import yaml

# Load environment variables from .env file
load_dotenv()

# --- Environment Variables ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Configuration from YAML file ---
def load_config():
    """Loads the configuration from config.yml."""
    try:
        with open("config.yml", "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yml not found. Please create it from the example.")
        raise
    except yaml.YAMLError as e:
        print(f"Error parsing config.yml: {e}")
        raise

config = load_config()

# --- Extracting config values for easier access ---
# Bot settings
PAIRS = [p.strip() for p in config['bot']['pairs'].split(',')]
TIMEFRAME = config['bot']['timeframe']

# Exchange settings
EXCHANGE_NAME = config['exchange']['name']
EXCHANGE_TESTNET = config['exchange']['testnet']

# Risk Management settings
INVESTMENT_MAX_USD = config['risk_management']['investment_max_usd']
DAILY_PROFIT_GOAL_USD = config['risk_management']['daily_profit_goal_usd']
STOP_LOSS_PCT = config['risk_management']['stop_loss_pct']
TAKE_PROFIT_PCT = config['risk_management']['take_profit_pct']
USE_ATR_FOR_SL_TP = config['risk_management']['use_atr_for_sl_tp']
ATR_SL_MULTIPLIER = config['risk_management']['atr_sl_multiplier']
ATR_TP_MULTIPLIER = config['risk_management']['atr_tp_multiplier']

# Strategy settings
EMA_SHORT_PERIOD = config['strategy']['ema_short_period']
EMA_LONG_PERIOD = config['strategy']['ema_long_period']
RSI_PERIOD = config['strategy']['rsi_period']
RSI_OVERSOLD_THRESHOLD = config['strategy']['rsi_oversold_threshold']
RSI_OVERBOUGHT_THRESHOLD = config['strategy']['rsi_overbought_threshold']

# --- Validation ---
missing = [name for name, val in {
    'API_KEY': API_KEY,
    'API_SECRET': API_SECRET,
    'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
    'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
}.items() if not val]
if missing:
    raise ValueError(
        "Missing required environment variables: " + ", ".join(missing)
    )
