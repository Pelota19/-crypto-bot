import sys
import asyncio

from src.config import (
    BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
)
from src.exchange.binance_client import BinanceFuturesClient
from src.telegram.console import send_message

def main() -> int:
    ok = True
    print("Python:", sys.version.replace("\n", " "))

    # Binance client/public data
    try:
        ex = BinanceFuturesClient(BINANCE_API_KEY or "", BINANCE_API_SECRET or "", testnet=BINANCE_TESTNET)
        df = ex.fetch_ohlcv_df("BTC/USDT", timeframe="1m", limit=5)
        assert not df.empty, "fetch_ohlcv_df returned empty DataFrame"
        print("Binance testnet OK: fetched", len(df), "candles for BTC/USDT")
    except Exception as e:
        ok = False
        print("[ERROR] Binance testnet check failed:", e)

    # Telegram (optional)
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            asyncio.run(send_message("✅ validate_config: configuración OK y bot puede enviar mensajes."))
            print("Telegram OK: test message sent")
        else:
            print("Telegram skipped (TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set)")
    except Exception as e:
        ok = False
        print("[ERROR] Telegram check failed:", e)

    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())