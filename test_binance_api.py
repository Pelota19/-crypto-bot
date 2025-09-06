import asyncio
import logging
import ccxt.async_support as ccxt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = "2f2c8badf2f0b0804c891361443019517c41a7f3e0a1dbdf0aab49489c4ed8e0"
API_SECRET = "3bcc1125f8bdac95f6992d27289c98cf416d3bcbcd5d1740a8af24180a0bd2"
USE_TESTNET = True

async def main():
    params = {
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "future"}
    }

    if USE_TESTNET:
        params["urls"] = {
            "api": {
                "fapiPublic": "https://testnet.binancefuture.com/fapi/v1",
                "fapiPrivate": "https://testnet.binancefuture.com/fapi/v1",
            }
        }

    client = ccxt.binance(params)
    if USE_TESTNET and hasattr(client, "set_sandbox_mode"):
        client.set_sandbox_mode(True)

    try:
        await client.load_markets()
        logger.info("✅ Conexión OK, mercados cargados")
        
        ticker = await client.fetch_ticker("BTC/USDT")
        logger.info("Ticker BTC/USDT: %s", ticker)
    except Exception as e:
        logger.error("❌ Error conectando a Binance testnet: %s", e)
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
