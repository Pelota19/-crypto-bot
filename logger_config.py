import logging
import logging.handlers
import sys
from pathlib import Path
import os

def setup_logging(
    logfile: str = "logs/unified_main.log.txt",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
):
    """
    Configura logging raíz:
    - RotatingFileHandler -> logfile (se crea la carpeta si hace falta)
    - NO agrega StreamHandler (no imprime en consola)
    - Redirige stdout/stderr al logger (prints y tracebacks irán al archivo)
    """
    log_path = Path(logfile)
    # Si logfile es relativo, interpretarlo desde el cwd actual.
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(level)

    # Eliminar handlers previos para evitar duplicados
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Redirigir stdout/stderr al logger
    class StreamToLogger:
        def __init__(self, level):
            self.level = level

        def write(self, message):
            # Evitar mensajes vacíos
            if not message:
                return
            message = message.rstrip("\n")
            if not message:
                return
            for line in message.splitlines():
                logging.getLogger().log(self.level, line)

        def flush(self):
            pass

    sys.stdout = StreamToLogger(logging.INFO)
    sys.stderr = StreamToLogger(logging.ERROR)

    logger.info("Logging inicializado. logfile=%s", os.path.abspath(str(log_path)))
