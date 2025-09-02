# Crypto Scalping Bot

Bot de trading automatizado para scalping en criptomonedas. Actualmente configurado para operar exclusivamente en **Binance Futuros (USDM) testnet**, con objetivo diario de ganancias (P&L) y notificaciones/controles por **Telegram**.

## Características

- Scalping multipar con timeframe 1m (EMA + RSI como base).
- Gestión de riesgo: tamaño de posición, Stop Loss (SL) y Take Profit (TP).
- Meta diaria (P&L) en USD: al alcanzarla, el bot detiene nuevas entradas hasta el siguiente día.
- Integración con Telegram como consola (/status, /pause, /resume).
- Arquitectura modular y lista para extender con técnicas más modernas e IA.

## Estructura

```
.
├─ .env.example
├─ .gitignore
├─ README.md
├─ requirements.txt
├─ scripts/
│  └─ run.sh
└─ src/
   ├─ __init__.py
   ├─ main.py
   ├─ config.py
   ├─ state.py
   ├─ exchange/
   │  └─ binance_client.py
   ├─ orders/
   │  └─ manager.py
   ├─ risk/
   │  └─ manager.py
   ├─ strategy/
   │  └─ scalping.py
   └─ telegram/
      └─ console.py
```

## Requisitos

- Python 3.10+
- Cuenta de testnet de Binance Futuros (USDM) y claves API de testnet.
- Bot de Telegram y `chat_id`.

## Instalación

1) Crear y activar entorno virtual:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2) Instalar dependencias:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3) Configurar variables de entorno:
- Copiar `.env.example` a `.env` y completar con tus datos reales de testnet y Telegram.

4) Ejecutar:
```bash
bash scripts/run.sh
# o
python -m src.main
```

## Uso por Telegram

Comandos disponibles:
- `/status`: muestra estado actual (P&L del día, objetivo, pausado/activo).
- `/pause`: pausa nuevas entradas.
- `/resume`: reanuda entradas (si no se alcanzó el P&L del día).

## Parámetros clave (desde .env)

- `MODE`: "paper" o "live".
- `STARTING_BALANCE_USDT`, `POSITION_SIZE_PERCENT`.
- `DAILY_PROFIT_TARGET_USD`, `MAX_DAILY_LOSS_USD`.
- `BINANCE_TESTNET`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`.

## Notas

- Este bot inicia con una estrategia base (EMA + RSI) para 1m como punto de partida. Es modular para incorporar técnicas más modernas (microestructura, orderbook, IA de ajuste dinámico de parámetros).
- En testnet de Binance Futuros (USDM), los pares típicos disponibles incluyen BTC/USDT y ETH/USDT. La disponibilidad de OCO/SL/TP puede variar; el gestor de órdenes abstrae y aplica la mejor aproximación soportada por la API.