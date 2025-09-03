"""Logging configuration with rotation."""
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from config.settings import LOG_LEVEL, LOGS_DIR

def setup_logging():
    """Setup logging with console and rotating file handlers."""
    # Create logs directory
    LOGS_DIR.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Clear existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set log level
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Rotating file handler for general logs
    log_file = LOGS_DIR / "crypto_bot.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler
    error_file = LOGS_DIR / "crypto_bot_error.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    return root_logger

def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)