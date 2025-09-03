"""Logging configuration with rotation and a single global setup."""
import logging
import logging.handlers
from pathlib import Path
from config.settings import LOG_LEVEL, LOGS_DIR

def setup_logging():
    """Setup logging with console and rotating file handlers. Idempotent."""
    LOGS_DIR.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    # Avoid adding duplicate handlers if called multiple times
    if root_logger.handlers:
        return root_logger

    # Set log level
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)

    # Rotating file handler
    log_file = LOGS_DIR / "crypto_bot.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)

    # Error file handler
    err_file = LOGS_DIR / "crypto_bot_error.log"
    eh = logging.handlers.RotatingFileHandler(
        err_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(formatter)
    root_logger.addHandler(eh)

    return root_logger

def get_logger(name: str = None) -> logging.Logger:
    return logging.getLogger(name)
