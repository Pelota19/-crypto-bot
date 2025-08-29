# crypto-bot

Bot de trading modular para Bybit (Testnet / Live).  
Objetivo: correr en Testnet con capital inicial de 1000 USDT, hacer paper trading hasta validar la estrategia y, si todo va bien, pasar a Live con mínimos cambios.

Características principales
- Modo testnet/paper por defecto.
- Gestión de riesgo: position sizing, max daily loss, objetivo diario de ganancia.
- Notificaciones por Telegram de órdenes y errores.
- Persistencia simple en SQLite para órdenes y PnL.
- Arquitectura modular: exchange client, strategy, trade manager, notifier, persistence.
- Puntos de extensión para añadir modelos ML/IA (scripts y hooks incluidos).

Requisitos mínimos
- Ubuntu (20.04+ recomendado)
- Python 3.10+
- Git

Instalación rápida (local / VM)
1. Clona el repo:
   git clone git@github.com:Pelota19/-crypto-bot.git
   cd crypto-bot

2. Crea virtualenv e instala:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

3. Copia y edita variables:
   cp .env.example .env
   # Rellena BYBIT_API_KEY, BYBIT_API_SECRET (testnet keys) y TELEGRAM_TOKEN/CHAT_ID
   # Asegurate BYBIT_MODE=paper y STARTING_BALANCE_USDT=1000

4. Inicializa DB (se crea automáticamente al ejecutar)

5. Ejecuta en modo demo/testnet:
   python -m src.main

Comandos útiles
- Ejecutar en background (systemd): ver scripts/deploy_systemd.sh
- Logs importantes se envían por Telegram (configura TELEGRAM_TOKEN y TELEGRAM_CHAT_ID)

Cambiar a Live
- Cambiar BYBIT_MODE=live en .env
- Revisa cuidadosamente los límites y la configuración de riesgo antes de operar en real.

Añadir IA/ML
- Hay un directorio `src/ai/` con plantillas de entrenamiento y `src/strategy/predictor.py` que carga modelos. Puedes entrenar modelos localmente y guardarlos en `models/` para que el bot los use.

Soporte y próximos pasos
- Lee los archivos en `src/` para entender flujo.
- Ejecuta en Testnet, recolecta resultados y ajustamos la estrategia/IA.
