# crypto_bot (demo)

Este PR añade archivos faltantes mínimos para que el repositorio tenga un entrypoint y componentes básicos:

- src/config.py (config por defecto)
- src/ai/__init__.py
- src/orders/manager.py (manager de órdenes simulado)
- src/strategy.py (decisor que usa src/ai/scorer)
- src/main.py (entrypoint demo)

- Scalping multipar con timeframe 1m (EMA + RSI como base).
- **Selección inteligente de pares**: Sistema de ranking top-K que selecciona los mejores símbolos basado en señales de estrategia y viabilidad de trading.
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
│  ├─ run.sh
│  ├─ run_testnet.sh
│  └─ select_pairs_smoke.py
└─ src/
   ├─ __init__.py
   ├─ main.py
   ├─ config.py
   ├─ state.py
   ├─ pair_selector.py
   ├─ exchange/
   │  └─ binance_client.py
   ├─ orders/
   │  └─ manager.py
   ├─ risk/
   │  └─ manager.py
   ├─ strategy/
   │  └─ strategy.py
   ├─ ai/
   │  └─ scorer.py
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

5) Probar selección de pares (opcional):
```bash
# Test sin conexión de red completa
bash scripts/run_testnet.sh

# Test de selección de pares (requiere API keys)
python scripts/select_pairs_smoke.py
```

## Uso por Telegram

Comandos disponibles:
- `/status`: muestra estado actual (P&L del día, objetivo, pausado/activo).
- `/pause`: pausa nuevas entradas.
- `/resume`: reanuda entradas (si no se alcanzó el P&L del día).

## Parámetros clave (desde .env)

### Trading básico:
- `MODE`: "paper" o "live".
- `STARTING_BALANCE_USDT`, `POSITION_SIZE_PERCENT`.
- `DAILY_PROFIT_TARGET_USD`, `MAX_DAILY_LOSS_USD`.
- `BINANCE_TESTNET`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`.

### Selección de pares (nuevo):
- `TOP_K_SELECTION`: true/false - habilita selección inteligente de pares.
- `MAX_ACTIVE_SYMBOLS`: número máximo de símbolos para operar por ciclo (default: 5).
- `MIN_NOTIONAL_USD`: valor mínimo de posición en USD (default: 10.0).

## Desarrollo y Validación

Validar configuración:
```bash
python validate_config.py
```

Ejecutar tests:
```bash
python test_basic.py
# o
python -m pytest test_basic.py -v
```

Linting y formateo:
```bash
python -m ruff check .
python -m black .
python -m mypy src --ignore-missing-imports
```

## Notas

- Este bot inicia con una estrategia base (EMA + RSI) para 1m como punto de partida. Es modular para incorporar técnicas más modernas (microestructura, orderbook, IA de ajuste dinámico de parámetros).
- **Nueva funcionalidad**: Sistema de selección Top-K que prioriza los mejores pares basado en señales de estrategia y viabilidad de trading (minQty, minNotional, liquidez).
- En testnet de Binance Futuros (USDM), los pares típicos disponibles incluyen BTC/USDT y ETH/USDT. La disponibilidad de OCO/SL/TP puede variar; el gestor de órdenes abstrae y aplica la mejor aproximación soportada por la API.
- El bot incluye validación de configuración, tests básicos y manejo robusto de errores para mayor estabilidad.