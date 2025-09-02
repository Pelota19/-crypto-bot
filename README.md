# Crypto Scalping Bot

Bot de trading automatizado para scalping en criptomonedas con **configuración dirigida por plan**. Actualmente configurado para operar en **Binance Futuros (USDM) testnet**, con gestión de riesgo avanzada, selección dinámica de universo y notificaciones por **Telegram**.

## 🚀 Características Principales

### Sistema de Configuración por Plan
- **Configuración YAML**: Plan de trading centralizado en `config/plan.yml`
- **Selección dinámica de universo**: Símbolos basados en liquidez y volumen
- **Guardrails de riesgo**: Límites automáticos de posición y pérdida diaria
- **Modo fallback**: Degradación automática de testnet a paper si faltan credenciales
- **CLI seguro**: Aplicación de configuración sin tocar secretos

### Trading y Gestión de Riesgo
- **Scalping conservador**: Timeframe 5m por defecto con EMA + RSI
- **Gestión de riesgo**: 0.5% tamaño de posición, 2% pérdida diaria máxima
- **Stop Loss/Take Profit**: 0.20%/0.40% configurables por plan
- **Apalancamiento**: 5x en modo aislado por defecto
- **Órdenes bracket**: SL/TP automáticos en modo live

### Integración y Monitoreo
- **Telegram avanzado**: Comandos extendidos (`/status`, `/plan`, `/refresh`)
- **Persistencia SQLite**: Historial de órdenes y balances
- **Logs estructurados**: Logging completo con rotación diaria
- **CI/CD**: Validación automática de configuración

## 📁 Estructura del Proyecto

```
.
├── config/
│   └── plan.yml                 # Configuración de trading centralizada
├── scripts/
│   ├── apply_profile.py         # CLI para aplicar plan a .env
│   └── run.sh
├── src/
│   ├── config/
│   │   └── plan_loader.py       # Carga y validación de planes
│   ├── risk/
│   │   ├── manager.py           # Cálculos SL/TP
│   │   └── guardrails.py        # Aplicación de límites de riesgo
│   ├── universe/
│   │   └── selector.py          # Selección dinámica de símbolos
│   ├── exchange/
│   │   └── binance_client.py    # Cliente de Binance Futures
│   ├── orders/
│   │   └── manager.py           # Gestión de órdenes y brackets
│   ├── persistence/
│   │   └── sqlite_store.py      # Almacenamiento de datos
│   ├── telegram/
│   │   └── console.py           # Interfaz de Telegram
│   └── main.py                  # Loop principal de trading
├── .github/workflows/
│   └── validate-profile.yml     # CI para validación de planes
├── test_plan_system.py          # Tests de validación completa
└── README.md
```

## 🛠️ Instalación y Configuración Rápida

### 1. Configuración del Entorno

```bash
# Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configuración con Plan (Recomendado)

```bash
# Aplicar configuración desde el plan
python scripts/apply_profile.py --dry-run    # Previsualizar cambios
python scripts/apply_profile.py --write      # Aplicar a .env

# Validar configuración
python validate_config.py

# Validar sistema completo
python test_plan_system.py
```

### 3. Configuración Manual de Secretos

Editar `.env` y agregar las credenciales:

```bash
# Binance Testnet (obligatorio para modo live)
BINANCE_API_KEY=tu_api_key_testnet
BINANCE_API_SECRET=tu_api_secret_testnet

# Telegram (opcional pero recomendado)
TELEGRAM_TOKEN=tu_bot_token
TELEGRAM_CHAT_ID=tu_chat_id
```

### 4. Ejecución

```bash
# Ejecutar bot
python -m src.main

# O usando script
bash scripts/run.sh
```

## 📋 Configuración del Plan (config/plan.yml)

El bot utiliza un sistema de configuración dirigida por plan que permite:

### Configuración de Riesgo
```yaml
risk:
  position_size_pct: 0.5          # 0.5% de equity por posición
  max_risk_per_trade_pct: 0.5     # Máximo 0.5% de riesgo por trade
  max_daily_loss_pct: 2.0         # Máximo 2% de pérdida diaria
  max_concurrent_positions: 3      # Máximo 3 posiciones simultáneas
  leverage: 5                      # Apalancamiento 5x
  margin_mode: "ISOLATED"          # Modo de margen aislado
```

### Selección Dinámica de Universo
```yaml
universe:
  mode: "dynamic"                  # Selección automática basada en liquidez
  dynamic_selector:
    min_quote_volume_24h_usdt: 300000000  # Mínimo 300M USDT volumen
    max_spread_bps: 2                     # Máximo 2 bps de spread
    max_symbols: 10                       # Máximo 10 símbolos
```

### Stop Loss y Take Profit
```yaml
sl_tp:
  sl_pct: 0.20                     # Stop Loss 0.20%
  tp_pct: 0.40                     # Take Profit 0.40%
```

## 🎮 Comandos de Telegram

Comandos disponibles para control del bot:

- `/status` - Estado completo (equity, PnL, posiciones, plan activo)
- `/plan` - Información del plan de trading actual  
- `/pause` - Pausar nuevas entradas
- `/resume` - Reanudar trading
- `/refresh` - Forzar actualización del universo dinámico

## 🔧 Configuración Avanzada

### Modo de Fallback Automático

El bot automáticamente degrada de `live_testnet` a `paper` si faltan credenciales:

```
Plan mode is 'live_testnet' but API credentials are missing. 
Falling back to paper mode.
```

### Guardrails de Riesgo

Sistema automático que previene:
- Posiciones que excedan el tamaño máximo configurado
- Trading cuando se alcanza la pérdida diaria máxima  
- Más posiciones concurrentes del límite configurado

### Selección Dinámica de Símbolos

Criterios de filtrado automático:
- Volumen mínimo de 24h
- Spread máximo permitido
- Profundidad mínima de orderbook
- Volatilidad realizada mínima

## 🧪 Desarrollo y Testing

### Validación Completa
```bash
python test_plan_system.py        # Test completo del sistema
python validate_config.py         # Validación de configuración
python test_basic.py             # Tests básicos
```

### Desarrollo
```bash
# Linting y formateo
python -m ruff check .
python -m black .
python -m mypy src --ignore-missing-imports
```

## 📊 Compatibilidad y Migración

### Compatibilidad hacia atrás
- ✅ Funciona con y sin `plan.yml`
- ✅ Mantiene semántica existente de paper/live
- ✅ Variables de entorno existentes respetadas

### Migración desde versión anterior
1. El bot funciona sin cambios si no existe `plan.yml`
2. Para activar el sistema de plan: `python scripts/apply_profile.py --write`
3. Personalizar `config/plan.yml` según necesidades

## ⚡ Características de Seguridad

- **Separación de secretos**: Configuración operacional separada de credenciales
- **Defaults conservadores**: Configuración segura por defecto
- **Validación automática**: CI/CD que valida configuración en cada cambio
- **Modo papel automático**: Fallback seguro si faltan credenciales
- **Límites estrictos**: Guardrails que previenen trading riesgoso

## 📈 Roadmap y Extensibilidad

El bot está diseñado modularmente para incorporar:
- ✅ Gestión de riesgo avanzada
- ✅ Selección dinámica de universo  
- 🔄 Microestructura de mercado
- 🔄 Machine learning para parámetros dinámicos
- 🔄 Análisis de orderbook en tiempo real
- 🔄 Optimización automática de spreads