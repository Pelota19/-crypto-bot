# Crypto Scalping Bot - IA-Enabled Strategy

Bot de trading automatizado para scalping en criptomonedas con estrategia híbrida moderna y meta-scorer basado en IA. Configurado para operar en **Binance Futuros (USDM) testnet** con gestión avanzada de riesgo, notificaciones por Telegram y límites de capital.

## Características principales

- **Estrategia híbrida moderna**: EMA9/21, RSI, ATR, VWAP deviation, micro-trend analysis
- **Meta-scorer de IA ligero**: Combina features técnicas con pesos ajustables persistidos
- **SL/TP dinámicos**: Basados en ATR para adaptarse a la volatilidad del mercado
- **Gestión de capital**: Límite máximo de 2000 USDT para sizing, independiente del balance real
- **Meta diaria**: Al alcanzar +50 USD de PnL, detiene nuevas entradas hasta el día siguiente
- **Telegram como consola principal**: Logging reducido en shell, notificaciones por Telegram
- **Validación de minQty**: Evita errores de InvalidOrder por tamaños mínimos de Binance
- **Arquitectura modular**: Lista para extensiones avanzadas de microestructura e IA

## Arquitectura del sistema

```
.
├─ .env.example              # Configuración de ejemplo con todas las variables
├─ README.md                 # Esta documentación
├─ requirements.txt          # Dependencias Python
├─ data/                     # Directorio de persistencia (creado automáticamente)
│  ├─ crypto_bot.db         # Base de datos SQLite para órdenes
│  ├─ state.json            # Estado del bot (PnL diario, etc.)
│  └─ ai_model.json         # Pesos del meta-scorer IA
└─ src/
   ├─ main.py               # Orquestador principal
   ├─ config.py             # Configuración desde variables de entorno
   ├─ ai/
   │  └─ scorer.py          # SimpleMetaScorer con persistencia
   ├─ strategy/
   │  └─ strategy.py        # Estrategia híbrida con features avanzadas
   ├─ exchange/
   │  └─ binance_client.py  # Cliente mejorado con normalización y validaciones
   ├─ orders/
   │  └─ manager.py         # Gestor de órdenes con brackets automáticos
   └─ telegram/
      └─ console.py         # Interfaz Telegram (/status, /pause, /resume)
```

## Requisitos

- Python 3.10+
- Cuenta de testnet de Binance Futuros (USDM) y claves API de testnet
- Bot de Telegram y `chat_id` (opcional pero recomendado)

## Instalación

1. **Clonar y configurar entorno**:
```bash
git clone <repository>
cd crypto_bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. **Instalar dependencias**:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3. **Configurar variables de entorno**:
```bash
cp .env.example .env
# Editar .env con tus claves de testnet y datos de Telegram
```

4. **Ejecutar el bot**:
```bash
python -m src.main
```

## Configuración (.env)

### Variables esenciales:

- `MODE`: `"paper"` (simulación) o `"live"` (real en testnet)
- `BINANCE_TESTNET`: `true` para usar testnet (recomendado)
- `BINANCE_API_KEY` / `BINANCE_API_SECRET`: Claves de testnet
- `CAPITAL_MAX_USDT`: `2000.0` (límite máximo para sizing)
- `DAILY_PROFIT_TARGET_USD`: `50.0` (meta diaria en USD)
- `POSITION_SIZE_PERCENT`: `1.0` (1% del capital por trade)

### Telegram (recomendado):

- `TELEGRAM_TOKEN`: Token del bot de Telegram
- `TELEGRAM_CHAT_ID`: ID del chat para notificaciones

### Avanzadas:

- `LOG_LEVEL`: `WARNING` (reduce ruido en consola)
- `LEVERAGE`: `5` (apalancamiento para modo live)
- `MARGIN_MODE`: `ISOLATED` o `CROSSED`

## Uso por Telegram

El bot envía notificaciones automáticas y acepta comandos:

- `/status`: Estado actual (equity, PnL del día, meta, pausas)
- `/pause`: Pausa nuevas entradas
- `/resume`: Reanuda operaciones (si no se alcanzó la meta diaria)

Ejemplos de notificaciones:
```
🤖 Bot iniciado en testnet.
Universo: BTC/USDT, ETH/USDT, BNB/USDT...
🎯 BTC/USDT BUY @ 43250.00 | Score: 0.342 | SL 43100.00 | TP 43450.00
```

## Cómo funciona la estrategia

### Features técnicas analizadas:
1. **Momentum**: EMA9-EMA21 normalizado
2. **RSI centrado**: (RSI-50)/50 para detectar sobrecompra/sobreventa
3. **VWAP deviation**: Desviación del precio respecto a VWAP en ATRs
4. **ATR regime**: Penaliza volatilidad excesiva
5. **Micro-trend**: Pendiente de precio a corto plazo

### Meta-scorer IA:
- Combina las features con pesos ajustables
- Persiste learning en `data/ai_model.json`
- Genera score [-1,1] para decisiones de entrada
- Stub preparado para aprendizaje online futuro

### SL/TP dinámicos:
- Basados en ATR actual del símbolo
- SL: ~0.35x ATR, TP: ~0.70x ATR
- Límites mínimos/máximos para evitar extremos

## Gestión de riesgo

- **Capital cap**: Máximo 2000 USDT para sizing (configurable)
- **Meta diaria**: +50 USD → bloquea nuevas entradas hasta mañana
- **Loss diario**: -100 USD → protección adicional
- **minQty validation**: Evita errores de Binance por tamaños pequeños
- **Testnet por defecto**: Operación segura para pruebas

## Desarrollo y testing

**Validar configuración**:
```bash
python validate_config.py
```

**Ejecutar tests básicos**:
```bash
python test_basic.py
```

**Linting y formateo**:
```bash
python -m ruff check .
python -m black .
```

## Notas importantes

### Sobre testnet y minQty:
- En testnet, algunos símbolos pueden tener requirements de `minQty` más estrictos
- El bot valida automáticamente si un trade es viable antes de enviarlo
- Si el tamaño calculado es menor a `minQty`, omite la orden y continúa

### Sobre el meta-scorer IA:
- Versión actual es un "IA ligero" con pesos fijos pero persistidos
- Preparado para futuras mejoras con aprendizaje online
- Los pesos se pueden ajustar manualmente en `data/ai_model.json`

### Sobre Telegram vs consola:
- Por defecto `LOG_LEVEL=WARNING` para reducir spam en shell
- Telegram es el canal principal de monitoreo y control
- Todos los trades y eventos importantes se notifican por Telegram

### Extensibilidad:
- Arquitectura modular preparada para:
  - Features adicionales de microestructura
  - Orderbook analysis
  - ML models más avanzados
  - Multiple timeframes
  - Portfolio optimization