import ccxt.async_support as ccxt
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key, api_secret, use_testnet=True):
        self.client = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"}
        })
        if use_testnet:
            self.client.set_sandbox_mode(True)
            logger.info("Binance TESTNET enabled (Futures USDT-M)")

    async def get_balance_usdt(self):
        bal = await self.client.fetch_balance()
        return float(bal['USDT']['total'])

    async def fetch_ohlcv_df(self, symbol, timeframe="1m", limit=200):
        raw = await self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    async def close(self):
        await self.client.close()
