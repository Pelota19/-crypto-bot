import asyncio
import os
import ccxt.async_support as ccxt

async def main():
    api_key = os.getenv("BINANCE_API_KEY", "2f2c8badf2f0b0804c891361443019517c41a7f3e0a1dbdf0aab49489c4ed8e0").strip()
    secret = os.getenv("BINANCE_SECRET", "3bcc1125f8bdac95f6992d27289c98cf416d3bcbcd5d1740a8af24180a0bd232").strip()
    if not api_key or not secret:
        print("Set BINANCE_API_KEY and BINANCE_SECRET in environment.")
        return

    # Configuración explícita para testnet futures
    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": True,
        "options": {"defaultType": "future", "adjustForTimeDifference": True},
        "urls": {
            "api": {
                "public": "https://testnet.binancefuture.com",
                "private": "https://testnet.binancefuture.com",
            }
        }
    })

    exchange.verbose = True  # para ver la petición firmada (no compartir signature)

    try:
        server_time = await exchange.fetch_time()
        print("server_time (ms):", server_time)

        try:
            balance = await exchange.fetch_balance()
            print("fetch_balance OK. Keys in balance:", list(balance.keys()))
        except Exception as e:
            print("fetch_balance falló:", repr(e))

        # Intento de orden en modo test
        symbol = "BTC/USDT"
        side = "BUY"
        type_ = "limit"
        price = 1
        amount = 0.0001
        params = {"test": True}
        try:
            print("Intentando create_order en modo test (no creará orden real)...")
            res = await exchange.create_order(symbol, type_, side, amount, price, params)
            print("create_order test result:", res)
        except Exception as e:
            print("create_order (test) falló:", repr(e))

    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
