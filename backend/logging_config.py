"""Console + rotating file logging (logs/app.log). Safe to call more than once."""
import logging
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

from backend.config import settings

LOGGER_NAME = "app"
_FORMAT = "%(asctime)s | %(levelname)s | rid=%(request_id)s | %(message)s"

# Set per request by the middleware; "-" outside a request (startup, scripts, tests).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Stamp every record with the current request ID so service-level logs can be correlated."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


def install_request_id_filter(logger: logging.Logger) -> None:
    if not any(isinstance(f, RequestIdFilter) for f in logger.filters):
        logger.addFilter(RequestIdFilter())


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_configured", False):
        return logger
    logger.setLevel(logging.INFO)
    install_request_id_filter(logger)
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
