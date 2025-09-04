import asyncio
import ccxt.async_support as ccxt

API_KEY = "2f2c8badf2f0b0804c891361443019517c41a7f3e0a1dbdf0aab49489c4ed8e0"
API_SECRET = "3bcc1125f8bdac95f6992d27289c98cf416d3bcbcd5d1740a8af24180a0bd232"

async def main():
    binance = ccxt.binance({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",  # Conectamos a futuros
        },
    })

    # Activar modo sandbox/testnet
    binance.set_sandbox_mode(True)

    try:
        balance = await binance.fetch_balance()
        print("✅ Conexión exitosa, balance en Futures Testnet:")
        print(balance)
    except Exception as e:
        print("❌ Error al conectar:", e)
    finally:
        await binance.close()

asyncio.run(main())
