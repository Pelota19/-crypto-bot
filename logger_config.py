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
    - RotatingFileHandler -> logfile
    - StreamHandler -> escribe al stdout real (para mostrar en consola)
    - Redirige stdout/stderr al logger (prints y excepciones quedan en el logfile y en consola)
    """
    # Guardar referencias al stdout/stderr originales PARA evitar recursión
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    log_path = Path(logfile)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(level)

    # Eliminar handlers previos para evitar duplicados si se llama varias veces
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

    # Console handler que escribe al stdout ORIGINAL (no al sys.stdout que luego redirigimos)
    ch = logging.StreamHandler(stream=original_stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Redirigir stdout/stderr al logger (captura prints y tracebacks)
    class StreamToLogger:
        def __init__(self, level):
            self.level = level
            self._buffer = ""

        def write(self, message):
            if not message:
                return
            # Buffer para concatenar fragmentos hasta newline
            self._buffer += message
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if line:
                    logging.getLogger().log(self.level, line)

        def flush(self):
            if self._buffer:
                logging.getLogger().log(self.level, self._buffer)
                self._buffer = ""

    sys.stdout = StreamToLogger(logging.INFO)
    sys.stderr = StreamToLogger(logging.ERROR)

    logger.info("Logging inicializado. logfile=%s", os.path.abspath(str(log_path)))
