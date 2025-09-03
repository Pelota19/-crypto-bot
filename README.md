# crypto_bot (demo)

Este PR añade archivos faltantes mínimos para que el repositorio tenga un entrypoint y componentes básicos:

- src/config.py (config por defecto)
- src/ai/__init__.py
- src/orders/manager.py (manager de órdenes simulado)
- src/strategy.py (decisor que usa src/ai/scorer)
- src/main.py (entrypoint demo)

Objetivo: facilitar review y pruebas locales. Ninguna implementación conecta por defecto con APIs externas; todas son plantillas que el mantenedor deberá adaptar.