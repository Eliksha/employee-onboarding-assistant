"""Console + rotating file logging (logs/app.log). Safe to call more than once."""
import logging
from logging.handlers import RotatingFileHandler

from backend.config import settings

LOGGER_NAME = "app"
_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_configured", False):
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(settings.log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        logger.warning("Could not create log file; logging to console only")

    logger._configured = True
    return logger
