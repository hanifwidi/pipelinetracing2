# utils/logger.py
import logging
from logging.handlers import RotatingFileHandler
import sys
import os
import multiprocessing
from rich.logging import RichHandler
from config import cfg

def setup_logger(name: str = "VectorFactory") -> logging.Logger:
    """
    Configures and returns a professional multi-handler logger.
    Provides Rich terminal output for UX and file-based rotating logs for debugging.
    """
    # Ensure log directory exists before initializing file handlers
    cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)

    # Prevent duplicate handlers if instantiated multiple times
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG if cfg.DEBUG_MODE else logging.INFO)
    logger.propagate = False

    # 1. Rich Console Handler (Terminal UI)
    rich_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=False,
        console=None  # Uses default stdout console
    )
    rich_handler.setLevel(logging.DEBUG if cfg.DEBUG_MODE else logging.INFO)
    rich_formatter = logging.Formatter("%(message)s")
    rich_handler.setFormatter(rich_formatter)

    # 2. Rotating File Handler (Disk Storage)
    name = "pipeline.log" if multiprocessing.current_process().name == "MainProcess" else f"worker-{os.getpid()}.log"
    log_file_path = cfg.LOG_DIR / name
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,              # Keep last 5 logs
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - [%(processName)s:%(threadName)s] - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    logger.addHandler(rich_handler)
    logger.addHandler(file_handler)

    return logger

# Global logger instance mapped to the utility module
log = setup_logger()
