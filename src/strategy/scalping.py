# src/strategy/scalping.py

from .strategy import Strategy
import logging

class ScalpingStrategy(Strategy):
    def __init__(self, exchange, data_handler, order_manager, indicator_manager, config):
        super().__init__(exchange, data_handler, order_manager, indicator_manager, config)
        self.symbols = config['symbols']
        self.timeframe = config['timeframe']
        self.kline_limit = config.get('kline_limit', 100)
        self.quantity = config['quantity']

    # REEMPLAZA ESTA FUNCIÓN COMPLETA
    def check_signals(self):
        logging.info("==================== NUEVO CICLO DE ANÁLISIS ====================")
        for symbol in self.symbols:
            try:
                logging.info(f"Analizando símbolo: {symbol}")
                
                klines = self.exchange.get_klines(symbol, self.timeframe, self.kline_limit)
                if klines is None or len(klines) == 0:
                    logging.warning(f"No se pudieron obtener datos (klines) para {symbol}. Saltando este ciclo.")
                    continue

                df = self.data_handler.process_klines(klines)
                
                self.indicator_manager.add_indicators(df)

                # Extraemos el último valor de los indicadores para que sea fácil de leer
                last_close = df['close'].iloc[-1]
                # Asegúrate de que la columna 'RSI' exista antes de acceder a ella
                if 'RSI' not in df.columns:
                    logging.error(f"La columna 'RSI' no se encontró en el DataFrame para {symbol}. Revisa tu 'indicator_manager'.")
                    continue
                last_rsi = df['RSI'].iloc[-1]
                
                # Mostramos los valores actuales en el log
                logging.info(f"[{symbol}] Precio actual: {last_close:.4f}, RSI actual: {last_rsi:.2f}")

                # --- Lógica de la estrategia ---
                
                # Condiciones de entrada (usaremos variables para que el log sea más claro)
                rsi_buy_threshold = 30
                rsi_sell_threshold = 70

                enter_long_condition = (last_rsi < rsi_buy_threshold)
                enter_short_condition = (last_rsi > rsi_sell_threshold)
                
                # Evaluamos las condiciones y lo mostramos en el log
                if enter_long_condition:
                    logging.info(f"[{symbol}] CONDICIÓN DE COMPRA CUMPLIDA: RSI ({last_rsi:.2f}) < {rsi_buy_threshold}")
                    # Descomenta la siguiente línea cuando estés seguro de que quieres operar
                    self.order_manager.place_order(symbol, 'BUY', self.quantity)
                    logging.info(f"[{symbol}] SIMULANDO orden de COMPRA (la llamada real está comentada).")

                elif enter_short_condition:
                    logging.info(f"[{symbol}] CONDICIÓN de VENTA CUMPLIDA: RSI ({last_rsi:.2f}) > {rsi_sell_threshold}")
                    # Descomenta la siguiente línea cuando estés seguro de que quieres operar
                    self.order_manager.place_order(symbol, 'SELL', self.quantity)
                    logging.info(f"[{symbol}] SIMULANDO orden de VENTA (la llamada real está comentada).")

                else:
                    logging.info(f"[{symbol}] No se cumplen condiciones. RSI ({last_rsi:.2f}) está entre {rsi_buy_threshold} y {rsi_sell_threshold}.")

            except Exception as e:
                logging.error(f"Ocurrió un error inesperado al analizar {symbol}: {e}")
        
        logging.info("==================== FIN DEL CICLO DE ANÁLISIS ====================\n")
