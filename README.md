# Crypto Scalping Bot

Bot de trading automatizado para scalping en criptomonedas. Actualmente preparado para operar en **testnet**, con objetivo diario de ganancias (PLN) y notificaciones/controles por **Telegram**.

## Características

- Scalping multipar con timeframe 1m (EMA + RSI como base).
- Gestión de riesgo: tamaño de posición, Stop Loss (SL) y Take Profit (TP).
- Meta diaria (PLN) en USD: al alcanzarla, el bot detiene nuevas entradas hasta el siguiente día.
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
   ├─ runner.py
   ├─ config.py
   ├─ state.py
   ├─ exchange/
   │  └─ client.py
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
- Cuenta de testnet en el exchange (p. ej. Binance o Bybit) y claves API de testnet.
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
python -m src.runner
```

## Uso por Telegram

Comandos disponibles:
- `/status`: muestra estado actual (PLN del día, objetivo, pausado/activo).
- `/pause`: pausa nuevas entradas.
- `/resume`: reanuda entradas (si no se alcanzó el PLN del día).

## Parámetros clave (desde .env)

- `DAILY_PROFIT_GOAL_USD`: objetivo diario (p. ej. 30).
- `INVESTMENT_MAX_USD`: capital máximo (p. ej. 2000).
- `PAIRS`: lista separada por comas de pares (BTC/USDT,ETH/USDT).
- `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT`: % SL/TP sobre precio de entrada.
- `EXCHANGE_NAME`, `EXCHANGE_TESTNET`, `API_KEY`, `API_SECRET`.

## Notas

- Este bot inicia con una estrategia base (EMA + RSI) para 1m como punto de partida. Es modular para incorporar técnicas más modernas (microestructura, orderbook, IA de ajuste dinámico de parámetros, etc.).
- Dependiendo del exchange y modo (spot/futuros), la disponibilidad de OCO/SL/TP varía. El gestor de órdenes abstrae y aplica la mejor aproximación soportada por la API.